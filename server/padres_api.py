"""Panel de padres (web, móvil): API JSON en /padres/api/* y páginas estáticas de server/padres_web/.

Es una sub-aplicación FastAPI independiente: puente.py solo hace `app.mount("/padres", padres_api.crear_app())`.
Seguridad:
- Login con usuario y contraseña (padres_auth); sesión en una cookie HttpOnly (`__Host-padres` con Secure en HTTPS).
- La familia sale SIEMPRE de la sesión; un id de otra familia da 404.
- CSRF: toda petición que modifica exige la cabecera X-Panel y, si trae Origin, debe ser el mismo host
  (el CORS del puente es «*» con credenciales, así que no se confía en él).
- Cabeceras estrictas (CSP sin scripts de terceros ni inline, no-store, nosniff, DENY, no-referrer).
- Los textos de los hechos vienen de lo que dice el niño: la página los pinta con textContent, nunca como HTML.
"""
import os
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

import agenda
import memoria
import padres_auth as auth
import persona

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "padres_web")
COOKIE_SEGURA = "__Host-padres"
COOKIE_LOCAL = "padres"              # solo en http (pruebas en el PC): sin prefijo __Host- ni Secure
_METODOS_QUE_CAMBIAN = {"POST", "PUT", "PATCH", "DELETE"}
_LOCALES = {"127.0.0.1", "::1", "localhost"}
_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")


class Entrada(BaseModel):
    usuario: str = Field(max_length=40)
    clave: str = Field(max_length=200)


class CambioClave(BaseModel):
    actual: str = Field(max_length=200)
    nueva: str = Field(max_length=200)


class PerfilIn(BaseModel):
    apodo: str = Field(default="", max_length=60)
    nacimiento: str = Field(default="", max_length=10)
    gustos: list[str] = Field(default_factory=list, max_length=30)


class PersonaIn(BaseModel):
    identidad: str = Field(default="", max_length=400)
    tono: str = Field(default="", max_length=800)
    reglas_extra: list[str] = Field(default_factory=list, max_length=20)


class TextoIn(BaseModel):
    texto: str = Field(max_length=300)
    vence: str | None = Field(default=None, max_length=10)


class EventoIn(BaseModel):
    tipo: str = Field(default="recordatorio", max_length=20)
    titulo: str = Field(min_length=1, max_length=120)
    hora: str = Field(max_length=5)
    fecha: str = Field(default="", max_length=10)
    dias: list[int] = Field(default_factory=list, max_length=7)
    activo: bool = True


class ActivoIn(BaseModel):
    activo: bool = True


class AjustesIn(BaseModel):
    avisos_activos: bool = False
    silencio_desde: str = Field(default="", max_length=5)
    silencio_hasta: str = Field(default="", max_length=5)
    permitir_alarma_silencio: bool = False


def _es_https(request):
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").lower() == "https"


def _ip(request):
    """IP del cliente. Detrás de Caddy (mismo equipo) la real viene en el último valor de X-Forwarded-For."""
    directo = request.client.host if request.client else ""
    if directo in _LOCALES:
        reenviado = request.headers.get("x-forwarded-for", "")
        if reenviado:
            return reenviado.split(",")[-1].strip()[:45]
    return directo


def _token(request):
    return request.cookies.get(COOKIE_SEGURA) or request.cookies.get(COOKIE_LOCAL) or ""


def _usuario(request):
    usuario = auth.usuario_de_sesion(_token(request))
    if not usuario:
        raise HTTPException(401, "Hay que entrar de nuevo.")
    return usuario


def _perfil_id(usuario):
    perfil_id = memoria.perfil_id_de_familia(usuario["familia_id"])
    if not perfil_id:
        raise HTTPException(404, "No hay perfil.")
    return perfil_id


def _hecho_de(usuario, id_hecho):
    """El hecho solo si es de esta familia; si no, 404 (no se confirma que exista)."""
    hecho = memoria.obtener_hecho(id_hecho)
    if not hecho or hecho["perfil_id"] != _perfil_id(usuario):
        raise HTTPException(404, "No existe.")
    return hecho


def _rasgo_de(usuario, id_rasgo):
    rasgo = memoria.obtener_rasgo(id_rasgo)
    if not rasgo or rasgo["perfil_id"] != _perfil_id(usuario):
        raise HTTPException(404, "No existe.")
    return rasgo


