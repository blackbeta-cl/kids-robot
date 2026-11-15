"""Agenda local del robot: recordatorios, alarmas, rutinas, temporizadores y cumpleaños.

Todo vive en memoria.db (la misma base del perfil, la persona y los hechos) y lleva familia_id.
- `eventos`: la regla (hora, una fecha o días de la semana).
- `avisos`: una fila por ocurrencia concreta; UNIQUE(evento_id, programado) evita repetir.
- `ajustes_familia`: interruptor de avisos, silencio y permiso para alarmas en silencio.

El robot no calcula fechas: pregunta GET /pendientes y el puente llama a `debido()`.
Este módulo no habla ni sintetiza: solo guarda, calcula y devuelve texto y datos.

Decisiones (14-nov-2026):
- Hasta que los padres configuren los avisos, `avisos_activos` es 0 y no se entrega nada
  (el botón «Probar» sí funciona: sus avisos llevan prueba=1).
- Un aviso que espera más de VENTANA_ATRASO_MIN se marca omitido; no se acumulan avisos viejos.
- La hora se guarda en UTC y se calcula en la zona horaria del robot, ROBOT_TZ (el servidor suele estar en UTC).
"""
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from functools import wraps

import persona

TIPOS = ("recordatorio", "alarma", "rutina", "cumpleanos", "temporizador")
AUTORES = ("padre", "nino", "sistema")
MAX_TITULO = 120
MAX_TEXTO = 200
MAX_EVENTOS_ACTIVOS = 20
VENTANA_ATRASO_MIN = 5          # un aviso más viejo ya no se entrega
HORIZONTE_HORAS = 48            # se materializan las ocurrencias de las próximas 48 h
CAMBIO_HORARIO_DIAS = 400       # margen para la próxima ocurrencia (incluye 29 de febrero)

_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
          "octubre", "noviembre", "diciembre")

_lock = threading.RLock()
_inicializadas = set()


# ---------- Base de datos ----------

def _ruta():
    import memoria
    return memoria.ruta_db()


@contextmanager
def _conectar():
    con = _abrir()
    try:
        yield con
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()