def _evento_de(usuario, id_evento):
    """El evento solo si es de esta familia; si no, 404 (no se confirma que exista)."""
    evento = agenda.obtener_evento(id_evento, familia_id=usuario["familia_id"])
    if not evento:
        raise HTTPException(404, "Ese evento no existe.")
    return evento


_CAMPOS_HECHO = ("id", "texto", "estado", "categoria", "fuente", "vence", "creado", "decidido")


def _hecho_json(h):
    return {k: h.get(k) for k in _CAMPOS_HECHO}


def _rasgo_json(r):
    return {k: r.get(k) for k in ("id", "texto", "estado", "creado", "decidido")}


def _perfil_json(fila, origen):
    return {"apodo": fila.get("apodo") or "", "nacimiento": fila.get("nacimiento") or "",
            "gustos": fila.get("gustos") or [], "origen": origen,
            "edad": persona.edad_de(fila.get("nacimiento"))}


def _persona_json(datos, origen):
    return {"identidad": datos.get("identidad") or "", "tono": datos.get("tono") or "",
            "reglas_extra": datos.get("reglas_extra") or [], "origen": origen,
            "defecto": {k: persona.PERSONA_POR_DEFECTO[k] for k in ("identidad", "tono", "reglas_extra")},
            "ejemplo": persona.PERSONA_EJEMPLO}


def crear_app():
    app = FastAPI(title="Panel de padres", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def seguridad(request: Request, llamar):
        ruta = request.url.path
        if ruta.startswith("/api/") and request.method in _METODOS_QUE_CAMBIAN:
            if request.headers.get("x-panel") != "1":
                return _con_cabeceras(JSONResponse({"detail": "Falta la cabecera X-Panel."}, status_code=403))
        origen = request.headers.get("origin")
        if origen and ruta.startswith("/api/"):
            if urlparse(origen).netloc != request.headers.get("host", ""):     # solo Host: nada que un cliente pueda reenviar
                return _con_cabeceras(JSONResponse({"detail": "Origen no permitido."}, status_code=403))
        return _con_cabeceras(await llamar(request))

    # ---------- Páginas ----------
    def _pagina(nombre, tipo):
        ruta = os.path.join(WEB_DIR, nombre)
        if not os.path.isfile(ruta):
            raise HTTPException(404, "No existe.")
        return FileResponse(ruta, media_type=tipo)

    @app.get("/", include_in_schema=False)
    def indice():
        return _pagina("index.html", "text/html; charset=utf-8")

    @app.get("/app.js", include_in_schema=False)
    def js():
        return _pagina("app.js", "text/javascript; charset=utf-8")

    @app.get("/app.css", include_in_schema=False)
    def css():
        return _pagina("app.css", "text/css; charset=utf-8")

    # ---------- Sesión ----------
    @app.post("/api/sesion")
    def entrar(datos: Entrada, request: Request, respuesta: Response):
        try:
            resultado = auth.iniciar_sesion(datos.usuario, datos.clave, _ip(request))
        except auth.Bloqueado as bloqueo:
            return JSONResponse({"detail": "Demasiados intentos. Espera un rato y vuelve a probar."},
                                status_code=429, headers={"Retry-After": str(bloqueo.segundos)})
        if not resultado:
            raise HTTPException(401, "Usuario o contraseña incorrectos.")
        token, usuario = resultado
        segura = _es_https(request)
        respuesta.set_cookie(COOKIE_SEGURA if segura else COOKIE_LOCAL, token, max_age=auth.SESION_DIAS_MAX * 86400,
                             path="/", httponly=True, secure=segura, samesite="lax")
        auth.auditar(usuario, "entrar")
        return {"usuario": usuario["nombre"]}

    @app.delete("/api/sesion")
    def salir(request: Request, respuesta: Response):
        auth.cerrar_sesion(_token(request))
        respuesta.delete_cookie(COOKIE_SEGURA, path="/", secure=True, httponly=True, samesite="lax")   # __Host- exige Secure
        respuesta.delete_cookie(COOKIE_LOCAL, path="/", httponly=True, samesite="lax")
        return {"ok": True}

    @app.get("/api/yo")
    def yo(request: Request):
        return {"usuario": _usuario(request)["nombre"]}

    @app.post("/api/clave")
    def cambiar_clave(datos: CambioClave, request: Request):
        usuario = _usuario(request)
        try:
            correcta = auth.comprobar_clave(usuario["usuario_id"], datos.actual, _ip(request))
        except auth.Bloqueado as bloqueo:
            return JSONResponse({"detail": "Demasiados intentos. Espera un rato y vuelve a probar."},
                                status_code=429, headers={"Retry-After": str(bloqueo.segundos)})
        if not correcta:
            raise HTTPException(403, "La contraseña actual no es correcta.")
        try:
            auth.cambiar_clave_de(usuario["usuario_id"], datos.nueva, conservar_token=_token(request))
        except auth.ClaveDebil as error:
            raise HTTPException(422, str(error))
        auth.auditar(usuario, "cambiar-clave")
        return {"ok": True}

    # ---------- Perfil ----------
    @app.get("/api/perfil")
    def leer_perfil(request: Request):
        usuario = _usuario(request)
        fila = memoria.leer_perfil(usuario["familia_id"])
        if fila:
            return _perfil_json(fila, "base")
        if str(usuario["familia_id"]) == "1" and memoria.leer_perfil() is None:      # respaldo de lectura
            return _perfil_json(persona.perfil_desde_archivo(), "archivo")
        return _perfil_json({}, "nuevo")

    @app.put("/api/perfil")
    def guardar_perfil(datos: PerfilIn, request: Request):
        usuario = _usuario(request)
        try:
            fila = memoria.guardar_perfil(datos.apodo, datos.nacimiento, datos.gustos, usuario["familia_id"])
        except ValueError as error:
            raise HTTPException(422, str(error))
        auth.auditar(usuario, "perfil")
        return _perfil_json(fila, "base")

    # ---------- Personalidad del robot ----------
    @app.get("/api/persona")
    def leer_persona(request: Request):
        usuario = _usuario(request)
        fila = memoria.leer_persona(familia_id=usuario["familia_id"])
        if fila:
            return _persona_json(fila, "base")
        if str(usuario["familia_id"]) == "1" and memoria.leer_persona() is None and persona.persona_desde_archivo():
            return _persona_json(persona.cargar_persona(), "archivo")                 # respaldo de lectura
        return _persona_json(persona.PERSONA_POR_DEFECTO, "defecto")

    @app.put("/api/persona")
    def guardar_persona(datos: PersonaIn, request: Request):
        usuario = _usuario(request)
        try:
            fila = memoria.guardar_persona(datos.identidad, datos.tono, datos.reglas_extra,
                                           familia_id=usuario["familia_id"])
        except ValueError as error:
            raise HTTPException(422, str(error))
        auth.auditar(usuario, "persona")
        return _persona_json(fila, "base")

    @app.delete("/api/persona")
    def restablecer_persona(request: Request):
        usuario = _usuario(request)
        memoria.restablecer_persona(familia_id=usuario["familia_id"])
        auth.auditar(usuario, "persona-restablecer")
        return _persona_json(persona.PERSONA_POR_DEFECTO, "defecto")

    # ---------- Hechos ----------
    @app.get("/api/hechos")
    def listar_hechos(request: Request, estado: str | None = None):
        usuario = _usuario(request)
        if estado and estado not in memoria.ESTADOS:
            raise HTTPException(422, "Estado desconocido.")
        return [_hecho_json(h) for h in memoria.listar(estado, perfil_id=_perfil_id(usuario))]

    @app.post("/api/hechos", status_code=201)
    def agregar_hecho(datos: TextoIn, request: Request):
        usuario = _usuario(request)
        perfil_id = _perfil_id(usuario)
        motivo = memoria._rechazo(" ".join(datos.texto.split()))
        if motivo:
            raise HTTPException(422, f"No se puede guardar: {motivo}.")
        id_hecho = memoria.agregar_candidato(datos.texto, fuente="agregado por los padres", estado="aprobado",
                                             vence=datos.vence or None, perfil_id=perfil_id)
        if not id_hecho:
            raise HTTPException(409, "Ya existe un hecho parecido.")
        memoria.decidir(id_hecho, "aprobado", por=usuario["nombre"])
        auth.auditar(usuario, "hecho-agregar", id_hecho)
        return _hecho_json(memoria.obtener_hecho(id_hecho))

    def _decidir(id_hecho, estado, request):
        usuario = _usuario(request)
        _hecho_de(usuario, id_hecho)
        memoria.decidir(id_hecho, estado, por=usuario["nombre"])
        auth.auditar(usuario, f"hecho-{estado}", id_hecho)
        return _hecho_json(memoria.obtener_hecho(id_hecho))

    @app.post("/api/hechos/{id_hecho}/aprobar")
    def aprobar_hecho(id_hecho: int, request: Request):
        return _decidir(id_hecho, "aprobado", request)

    @app.post("/api/hechos/{id_hecho}/rechazar")
    def rechazar_hecho(id_hecho: int, request: Request):
        return _decidir(id_hecho, "rechazado", request)

    @app.patch("/api/hechos/{id_hecho}")
    def editar_hecho(id_hecho: int, datos: TextoIn, request: Request):
        usuario = _usuario(request)
        _hecho_de(usuario, id_hecho)
        try:
            memoria.editar(id_hecho, datos.texto)
        except ValueError as error:
            raise HTTPException(422, str(error))
        auth.auditar(usuario, "hecho-editar", id_hecho)
        return _hecho_json(memoria.obtener_hecho(id_hecho))

    @app.delete("/api/hechos/{id_hecho}")
    def borrar_hecho(id_hecho: int, request: Request):
        usuario = _usuario(request)
        _hecho_de(usuario, id_hecho)
        memoria.borrar(id_hecho)
        auth.auditar(usuario, "hecho-borrar", id_hecho)
        return {"ok": True}

    # ---------- Rasgos (los propone el resumen semanal; nada se activa sin aprobar) ----------
    @app.get("/api/rasgos")
    def listar_rasgos(request: Request, estado: str | None = None):
        usuario = _usuario(request)
        if estado and estado not in memoria.ESTADOS_RASGO:
            raise HTTPException(422, "Estado desconocido.")
        return [_rasgo_json(r) for r in memoria.listar_rasgos(estado, perfil_id=_perfil_id(usuario))]

    def _decidir_rasgo(id_rasgo, estado, request):
        usuario = _usuario(request)
        _rasgo_de(usuario, id_rasgo)
        try:
            memoria.decidir_rasgo(id_rasgo, estado, por=usuario["nombre"])
        except ValueError as error:
            raise HTTPException(409, str(error))
        auth.auditar(usuario, f"rasgo-{estado}", id_rasgo)
        return _rasgo_json(memoria.obtener_rasgo(id_rasgo))

    @app.post("/api/rasgos/{id_rasgo}/aprobar")
    def aprobar_rasgo(id_rasgo: int, request: Request):
        return _decidir_rasgo(id_rasgo, "activo", request)

    @app.post("/api/rasgos/{id_rasgo}/retirar")
    def retirar_rasgo(id_rasgo: int, request: Request):
        return _decidir_rasgo(id_rasgo, "retirado", request)

    @app.delete("/api/rasgos/{id_rasgo}")
    def borrar_rasgo(id_rasgo: int, request: Request):
        usuario = _usuario(request)
        _rasgo_de(usuario, id_rasgo)
        memoria.borrar_rasgo(id_rasgo)
        auth.auditar(usuario, "rasgo-borrar", id_rasgo)
        return {"ok": True}

    # ---------- Agenda (recordatorios, alarmas, rutinas) ----------
    def _evento_normalizado(datos: EventoIn):
        """Fecha o días, nunca los dos: la fecha manda si el formulario la trae."""
        if datos.tipo not in ("recordatorio", "alarma", "rutina"):
            raise HTTPException(422, "Tipo inválido: usa recordatorio, alarma o rutina.")
        fecha = (datos.fecha or "").strip()
        dias = [] if fecha else sorted({int(d) for d in datos.dias if 0 <= int(d) <= 6})
        return {"tipo": datos.tipo, "titulo": datos.titulo, "hora": datos.hora,
                "fecha": fecha or None, "dias": dias or None, "activo": datos.activo}

    @app.get("/api/agenda")
    def leer_agenda(request: Request):
        usuario = _usuario(request)
        familia = usuario["familia_id"]
        agenda.asegurar_cumpleanos(familia)
        return {
            "eventos": agenda.listar_eventos(familia, incluir_inactivos=True),
            "ajustes": agenda.ajustes(familia),
            "avisos": agenda.listar_avisos(familia, limite=12),
            "ahora": persona.ahora_robot().isoformat(timespec="minutes"),
        }

    @app.post("/api/agenda", status_code=201)
    def crear_evento_agenda(datos: EventoIn, request: Request):
        usuario = _usuario(request)
        campos = _evento_normalizado(datos)
        try:
            evento = agenda.crear_evento(creado_por="padre", familia_id=usuario["familia_id"],
                                         **campos)
        except ValueError as error:
            raise HTTPException(422, str(error))
        auth.auditar(usuario, "agenda-crear", evento["id"])
        return evento

    @app.put("/api/agenda/ajustes")
    def guardar_ajustes_agenda(datos: AjustesIn, request: Request):
        usuario = _usuario(request)
        if datos.avisos_activos and not (datos.silencio_desde and datos.silencio_hasta):
            raise HTTPException(422, "Configura el horario de silencio antes de encender los avisos.")
        try:
            ajustes = agenda.guardar_ajustes(
                familia_id=usuario["familia_id"], avisos_activos=datos.avisos_activos,
                silencio_desde=datos.silencio_desde, silencio_hasta=datos.silencio_hasta,
                permitir_alarma_silencio=datos.permitir_alarma_silencio)
        except ValueError as error:
            raise HTTPException(422, str(error))
        auth.auditar(usuario, "agenda-ajustes")
        return ajustes

    @app.put("/api/agenda/{id_evento}")
    def editar_evento_agenda(id_evento: int, datos: EventoIn, request: Request):
        usuario = _usuario(request)
        _evento_de(usuario, id_evento)
        campos = _evento_normalizado(datos)
        try:
            evento = agenda.editar_evento(id_evento, familia_id=usuario["familia_id"],
                                           autor=None, **campos)
        except ValueError as error:
            raise HTTPException(422, str(error))
        if not evento:
            raise HTTPException(404, "Ese evento no existe.")
        auth.auditar(usuario, "agenda-editar", id_evento)
        return evento

    @app.patch("/api/agenda/{id_evento}/activo")
    def activar_evento_agenda(id_evento: int, datos: ActivoIn, request: Request):
        usuario = _usuario(request)
        _evento_de(usuario, id_evento)
        evento = agenda.activar_evento(id_evento, familia_id=usuario["familia_id"],
                                       activo=datos.activo, autor=None)
        if not evento:
            raise HTTPException(404, "Ese evento no existe.")
        auth.auditar(usuario, "agenda-activar" if datos.activo else "agenda-desactivar", id_evento)
        return evento

    @app.delete("/api/agenda/{id_evento}")
    def borrar_evento_agenda(id_evento: int, request: Request):
        usuario = _usuario(request)
        _evento_de(usuario, id_evento)
        agenda.borrar_evento(id_evento, familia_id=usuario["familia_id"], autor=None)
        auth.auditar(usuario, "agenda-borrar", id_evento)
        return {"ok": True}

    @app.post("/api/agenda/{id_evento}/probar")
    def probar_evento_agenda(id_evento: int, request: Request):
        """Crea un aviso inmediato (prueba=1): pasa aunque los avisos estén apagados o en silencio."""
        usuario = _usuario(request)
        _evento_de(usuario, id_evento)
        try:
            aviso = agenda.probar_evento(id_evento, familia_id=usuario["familia_id"])
        except ValueError as error:
            raise HTTPException(409, str(error))
        if not aviso:
            raise HTTPException(404, "Ese evento no existe.")
        auth.auditar(usuario, "agenda-probar", id_evento)
        return {"aviso": aviso, "mensaje": "El robot lo dirá en el próximo sondeo (20-30 s)."}

    @app.post("/api/agenda/{id_evento}/escuchar")
    def escuchar_evento_agenda(id_evento: int, request: Request):
        """Dice el texto en los parlantes de este PC (no pasa por el robot)."""
        usuario = _usuario(request)
        evento = _evento_de(usuario, id_evento)
        texto = agenda.texto_de_evento(evento)
        import puente                                   # import tardío: puente monta este panel
        puente.hablar(texto)
        auth.auditar(usuario, "agenda-escuchar", id_evento)
        return {"texto": texto}

    return app


def _con_cabeceras(respuesta):
    respuesta.headers["Content-Security-Policy"] = _CSP
    respuesta.headers["Cache-Control"] = "no-store"
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["X-Frame-Options"] = "DENY"
    respuesta.headers["Referrer-Policy"] = "no-referrer"
    respuesta.headers["Strict-Transport-Security"] = "max-age=31536000"
    return respuesta