def _abrir():
    ruta = _ruta()
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    con = sqlite3.connect(ruta, timeout=5)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=5000")
    con.execute("PRAGMA foreign_keys=ON")
    if ruta not in _inicializadas:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS eventos(
            id INTEGER PRIMARY KEY,
            familia_id TEXT NOT NULL DEFAULT '1',
            robot_id TEXT NOT NULL,
            tipo TEXT NOT NULL,
            titulo TEXT NOT NULL,
            texto_voz TEXT,
            hora TEXT,
            fecha TEXT,
            dias TEXT,
            activo INTEGER NOT NULL DEFAULT 1,
            creado_por TEXT NOT NULL,
            creado TEXT NOT NULL,
            actualizado TEXT);
        CREATE INDEX IF NOT EXISTS eventos_familia ON eventos(familia_id, activo);
        CREATE TABLE IF NOT EXISTS avisos(
            id INTEGER PRIMARY KEY,
            evento_id INTEGER NOT NULL REFERENCES eventos(id) ON DELETE CASCADE,
            programado TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'pendiente',
            intentos INTEGER NOT NULL DEFAULT 0,
            entregado TEXT, confirmado TEXT, motivo TEXT,
            prueba INTEGER NOT NULL DEFAULT 0,
            UNIQUE(evento_id, programado));
        CREATE INDEX IF NOT EXISTS avisos_pendientes ON avisos(estado, programado);
        CREATE TABLE IF NOT EXISTS ajustes_familia(
            familia_id TEXT PRIMARY KEY,
            avisos_activos INTEGER NOT NULL DEFAULT 0,
            silencio_desde TEXT,
            silencio_hasta TEXT,
            permitir_alarma_silencio INTEGER NOT NULL DEFAULT 0,
            silencio_temporal_hasta TEXT,
            actualizado TEXT);
        """)
        columnas = {f[1] for f in con.execute("PRAGMA table_info(avisos)")}
        if "prueba" not in columnas:          # migración aditiva de una base anterior
            con.execute("ALTER TABLE avisos ADD COLUMN prueba INTEGER NOT NULL DEFAULT 0")
        columnas_ajustes = {f[1] for f in con.execute("PRAGMA table_info(ajustes_familia)")}
        if "silencio_temporal_hasta" not in columnas_ajustes:
            con.execute("ALTER TABLE ajustes_familia ADD COLUMN silencio_temporal_hasta TEXT")
        con.commit()
        _inicializadas.add(ruta)
    return con


def _sincronizado(funcion):
    """Serializa las operaciones de escritura y la elección de avisos dentro de este proceso."""
    @wraps(funcion)
    def envoltura(*args, **kwargs):
        with _lock:
            return funcion(*args, **kwargs)
    return envoltura


# ---------- Hora ----------

def _local(ahora=None):
    zona = persona.zona_robot()
    if ahora is None:
        return datetime.now(zona)
    if ahora.tzinfo is None:
        return ahora.replace(tzinfo=zona)
    return ahora.astimezone(zona)


def _iso_utc(cuando):
    return cuando.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _a_local(iso):
    try:
        return datetime.fromisoformat(iso).astimezone(persona.zona_robot())
    except (TypeError, ValueError):
        return None


def _hora_objeto(evento):
    texto = (evento.get("hora") or "09:00").strip()
    hh, mm = texto.split(":")
    return time(int(hh), int(mm))


# ---------- Validación ----------

def _dias_lista(valor):
    if valor is None or valor == "":
        return []
    partes = valor.split(",") if isinstance(valor, str) else list(valor)
    salida = []
    for parte in partes:
        if isinstance(parte, str) and not parte.strip():
            continue
        try:
            numero = int(parte)
        except (TypeError, ValueError):
            raise ValueError("día de la semana inválido (0=lunes ... 6=domingo).")
        if not 0 <= numero <= 6:
            raise ValueError("día de la semana inválido (0=lunes ... 6=domingo).")
        if numero not in salida:
            salida.append(numero)
    return sorted(salida)


def _hora_valida(texto):
    texto = (texto or "").strip()
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", texto):
        raise ValueError("hora inválida: escribe HH:MM (por ejemplo 17:30).")
    return texto


def _fecha_valida(texto):
    try:
        return date.fromisoformat((texto or "").strip())
    except ValueError:
        raise ValueError("fecha inválida: escribe AAAA-MM-DD.")


def _perfil(familia_id="1"):
    """Perfil del niño de la familia; nunca lanza (si falla la base, cae al archivo de siempre)."""
    try:
        import memoria
        fila = memoria.leer_perfil(familia_id)
        if fila:
            return fila
        if str(familia_id) == "1":
            return persona.cargar_perfil()
    except Exception:
        pass
    return None


def _validar_evento(datos, familia_id="1", permitir_pasado=False):
    """Normaliza y valida un evento. Devuelve el diccionario listo para guardar."""
    tipo = (datos.get("tipo") or "").strip()
    if tipo not in TIPOS:
        raise ValueError(f"tipo inválido: usa uno de {', '.join(TIPOS)}.")

    titulo = (datos.get("titulo") or "").strip()
    if not titulo and tipo == "cumpleanos":
        titulo = "mi cumpleaños"
    if not 1 <= len(titulo) <= MAX_TITULO:
        raise ValueError(f"el título debe tener entre 1 y {MAX_TITULO} caracteres.")

    texto_voz = (datos.get("texto_voz") or "").strip()
    if len(texto_voz) > MAX_TEXTO:
        raise ValueError(f"el texto para decir no puede pasar de {MAX_TEXTO} caracteres.")

    hora = (datos.get("hora") or "").strip()
    if tipo == "cumpleanos":
        hora = _hora_valida(hora or "09:00")
    else:
        hora = _hora_valida(hora)

    dias = _dias_lista(datos.get("dias"))
    fecha = (datos.get("fecha") or "").strip()

    if tipo == "cumpleanos":
        if not fecha:
            nacimiento = (_perfil(familia_id) or {}).get("nacimiento") or ""
            if len(nacimiento) >= 10:
                fecha = nacimiento[5:10]
            else:
                raise ValueError("falta la fecha de nacimiento para el cumpleaños.")
        partes = fecha.split("-")
        if len(partes) == 3:                  # admite AAAA-MM-DD
            partes = partes[1:]
        elif len(partes) != 2:
            raise ValueError("el cumpleaños se guarda como MM-DD.")
        try:
            dia = date(2000, int(partes[0]), int(partes[1]))     # 2000: permite 29 de febrero
        except ValueError:
            raise ValueError("fecha de cumpleaños inválida.")
        fecha = f"{dia.month:02d}-{dia.day:02d}"
        dias = []
    else:
        if fecha and dias:
            raise ValueError("un evento lleva una fecha o días de la semana, no los dos.")
        if tipo == "temporizador" and not fecha:
            raise ValueError("un temporizador necesita fecha y hora.")
        if not fecha and not dias:
            raise ValueError("el evento necesita una fecha o días de la semana.")
        if fecha:
            fecha_obj = _fecha_valida(fecha)
            hoy = _local().date()
            if not permitir_pasado and fecha_obj < hoy:
                raise ValueError("la fecha ya pasó.")
            if fecha_obj > hoy + timedelta(days=366):
                raise ValueError("la fecha está demasiado lejos (máximo un año).")
            fecha = fecha_obj.isoformat()
        if tipo == "temporizador":
            dias = []

    return {
        "tipo": tipo,
        "titulo": titulo,
        "texto_voz": texto_voz,
        "hora": hora,
        "fecha": fecha or None,
        "dias": dias,
        "activo": bool(datos.get("activo", True)),
    }


def _fila_a_evento(fila):
    evento = dict(fila)
    evento["activo"] = bool(evento.get("activo", 0))
    evento["dias"] = _dias_lista(evento.get("dias"))
    return evento


def _evento_publico(evento, ahora=None):
    """Copia para el panel y la voz: añade la próxima ocurrencia en hora local."""
    ahora_l = _local(ahora)
    siguiente = None
    if evento["activo"]:
        ocurrencias = _ocurrencias(evento, ahora_l, ahora_l + timedelta(days=CAMBIO_HORARIO_DIAS))
        if ocurrencias:
            siguiente = ocurrencias[0].isoformat(timespec="minutes")
    return {
        "id": evento["id"],
        "tipo": evento["tipo"],
        "titulo": evento["titulo"],
        "texto_voz": evento["texto_voz"] or "",
        "hora": evento["hora"] or "",
        "fecha": evento["fecha"] or "",
        "dias": evento["dias"],
        "activo": evento["activo"],
        "creado_por": evento["creado_por"],
        "creado": evento["creado"],
        "actualizado": evento["actualizado"] or "",
        "siguiente": siguiente,
    }


# ---------- Ocurrencias y repetición ----------

def _ocurrencias(evento, desde, hasta):
    """Fechas/horas locales (aware) del evento entre `desde` y `hasta`, ambos aware."""
    if hasta <= desde:
        return []
    try:
        hora = _hora_objeto(evento)
    except (ValueError, TypeError):
        return []
    zona = persona.zona_robot()

    if evento.get("tipo") == "cumpleanos":
        partes = (evento.get("fecha") or "").split("-")
        if len(partes) != 2:
            return []
        try:
            mes, dia = int(partes[0]), int(partes[1])
        except ValueError:
            return []
        salida = []
        for anio in range(desde.year, hasta.year + 1):
            try:
                fecha = date(anio, mes, dia)
            except ValueError:
                continue                     # 29 de febrero en un año que no es bisiesto
            cuando = datetime.combine(fecha, hora, tzinfo=zona)
            if desde <= cuando <= hasta:
                salida.append(cuando)
        return salida

    if evento.get("fecha"):
        cuando = datetime.combine(_fecha_valida(evento["fecha"]), hora, tzinfo=zona)
        return [cuando] if desde <= cuando <= hasta else []

    dias = evento.get("dias") or []
    if not dias:
        return []
    salida = []
    dia_actual = desde.date()
    while dia_actual <= hasta.date():
        if dia_actual.weekday() in dias:
            cuando = datetime.combine(dia_actual, hora, tzinfo=zona)
            if desde <= cuando <= hasta:
                salida.append(cuando)
        dia_actual += timedelta(days=1)
    return salida


def _familias(familia_id=None):
    if familia_id is not None:
        return [str(familia_id)]
    ids = set()
    with _conectar() as con:
        for tabla in ("eventos", "perfiles"):
            try:
                ids |= {str(f[0]) for f in con.execute(f"SELECT DISTINCT familia_id FROM {tabla}")}
            except sqlite3.OperationalError:
                pass                          # la tabla perfiles la crea memoria.py
    return sorted(ids) or ["1"]


@_sincronizado
def asegurar_cumpleanos(familia_id="1", ahora=None):
    """Crea o actualiza el evento automático de cumpleaños a partir del perfil. No duplica uno manual."""
    perfil = _perfil(familia_id) or {}
    nacimiento = (perfil.get("nacimiento") or "").strip()
    ahora_iso = _iso_utc(_local(ahora))
    with _conectar() as con:
        fila = con.execute(
            "SELECT * FROM eventos WHERE familia_id=? AND tipo='cumpleanos' ORDER BY id LIMIT 1",
            (str(familia_id),)).fetchone()
        if not nacimiento:
            if fila and fila["creado_por"] == "sistema":
                con.execute("UPDATE eventos SET activo=0, actualizado=? WHERE id=?", (ahora_iso, fila["id"]))
            return fila["id"] if fila else None
        try:
            fecha_nacimiento = date.fromisoformat(nacimiento)
        except ValueError:
            return fila["id"] if fila else None
        mmdd = f"{fecha_nacimiento.month:02d}-{fecha_nacimiento.day:02d}"
        if fila:
            if fila["creado_por"] == "sistema" and (fila["fecha"] != mmdd or not fila["activo"]):
                con.execute("UPDATE eventos SET fecha=?, activo=1, actualizado=? WHERE id=?",
                            (mmdd, ahora_iso, fila["id"]))
            return fila["id"]
        cursor = con.execute(
            "INSERT INTO eventos(familia_id, robot_id, tipo, titulo, texto_voz, hora, fecha, dias, activo, "
            "creado_por, creado, actualizado) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(familia_id), persona.ROBOT_ID, "cumpleanos", "mi cumpleaños", "", "09:00", mmdd, None,
             1, "sistema", ahora_iso, ahora_iso))
        return cursor.lastrowid


@_sincronizado
def materializar(ahora=None, horizonte_horas=HORIZONTE_HORAS, familia_id=None):
    """Crea los avisos de las próximas ocurrencias y marca los atrasados. Devuelve cuántos creó."""
    ahora_l = _local(ahora)
    hasta = ahora_l + timedelta(hours=horizonte_horas)
    familias = _familias(familia_id)
    for familia in familias:
        asegurar_cumpleanos(familia, ahora=ahora_l)

    creados = 0
    with _conectar() as con:
        for familia in familias:
            filas = con.execute(
                "SELECT * FROM eventos WHERE familia_id=? AND activo=1", (str(familia),)).fetchall()
            for fila in filas:
                evento = _fila_a_evento(fila)
                for cuando in _ocurrencias(evento, ahora_l, hasta):
                    cursor = con.execute(
                        "INSERT OR IGNORE INTO avisos(evento_id, programado) VALUES (?,?)",
                        (evento["id"], _iso_utc(cuando)))
                    creados += cursor.rowcount
        limite = _iso_utc(ahora_l - timedelta(minutes=VENTANA_ATRASO_MIN))
        con.execute(
            "UPDATE avisos SET estado='omitido', motivo='atrasado' "
            "WHERE estado='pendiente' AND programado < ? AND prueba=0", (limite,))
    return creados


# ---------- Alta, edición y borrado ----------

@_sincronizado
def crear_evento(tipo, titulo, hora=None, fecha=None, dias=None, texto_voz="", creado_por="padre",
                 familia_id="1", robot_id=None, activo=True):
    if creado_por not in AUTORES:
        raise ValueError("autor inválido.")
    datos = _validar_evento({"tipo": tipo, "titulo": titulo, "hora": hora, "fecha": fecha, "dias": dias,
                             "texto_voz": texto_voz, "activo": activo}, familia_id)
    if datos["activo"]:
        activos = len(listar_eventos(familia_id, incluir_inactivos=False))
        if activos >= MAX_EVENTOS_ACTIVOS:
            raise ValueError(f"ya hay {MAX_EVENTOS_ACTIVOS} eventos activos; borra o desactiva uno.")

    ahora = _iso_utc(_local())
    with _conectar() as con:
        cursor = con.execute(
            "INSERT INTO eventos(familia_id, robot_id, tipo, titulo, texto_voz, hora, fecha, dias, activo, "
            "creado_por, creado, actualizado) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(familia_id), robot_id or persona.ROBOT_ID, datos["tipo"], datos["titulo"],
             datos["texto_voz"], datos["hora"], datos["fecha"],
             ",".join(map(str, datos["dias"])) or None, int(datos["activo"]),
             creado_por, ahora, ahora))
        id_evento = cursor.lastrowid
    return _evento_publico(obtener_evento(id_evento, familia_id))


def _puede_modificar(evento, autor):
    return autor in (None, "padre", "sistema") or evento["creado_por"] == "nino"


@_sincronizado
def editar_evento(id_evento, familia_id="1", autor=None, ahora=None, **cambios):
    actual = obtener_evento(id_evento, familia_id)
    if not actual:
        return None
    if not _puede_modificar(actual, autor):
        raise PermissionError("el niño no puede editar lo que crearon los padres.")
    datos = {clave: actual[clave] for clave in ("tipo", "titulo", "texto_voz", "hora", "fecha", "dias", "activo")}
    datos.update({clave: valor for clave, valor in cambios.items() if clave in datos})
    datos = _validar_evento(datos, familia_id, permitir_pasado=True)

    ahora_l = _local(ahora)
    with _conectar() as con:
        con.execute(
            "UPDATE eventos SET tipo=?, titulo=?, texto_voz=?, hora=?, fecha=?, dias=?, activo=?, actualizado=? "
            "WHERE id=? AND familia_id=?",
            (datos["tipo"], datos["titulo"], datos["texto_voz"], datos["hora"], datos["fecha"],
             ",".join(map(str, datos["dias"])) or None, int(datos["activo"]),
             _iso_utc(ahora_l), id_evento, str(familia_id)))
        con.execute(
            "DELETE FROM avisos WHERE evento_id=? AND estado='pendiente' AND prueba=0 AND programado >= ?",
            (id_evento, _iso_utc(ahora_l)))
    return _evento_publico(obtener_evento(id_evento, familia_id))


@_sincronizado
def activar_evento(id_evento, familia_id="1", activo=True, autor=None, ahora=None):
    actual = obtener_evento(id_evento, familia_id)
    if not actual:
        return None
    if not _puede_modificar(actual, autor):
        raise PermissionError("el niño no puede cambiar lo que crearon los padres.")
    ahora_l = _local(ahora)
    with _conectar() as con:
        con.execute("UPDATE eventos SET activo=?, actualizado=? WHERE id=? AND familia_id=?",
                    (int(bool(activo)), _iso_utc(ahora_l), id_evento, str(familia_id)))
        if not activo:
            con.execute("DELETE FROM avisos WHERE evento_id=? AND estado='pendiente'", (id_evento,))
    return _evento_publico(obtener_evento(id_evento, familia_id))


@_sincronizado
def borrar_evento(id_evento, familia_id="1", autor=None):
    actual = obtener_evento(id_evento, familia_id)
    if not actual:
        return 0
    if not _puede_modificar(actual, autor):
        raise PermissionError("el niño no puede borrar lo que crearon los padres.")
    with _conectar() as con:
        con.execute("DELETE FROM avisos WHERE evento_id=?", (id_evento,))
        return con.execute("DELETE FROM eventos WHERE id=? AND familia_id=?",
                           (id_evento, str(familia_id))).rowcount


def obtener_evento(id_evento, familia_id=None):
    with _conectar() as con:
        fila = con.execute("SELECT * FROM eventos WHERE id=?", (id_evento,)).fetchone()
    if not fila:
        return None
    evento = _fila_a_evento(fila)
    if familia_id is not None and evento["familia_id"] != str(familia_id):
        return None
    return evento


def listar_eventos(familia_id="1", incluir_inactivos=False, ahora=None):
    consulta = "SELECT * FROM eventos WHERE familia_id=?"
    if not incluir_inactivos:
        consulta += " AND activo=1"
    consulta += " ORDER BY activo DESC, hora, id"
    with _conectar() as con:
        filas = con.execute(consulta, (str(familia_id),)).fetchall()
    return [_evento_publico(_fila_a_evento(fila), ahora) for fila in filas]


def crear_temporizador(minutos, familia_id="1", creado_por="nino", ahora=None, robot_id=None):
    """Temporizador de 1 a 180 minutos. Se guarda como evento de una vez."""
    try:
        minutos = int(minutos)
    except (TypeError, ValueError):
        raise ValueError("los minutos deben ser un número.")
    if not 1 <= minutos <= 180:
        raise ValueError("el temporizador debe durar entre 1 y 180 minutos.")
    cuando = _local(ahora) + timedelta(minutes=minutos)
    return crear_evento("temporizador", f"{minutos} minutos", hora=f"{cuando:%H:%M}",
                        fecha=cuando.date().isoformat(), texto_voz="¡Se acabó el tiempo!",
                        creado_por=creado_por, familia_id=familia_id, robot_id=robot_id)


# ---------- Ajustes (silencio y avisos) ----------

def ajustes(familia_id="1"):
    with _conectar() as con:
        fila = con.execute("SELECT * FROM ajustes_familia WHERE familia_id=?",
                           (str(familia_id),)).fetchone()
    if not fila:
        return {"familia_id": str(familia_id), "avisos_activos": False, "silencio_desde": "",
                "silencio_hasta": "", "permitir_alarma_silencio": False,
                "silencio_temporal_hasta": ""}
    temporal = _a_local(fila["silencio_temporal_hasta"]) if fila["silencio_temporal_hasta"] else None
    return {
        "familia_id": fila["familia_id"],
        "avisos_activos": bool(fila["avisos_activos"]),
        "silencio_desde": fila["silencio_desde"] or "",
        "silencio_hasta": fila["silencio_hasta"] or "",
        "permitir_alarma_silencio": bool(fila["permitir_alarma_silencio"]),
        "silencio_temporal_hasta": temporal.isoformat(timespec="minutes") if temporal else "",
    }


@_sincronizado
def guardar_ajustes(familia_id="1", avisos_activos=False, silencio_desde="", silencio_hasta="",
                    permitir_alarma_silencio=False, ahora=None):
    desde = (silencio_desde or "").strip()
    hasta = (silencio_hasta or "").strip()
    if bool(desde) != bool(hasta):
        raise ValueError("el silencio necesita hora de inicio y de fin (o ninguna).")
    if desde:
        desde = _hora_valida(desde)
        hasta = _hora_valida(hasta)
    with _conectar() as con:
        con.execute(
            "INSERT INTO ajustes_familia(familia_id, avisos_activos, silencio_desde, silencio_hasta, "
            "permitir_alarma_silencio, actualizado) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(familia_id) DO UPDATE SET avisos_activos=excluded.avisos_activos, "
            "silencio_desde=excluded.silencio_desde, silencio_hasta=excluded.silencio_hasta, "
            "permitir_alarma_silencio=excluded.permitir_alarma_silencio, actualizado=excluded.actualizado",
            (str(familia_id), int(bool(avisos_activos)), desde or None, hasta or None,
             int(bool(permitir_alarma_silencio)), _iso_utc(_local(ahora))))
    return ajustes(familia_id)


@_sincronizado
def silenciar(minutos=30, familia_id="1", ahora=None):
    """Cállate por un rato: silencia los avisos proactivos, no las alarmas ni el botón de prueba."""
    try:
        minutos = int(minutos)
    except (TypeError, ValueError):
        raise ValueError("los minutos deben ser un número.")
    if not 1 <= minutos <= 1440:
        raise ValueError("el silencio debe durar entre 1 minuto y 24 horas.")
    hasta = _local(ahora) + timedelta(minutes=minutos)
    with _conectar() as con:
        con.execute(
            "INSERT INTO ajustes_familia(familia_id, silencio_temporal_hasta, actualizado) VALUES (?,?,?) "
            "ON CONFLICT(familia_id) DO UPDATE SET silencio_temporal_hasta=excluded.silencio_temporal_hasta, "
            "actualizado=excluded.actualizado",
            (str(familia_id), _iso_utc(hasta), _iso_utc(_local(ahora))))
    return hasta


@_sincronizado
def reactivar(familia_id="1", ahora=None):
    """Vuelve a avisar ahora mismo (quita el silencio temporal; no toca el horario de los padres)."""
    with _conectar() as con:
        con.execute(
            "INSERT INTO ajustes_familia(familia_id, silencio_temporal_hasta, actualizado) VALUES (?,NULL,?) "
            "ON CONFLICT(familia_id) DO UPDATE SET silencio_temporal_hasta=NULL, actualizado=excluded.actualizado",
            (str(familia_id), _iso_utc(_local(ahora))))
    return ajustes(familia_id)


def _silencio_temporal(ahora_local, configuracion):
    texto = configuracion.get("silencio_temporal_hasta") or ""
    if not texto:
        return False
    try:
        hasta = datetime.fromisoformat(texto)
        if hasta.tzinfo is None:              # ajustes() lo devuelve en hora local del robot
            hasta = hasta.replace(tzinfo=persona.zona_robot())
        return ahora_local < hasta.astimezone(persona.zona_robot())
    except (TypeError, ValueError):
        return False


def _silencio(ahora_local, configuracion):
    desde, hasta = configuracion.get("silencio_desde"), configuracion.get("silencio_hasta")
    if not desde or not hasta:
        return False
    inicio = time.fromisoformat(desde)
    fin = time.fromisoformat(hasta)
    actual = ahora_local.time()
    if inicio <= fin:
        return inicio <= actual < fin
    return actual >= inicio or actual < fin


def en_silencio(familia_id="1", ahora=None):
    ahora_l = _local(ahora)
    configuracion = ajustes(familia_id)
    return _silencio(ahora_l, configuracion) or _silencio_temporal(ahora_l, configuracion)


# ---------- Entrega ----------

@_sincronizado
def debido(familia_id="1", robot_id=None, ahora=None):
    """El próximo aviso que el robot debe decir, o None. No lo marca como dicho: eso lo hace `confirmar`."""
    robot_id = robot_id or persona.ROBOT_ID
    ahora_l = _local(ahora)
    configuracion = ajustes(familia_id)
    silencio = _silencio(ahora_l, configuracion)
    silencio_temporal = _silencio_temporal(ahora_l, configuracion)

    with _conectar() as con:
        limite = _iso_utc(ahora_l - timedelta(minutes=VENTANA_ATRASO_MIN))
        con.execute("UPDATE avisos SET estado='omitido', motivo='atrasado' "
                    "WHERE estado='pendiente' AND programado < ? AND prueba=0", (limite,))

        # Un aviso por minuto como máximo, aunque el robot pregunte más seguido.
        fila = con.execute(
            "SELECT MAX(a.entregado) FROM avisos a JOIN eventos e ON e.id=a.evento_id "
            "WHERE e.familia_id=? AND e.robot_id=?", (str(familia_id), robot_id)).fetchone()
        ultimo = fila[0] if fila else None
        if ultimo and ultimo > _iso_utc(ahora_l - timedelta(minutes=1)):
            return None

        consulta = ("SELECT a.id AS aviso_id, a.programado, a.prueba, e.* "
                    "FROM avisos a JOIN eventos e ON e.id=a.evento_id "
                    "WHERE e.familia_id=? AND e.robot_id=? AND e.activo=1 AND a.estado='pendiente' "
                    "AND a.programado <= ?")
        if not configuracion["avisos_activos"]:
            consulta += " AND a.prueba=1"
        consulta += " ORDER BY a.programado LIMIT 10"
        filas = con.execute(consulta, (str(familia_id), robot_id, _iso_utc(ahora_l))).fetchall()
        if not filas:
            return None

        perfil = _perfil(familia_id)
        elegido = None
        for fila in filas:
            evento = _fila_a_evento(fila)
            es_prueba = bool(fila["prueba"])
            if silencio_temporal and not es_prueba and evento["tipo"] != "alarma":
                continue                  # «cállate»: las alarmas siguen pasando
            if silencio and not silencio_temporal and not es_prueba:
                if not (evento["tipo"] == "alarma" and configuracion["permitir_alarma_silencio"]):
                    continue
            elegido = (fila, evento, es_prueba)
            break
        if elegido is None:
            return None

        fila, evento, es_prueba = elegido
        con.execute("UPDATE avisos SET entregado=?, intentos=intentos+1 WHERE id=?",
                    (_iso_utc(ahora_l), fila["aviso_id"]))
        cuando = _a_local(fila["programado"]) or ahora_l
        publico = _evento_publico(evento, ahora_l)
        return {
            "id": fila["aviso_id"],
            "evento_id": evento["id"],
            "tipo": evento["tipo"],
            "titulo": evento["titulo"],
            "texto": texto_de_evento(evento, cuando, perfil),
            "emocion": "feliz" if evento["tipo"] == "cumpleanos" else "neutral",
            "cuello": None,
            "programado": fila["programado"],
            "programado_local": cuando.isoformat(timespec="minutes"),
            "prueba": es_prueba,
            "evento": publico,
        }


@_sincronizado
def confirmar(id_aviso, resultado="dicho", familia_id="1", motivo="", ahora=None):
    """Marca el aviso como dicho u omitido. Idempotente: repetirlo no cambia nada."""
    if resultado not in ("dicho", "omitido"):
        raise ValueError("resultado inválido: usa 'dicho' u 'omitido'.")
    with _conectar() as con:
        fila = con.execute(
            "SELECT a.estado FROM avisos a JOIN eventos e ON e.id=a.evento_id "
            "WHERE a.id=? AND e.familia_id=?", (id_aviso, str(familia_id))).fetchone()
        if not fila:
            return None
        if fila["estado"] == "pendiente":
            con.execute("UPDATE avisos SET estado=?, confirmado=?, motivo=? WHERE id=?",
                        (resultado, _iso_utc(_local(ahora)), (motivo or "")[:200], id_aviso))
        return fila["estado"] if fila["estado"] != "pendiente" else resultado


@_sincronizado
def probar_evento(id_evento, familia_id="1", ahora=None):
    """Crea una ocurrencia inmediata (prueba=1): se entrega aunque los avisos estén apagados o en silencio."""
    evento = obtener_evento(id_evento, familia_id)
    if not evento:
        return None
    if not evento["activo"]:
        raise ValueError("el evento está desactivado.")
    cuando = _iso_utc(_local(ahora))
    with _conectar() as con:
        con.execute("INSERT OR IGNORE INTO avisos(evento_id, programado, prueba) VALUES (?,?,1)",
                    (id_evento, cuando))
        fila = con.execute("SELECT id FROM avisos WHERE evento_id=? AND programado=?",
                           (id_evento, cuando)).fetchone()
    return fila["id"] if fila else None


def listar_avisos(familia_id="1", limite=20):
    """Historial corto para el panel: últimos avisos con su estado."""
    with _conectar() as con:
        filas = con.execute(
            "SELECT a.id, a.programado, a.estado, a.intentos, a.entregado, a.confirmado, a.motivo, a.prueba, "
            "e.tipo, e.titulo FROM avisos a JOIN eventos e ON e.id=a.evento_id "
            "WHERE e.familia_id=? ORDER BY a.programado DESC LIMIT ?",
            (str(familia_id), int(limite))).fetchall()
    salida = []
    for fila in filas:
        programado = _a_local(fila["programado"])
        entregado = _a_local(fila["entregado"]) if fila["entregado"] else None
        confirmado = _a_local(fila["confirmado"]) if fila["confirmado"] else None
        salida.append({
            "id": fila["id"],
            "tipo": fila["tipo"],
            "titulo": fila["titulo"],
            "estado": fila["estado"],
            "intentos": fila["intentos"],
            "prueba": bool(fila["prueba"]),
            "programado": programado.isoformat(timespec="minutes") if programado else "",
            "entregado": entregado.isoformat(timespec="minutes") if entregado else "",
            "confirmado": confirmado.isoformat(timespec="minutes") if confirmado else "",
            "motivo": fila["motivo"] or "",
        })
    return salida


# ---------- Texto para la voz ----------

def texto_de_evento(evento, cuando=None, perfil=None):
    """Lo que dice el robot al entregar el aviso. Usa texto_voz si lo hay; si no, una plantilla fija."""
    texto = (evento.get("texto_voz") or "").strip()
    if texto:
        return texto
    titulo = (evento.get("titulo") or "").strip()
    tipo = evento.get("tipo")
    if tipo == "cumpleanos":
        perfil = perfil or {}
        apodo = (perfil.get("apodo") or "").strip()
        edad = persona.edad_de(perfil.get("nacimiento"), (cuando or _local()).date())
        saludo = f"¡Feliz cumpleaños, {apodo}!" if apodo else "¡Feliz cumpleaños!"
        return f"{saludo} Hoy cumples {edad} años." if edad else saludo
    if tipo == "alarma":
        return f"¡Alarma! {titulo}."
    if tipo == "rutina":
        return f"Es hora de {titulo}."
    if tipo == "temporizador":
        return "¡Se acabó el tiempo!"
    return f"Recuerda: {titulo}."


def _fecha_larga(dia):
    return f"{_DIAS[dia.weekday()]} {dia.day} de {_MESES[dia.month - 1]}"


def fecha_larga(dia):
    """«sábado 14 de noviembre», para respuestas y panel."""
    return _fecha_larga(dia)


# ---------- Consultas por voz ----------

def ocurrencias_entre(familia_id="1", desde=None, hasta=None, ahora=None):
    """Ocurrencias activas entre dos instantes locales. Devuelve [{evento, cuando}] ordenado."""
    ahora_l = _local(ahora)
    desde = desde or ahora_l.replace(hour=0, minute=0, second=0, microsecond=0)
    hasta = hasta or (desde + timedelta(days=1))
    asegurar_cumpleanos(familia_id, ahora=ahora_l)
    salida = []
    with _conectar() as con:
        filas = con.execute("SELECT * FROM eventos WHERE familia_id=? AND activo=1",
                            (str(familia_id),)).fetchall()
    for fila in filas:
        evento = _fila_a_evento(fila)
        for cuando in _ocurrencias(evento, desde, hasta):
            salida.append({"evento": _evento_publico(evento, ahora_l), "cuando": cuando})
    salida.sort(key=lambda item: item["cuando"])
    return salida


def _frase_de_item(item):
    evento = item["evento"]
    cuando = item["cuando"]
    if evento["tipo"] == "cumpleanos":
        return f"a las {cuando:%H:%M} tu cumpleaños"
    return f"a las {cuando:%H:%M} {evento['titulo']}"


def describir_dia(familia_id="1", dia="hoy", ahora=None):
    """«Hoy tienes dos cosas: a las 17:00 hacer la tarea y a las 20:30 lavarte los dientes.»"""
    ahora_l = _local(ahora)
    if dia == "hoy":
        fecha = ahora_l.date()
        etiqueta = "Hoy"
    elif dia in ("manana", "mañana"):
        fecha = ahora_l.date() + timedelta(days=1)
        etiqueta = "Mañana"
    else:
        fecha = date.fromisoformat(dia)
        etiqueta = f"El {_fecha_larga(fecha)}"
    inicio = datetime.combine(fecha, time(0, 0), tzinfo=persona.zona_robot())
    fin = inicio + timedelta(days=1)
    items = ocurrencias_entre(familia_id, inicio, fin, ahora=ahora_l)
    if not items:
        return f"{etiqueta} no tienes nada programado."
    frases = [_frase_de_item(item) for item in items]
    if len(frases) == 1:
        return f"{etiqueta} tienes una cosa: {frases[0]}."
    if len(frases) == 2:
        return f"{etiqueta} tienes dos cosas: {frases[0]} y {frases[1]}."
    return f"{etiqueta} tienes {len(frases)} cosas: {', '.join(frases[:-1])} y {frases[-1]}."


def describir_proximos(familia_id="1", dias=7, ahora=None, maximo=6):
    """Resumen de los próximos días para «¿qué tengo esta semana?»."""
    ahora_l = _local(ahora)
    items = ocurrencias_entre(familia_id, ahora_l, ahora_l + timedelta(days=dias), ahora=ahora_l)
    if not items:
        return "No tienes nada programado en los próximos días."
    partes = []
    for item in items[:maximo]:
        fecha = item["cuando"].date()
        etiqueta = "hoy" if fecha == ahora_l.date() else (
            "mañana" if fecha == ahora_l.date() + timedelta(days=1) else f"el {_DIAS[fecha.weekday()]}")
        partes.append(f"{etiqueta} a las {item['cuando']:%H:%M} {item['evento']['titulo']}")
    texto = "Tienes: " + "; ".join(partes)
    if len(items) > maximo:
        texto += f"; y {len(items) - maximo} más"
    return texto + "."


def proximo_cumple(familia_id="1", ahora=None):
    """{'fecha': date, 'dias': n, 'edad': años que cumple} o None si no hay fecha de nacimiento."""
    perfil = _perfil(familia_id) or {}
    try:
        nacimiento = date.fromisoformat((perfil.get("nacimiento") or "").strip())
    except ValueError:
        return None
    hoy = _local(ahora).date()
    for anio in range(hoy.year, hoy.year + 9):        # 9 años cubre el 29 de febrero
        try:
            fecha = date(anio, nacimiento.month, nacimiento.day)
        except ValueError:
            continue
        if fecha >= hoy:
            return {"fecha": fecha, "dias": (fecha - hoy).days, "edad": anio - nacimiento.year}
    return None


def describir_cumple(familia_id="1", ahora=None):
    datos = proximo_cumple(familia_id, ahora)
    if not datos:
        return "Todavía no sé la fecha de tu cumpleaños."
    if datos["dias"] == 0:
        return f"¡Hoy es tu cumpleaños! Cumples {datos['edad']} años."
    if datos["dias"] == 1:
        return f"Falta 1 día para tu cumpleaños: cumples {datos['edad']} años."
    return f"Faltan {datos['dias']} días para tu cumpleaños: cumples {datos['edad']} años."
