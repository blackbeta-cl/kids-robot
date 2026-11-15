"""Intenciones de agenda por voz, sin modelo.

Convierte una frase en una acción local: crear recordatorio/alarma/temporizador,
consultar, cancelar, silenciar, pedir la hora o el cumpleaños.

Reglas:
- No habla con el modelo ni inventa nada.
- Si falta la hora o el título, guarda una intención pendiente por 60 s y pregunta.
- Entiende la hora en español y resuelve la ambigüedad de 12 h: 8–12 tal cual,
  1–7 de la tarde salvo que diga «de la mañana».
- Si la hora ya pasó hoy, programa para mañana y lo dice.
- El niño crea con `creado_por='nino'`; el permiso lo aplica `agenda.py`.

La entrada puede venir con tildes y mayúsculas: aquí se normaliza.
"""
import re
import threading
import unicodedata
from datetime import date, datetime, time, timedelta

import agenda
import persona

VENCE_PENDIENTE = 60          # segundos para completar una frase a medias
MAX_CREACIONES_MINUTO = 3
MAX_TITULO = agenda.MAX_TITULO

_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábados", "domingos")
_DIAS_SEMANA = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3,
                "viernes": 4, "sabado": 5, "domingo": 6}
_DIAS_ALT = "lunes|martes|miercoles|jueves|viernes|sabado|domingo"
_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre")
_MESES_NUM = {nombre: numero for numero, nombre in enumerate(_MESES, start=1)}
_MES_ALT = "|".join(_MESES)

_NUM = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
    "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17,
    "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiuno": 21,
    "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25,
    "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
    "treinta": 30, "cuarenta": 40, "cincuenta": 50,
}
_NUM_ALT = "|".join(sorted(_NUM, key=len, reverse=True))
_PERIODOS = "manana|tarde|noche|madrugada"

_TIEMPO_ABS = re.compile(
    r"\b(?:a\s+las?)\s+(" + _NUM_ALT + r"|\d{1,2})"
    r"(?:\s*:\s*(\d{2}))?"
    r"(?:\s+(y|menos)\s+(media|cuarto|" + _NUM_ALT + r"|\d{1,2}))?"
    r"(?:\s+de\s+la\s+(" + _PERIODOS + r"))?\b"
)
_TIEMPO_RELOJ = re.compile(
    r"\b(\d{1,2})\s*:\s*(\d{2})(?:\s+de\s+la\s+(" + _PERIODOS + r"))?"
)
_TIEMPO_PALABRA = re.compile(r"\b(?:(?:a\s+las?|al|a)\s+)?(mediodia|medianoche)\b")
_TIEMPO_SUELTO = re.compile(
    r"\b(\d{1,2})\s+y\s+(media|cuarto)\b(?:\s+de\s+la\s+(" + _PERIODOS + r"))?"
)
_RELATIVO = re.compile(
    r"\ben\s+(\d{1,3}|" + _NUM_ALT + r"|media|medio)\s*"
    r"(minutos?|min|horas?|h)\b(?:\s+y\s+media\b)?"
)
_RELATIVO_HORA_MEDIA = re.compile(r"\ben\s+hora\s+y\s+media\b")
_DURACION = re.compile(
    r"\b(?:por\s+)?(\d{1,3}|" + _NUM_ALT + r"|media|medio|hora\s+y\s+media)\s*"
    r"(minutos?|min|horas?|h)\b"
)
_PON_MINUTOS = re.compile(
    r"\b(?:pon|ponme|programa|inicia)\s+(\d{1,3}|" + _NUM_ALT + r"|media)\s*"
    r"(minutos?|min|horas?|h)\b"
)
_TEMPORIZADOR = re.compile(r"\b(?:temporizador|timer|contador)\b")
_ALARMA = re.compile(r"\b(?:alarma|despiertame|despertarme|despertador)\b")
_RECORDAR = re.compile(
    r"\b(?:recuerdame|recuerdeme|recordarme|acuerdate|avisame|aviseme|anotame|apuntame|agendame)\b"
)

_QUERY_DIA = re.compile(
    r"\b(?:que\s+(?:tengo|hay|me\s+toca|hago)|tengo\s+algo|mi\s+agenda|"
    r"como\s+(?:esta|viene)\s+mi\s+(?:dia|agenda)|que\s+tengo\s+que\s+hacer)\b"
)
_QUERY_SEMANA = re.compile(r"\b(?:esta\s+semana|proximos?\s+dias?|la\s+semana)\b")
_QUERY_EVENTO = re.compile(
    r"\b(?:a\s+que\s+hora\s+(?:es|son|tengo|hay|me\s+toca)|"
    r"cuando\s+(?:es|son|tengo|hay|me\s+toca))\b"
)
_QUERY_HORA = re.compile(
    r"\b(?:que\s+hora\s+es|me\s+dices\s+la\s+hora|dime\s+la\s+hora|"
    r"que\s+hora\s+son|la\s+hora\s+por\s+favor)\b"
)
_QUERY_FECHA = re.compile(
    r"\b(?:que\s+dia\s+es(?:\s+hoy)?|que\s+fecha\s+es(?:\s+hoy)?|a\s+que\s+dia\s+estamos)\b"
)
_CUMPLE = re.compile(
    r"\b(?:cuanto\s+(?:falta|queda)\s+(?:para|pa)\s+(?:mi|el)\s+cumpleanos|"
    r"cuando\s+es\s+(?:mi|el)\s+cumpleanos|mi\s+cumpleanos)\b"
)
_SILENCIO = re.compile(
    r"\b(?:callate|callense|no\s+molestes|no\s+me\s+molestes|no\s+molestar|"
    r"deja\s+de\s+molestar|haz\s+silencio|modo\s+silencio|silencio\s+por)\b"
)
_REACTIVAR = re.compile(
    r"\b(?:vuelve\s+a\s+hablar|puedes\s+hablar|ya\s+puedes\s+hablar|"
    r"reactiva\s+(?:los\s+)?avisos|vuelve\s+a\s+avisar)\b"
)
_RUTINA_HECHA = re.compile(
    r"\b(?:ya\s+lo\s+hice|ya\s+hice|ya\s+termine|ya\s+acabe|lo\s+termine|"
    r"termine\s+la\s+tarea|tarea\s+hecha)\b"
)
_AYUDA = re.compile(r"\b(?:que\s+sabes\s+hacer|que\s+puedes\s+hacer|para\s+que\s+sirves|ayuda)\b")
_CANCELAR = re.compile(r"\b(?:cancela|cancelar|borra|borrar|elimina|eliminar|quita|quitar|suspende)\b")
_CANCELAR_MEMORIA = re.compile(r"\b(?:memoria|conversacion|todo\s+lo\s+que\s+sabes)\b")
_OLVIDAR = re.compile(r"\b(?:olvidalo|olvidalo\s+todo|olvida\s+eso|cancela\s+eso|dejalo)\b")

_TRIGGER_RECORDAR = re.compile(
    r"\b(?:recuerdame|recuerdeme|recordarme|acuerdate|avisame|aviseme|anotame|apuntame|agendame)"
    r"(?:\s+que\b)?"
)
_TRIGGER_ALARMA = re.compile(
    r"\b(?:(?:ponme|pon|programa|crea|coloca|quiero|necesito)\s+(?:una\s+)?alarma|"
    r"despiertame|despertarme|despertador)\b"
)
_TRIGGER_RECORDATORIO = re.compile(
    r"\b(?:(?:ponme|pon|crea|programa)\s+(?:un\s+)?recordatorio(?:\s+de)?)\b"
)
_TRIGGER_TEMPORIZADOR = re.compile(
    r"\b(?:(?:ponme|pon|programa|inicia|crea)\s+(?:un\s+)?(?:temporizador|timer|contador)"
    r"(?:\s+de)?)\b"
)
_TRIGGER_PON_MINUTOS = re.compile(
    r"\b(?:pon|ponme|programa|inicia)\s+(?:\d{1,3}|" + _NUM_ALT + r"|media)\s*"
    r"(?:minutos?|min|horas?|h)\b"
)

_STOP = {
    "de", "del", "la", "las", "el", "los", "un", "una", "unos", "unas", "mi", "mis",
    "tu", "tus", "que", "y", "a", "al", "en", "por", "para", "con", "me", "te", "se",
    "lo", "es", "son", "hoy", "manana", "ya", "favor", "porfa", "dime", "quiero",
    "necesito", "pon", "ponme", "hay", "tengo", "hora", "cuando", "como", "esta",
}

_PENDIENTES = {}
_CREACIONES = {}
_lock = threading.RLock()


def normalizar(texto):
    """Minúsculas y sin tildes, igual que `asistente_voz.normalizar`."""
    plano = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in plano if unicodedata.category(c) != "Mn")


def limpiar():
    """Vacía el estado en memoria (pruebas o reinicio del proceso)."""
    with _lock:
        _PENDIENTES.clear()
        _CREACIONES.clear()


# ---------- Hora ----------

def _local(ahora=None):
    zona = persona.zona_robot()
    if ahora is None:
        return datetime.now(zona)
    if ahora.tzinfo is None:
        return ahora.replace(tzinfo=zona)
    return ahora.astimezone(zona)


def _num(texto):
    texto = (texto or "").strip()
    if texto.isdigit():
        return int(texto)
    return _NUM.get(texto)


def _enmascarar(t, spans):
    lista = list(t)
    for inicio, fin in spans:
        for i in range(max(0, inicio), min(len(lista), fin)):
            lista[i] = " "
    return "".join(lista)


def _aplicar_periodo(hora, periodo):
    if periodo == "tarde":
        return 12 if hora == 12 else (hora + 12 if hora < 12 else hora)
    if periodo == "noche":
        return 0 if hora == 12 else (hora + 12 if hora < 12 else hora)
    if periodo in ("manana", "madrugada"):
        return 0 if hora == 12 else hora
    return hora


def _parsear_hora(t, permitir_suelto=False):
    """Devuelve {'hora': 'HH:MM', 'span': (a,b), 'ambiguo': bool} o None."""
    if not t:
        return None
    m = _TIEMPO_ABS.search(t)
    patron = "abs"
    if not m:
        m = _TIEMPO_RELOJ.search(t)
        patron = "reloj"
    if not m:
        m = _TIEMPO_PALABRA.search(t)
        patron = "palabra"
    if not m and permitir_suelto:
        m = _TIEMPO_SUELTO.search(t)
        patron = "suelto"
    if not m:
        return None

    periodo = None
    if patron == "palabra":
        palabra = m.group(1)
        hora, minuto = (12, 0) if palabra == "mediodia" else (0, 0)
        return {"hora": f"{hora:02d}:{minuto:02d}", "span": m.span(), "ambiguo": False}

    if patron == "abs":
        hora = _num(m.group(1))
        minuto = _num(m.group(2)) if m.group(2) else 0
        relacion, resto = m.group(3), m.group(4)
        periodo = m.group(5)
    elif patron == "reloj":
        hora, minuto = int(m.group(1)), int(m.group(2))
        relacion, resto = None, None
        periodo = m.group(3)
    else:                                  # «7 y media»
        hora = _num(m.group(1))
        relacion, resto = "y", m.group(2)
        periodo = m.group(3)

    if hora is None or minuto is None:
        return None
    if resto in ("media", "cuarto"):
        cantidad = 30 if resto == "media" else 15
    elif resto:
        cantidad = _num(resto)
    else:
        cantidad = 0
    if cantidad is None:
        return None

    if relacion == "menos":
        total = hora * 60 - cantidad
        total %= 24 * 60
        hora, minuto = divmod(total, 60)
    else:
        minuto += cantidad
    if not 0 <= hora <= 23 or not 0 <= minuto <= 59:
        return None

    ambiguo = periodo is None and 1 <= hora <= 7
    if periodo:
        hora = _aplicar_periodo(hora, periodo)
    elif ambiguo:
        hora += 12
    return {"hora": f"{hora:02d}:{minuto:02d}", "span": m.span(), "ambiguo": ambiguo}


def _parsear_duracion(t):
    """Minutos de «10 minutos», «media hora», «hora y media»; None si no hay."""
    if not t:
        return None
    if re.search(r"\bmedia\s+hora\b", t):
        return 30
    if re.search(r"\bhora\s+y\s+media\b", t):
        return 90
    m = _DURACION.search(t)
    if not m:
        return None
    cantidad = m.group(1)
    unidad = m.group(2)
    if cantidad in ("media", "medio"):
        return 30 if unidad.startswith("hora") else None
    valor = _num(cantidad)
    if valor is None:
        return None
    if unidad.startswith("hora"):
        valor *= 60
    if re.search(r"\by\s+media\b", t[m.end():m.end() + 12]):
        valor += 30
    return int(valor)


def _relativo_minutos(t):
    """Minutos de «en 10 minutos» / «en hora y media». Devuelve (minutos, span)."""
    m = _RELATIVO.search(t)
    if m:
        if m.group(1) in ("media", "medio"):
            cantidad = 30
        else:
            cantidad = _num(m.group(1))
            if cantidad is not None and m.group(2).startswith("hora"):
                cantidad *= 60
        if cantidad is None:
            return None, None
        if re.search(r"\by\s+media\b", t[m.end():m.end() + 12]):
            cantidad += 30
        return cantidad, m.span()
    m = _RELATIVO_HORA_MEDIA.search(t)
    if m:
        return 90, m.span()
    return None, None


# ---------- Días y fechas ----------

def _etiqueta_dias(dias):
    dias = list(dias)
    if dias == [0, 1, 2, 3, 4, 5, 6]:
        return "todos los días"
    if dias == [0, 1, 2, 3, 4]:
        return "de lunes a viernes"
    nombres = [_DIAS[d] for d in dias]
    if len(nombres) == 1:
        return f"los {nombres[0]}"
    return "los " + ", ".join(nombres[:-1]) + " y " + nombres[-1]


def _parsear_dia(t):
    """Devuelve la parte del día/fecha de la frase (sin hora) o None."""
    if not t:
        return None

    m = re.search(r"\bpasado\s+manana\b", t)
    if m:
        return {"tipo": "relativo", "offset": 2, "etiqueta": "pasado mañana", "span": m.span()}
    m = re.search(r"\bhoy\b", t)
    if m:
        return {"tipo": "relativo", "offset": 0, "etiqueta": "hoy", "span": m.span()}
    m = re.search(r"\bmanana\b", t)
    if m:
        return {"tipo": "relativo", "offset": 1, "etiqueta": "mañana", "span": m.span()}

    m = re.search(r"\b(?:todos\s+los\s+dias|cada\s+dia|diariamente)\b", t)
    if m:
        return {"tipo": "dias", "dias": [0, 1, 2, 3, 4, 5, 6],
                "etiqueta": "todos los días", "span": m.span()}
    if re.search(r"\bentre\s+semana\b", t):
        m = re.search(r"\bentre\s+semana\b", t)
        return {"tipo": "dias", "dias": [0, 1, 2, 3, 4],
                "etiqueta": "de lunes a viernes", "span": m.span()}

    m = re.search(r"\b(?:de\s+)?(" + _DIAS_ALT + r")\s+a\s+(" + _DIAS_ALT + r")\b", t)
    if m:
        inicio, fin = _DIAS_SEMANA[m.group(1)], _DIAS_SEMANA[m.group(2)]
        dias = []
        actual = inicio
        while True:
            dias.append(actual)
            if actual == fin:
                break
            actual = (actual + 1) % 7
        return {"tipo": "dias", "dias": dias,
                "etiqueta": f"de {m.group(1)} a {m.group(2)}", "span": m.span()}

    m = re.search(r"\b(?:todos\s+)?los\s+((?:" + _DIAS_ALT +
                  r")(?:\s*,?\s*(?:y|e)\s+(?:" + _DIAS_ALT + r"))*)\b", t)
    if m:
        dias = sorted({_DIAS_SEMANA[p] for p in re.findall(_DIAS_ALT, m.group(1))})
        return {"tipo": "dias", "dias": dias, "etiqueta": _etiqueta_dias(dias), "span": m.span()}

    m = re.search(r"\b(" + _DIAS_ALT + r")\s+y\s+(" + _DIAS_ALT + r")\b", t)
    if m and "el " not in t[max(0, m.start() - 3):m.start()]:
        dias = sorted({_DIAS_SEMANA[m.group(1)], _DIAS_SEMANA[m.group(2)]})
        return {"tipo": "dias", "dias": dias, "etiqueta": _etiqueta_dias(dias), "span": m.span()}

    m = re.search(
        r"\b(?:el\s+)?(\d{1,2}|primero|uno)\s+de\s+(" + _MES_ALT + r")(?:\s+de\s+(\d{4}))?\b", t)
    if m:
        dia = 1 if m.group(1) in ("primero", "uno") else int(m.group(1))
        mes = _MESES_NUM[m.group(2)]
        anio = int(m.group(3)) if m.group(3) else None
        return {"tipo": "fecha", "dia": dia, "mes": mes, "anio": anio, "span": m.span()}

    m = re.search(r"\b(?:el\s+)?(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b", t)
    if m:
        return {"tipo": "fecha", "dia": int(m.group(1)), "mes": int(m.group(2)),
                "anio": int(m.group(3)) if m.group(3) else None, "span": m.span()}

    m = re.search(r"\b(" + _DIAS_ALT + r")\s+que\s+viene\b", t)
    if m:
        return {"tipo": "semana_dia", "dia_semana": _DIAS_SEMANA[m.group(1)],
                "proximo": True, "span": m.span()}

    m = re.search(r"\b(?:(este|proximo|proxima)\s+)?(" + _DIAS_ALT + r")\b", t)
    if m:
        return {"tipo": "semana_dia", "dia_semana": _DIAS_SEMANA[m.group(2)],
                "proximo": bool(m.group(1)), "span": m.span()}
    return None


def _fecha_de_dia(dia, ahora_l, hora=None, para_consulta=False):
    """Fecha concreta de un día relativo/semana/fecha. `hora` es 'HH:MM' o None."""
    hoy = ahora_l.date()
    hh, mm = (0, 0)
    if hora:
        hh, mm = int(hora[:2]), int(hora[3:])
    objetivo = None
    if dia["tipo"] == "relativo":
        objetivo = datetime.combine(hoy + timedelta(days=dia["offset"]), time(hh, mm),
                                    tzinfo=persona.zona_robot())
    elif dia["tipo"] == "semana_dia":
        adelante = (dia["dia_semana"] - hoy.weekday()) % 7
        if dia.get("proximo") and adelante == 0:
            adelante = 7
        objetivo = datetime.combine(hoy + timedelta(days=adelante), time(hh, mm),
                                    tzinfo=persona.zona_robot())
        if not para_consulta and objetivo.replace(second=0, microsecond=0) < ahora_l.replace(second=0, microsecond=0):
            objetivo += timedelta(days=7)          # la hora ya pasó: la próxima semana
    elif dia["tipo"] == "fecha":
        anio = dia.get("anio") or hoy.year
        try:
            objetivo = datetime.combine(date(anio, dia["mes"], dia["dia"]), time(hh, mm),
                                        tzinfo=persona.zona_robot())
        except ValueError:
            return None
        if dia.get("anio") is None:
            paso = objetivo.date() < hoy
            if not paso and not para_consulta and objetivo.date() == hoy:
                paso = objetivo.replace(second=0, microsecond=0) < ahora_l.replace(second=0, microsecond=0)
            if paso:
                try:
                    objetivo = objetivo.replace(year=anio + 1)   # el próximo año
                except ValueError:
                    return None
    else:
        return None
    return objetivo


def _etiqueta_cuando(objetivo, ahora_l):
    fecha = objetivo.date()
    hoy = ahora_l.date()
    if fecha == hoy:
        etiqueta = "hoy"
    elif fecha == hoy + timedelta(days=1):
        etiqueta = "mañana"
    else:
        etiqueta = f"el {agenda.fecha_larga(fecha)}"
    return f"{etiqueta} a las {objetivo:%H:%M}"


def _resolver_cuando(datos, ahora_l):
    """Devuelve fecha/días y el texto «mañana a las 17:00» para la respuesta."""
    if datos.get("objetivo"):
        objetivo = datos["objetivo"]
        if objetivo.tzinfo is None:
            objetivo = objetivo.replace(tzinfo=persona.zona_robot())
        return {"fecha": objetivo.date().isoformat(), "dias": None,
                "etiqueta": _etiqueta_cuando(objetivo, ahora_l), "rodado": False}
    if datos.get("dia") and datos["dia"].get("tipo") == "dias":
        dias = datos["dia"]["dias"]
        return {"fecha": None, "dias": dias,
                "etiqueta": f"{datos['dia'].get('etiqueta') or _etiqueta_dias(dias)} a las {datos['hora']}",
                "rodado": False}

    dia = datos.get("dia")
    if dia is None:
        dia = {"tipo": "relativo", "offset": 0, "etiqueta": "hoy"}
    objetivo = _fecha_de_dia(dia, ahora_l, datos["hora"])
    if objetivo is None:
        return None

    rodado = False
    if dia["tipo"] == "relativo" and dia["offset"] == 0:
        if objetivo.replace(second=0, microsecond=0) < ahora_l.replace(second=0, microsecond=0):
            objetivo += timedelta(days=1)
            rodado = True
    return {"fecha": objetivo.date().isoformat(), "dias": None,
            "etiqueta": _etiqueta_cuando(objetivo, ahora_l), "rodado": rodado,
            "hora_dicha": datos["hora"]}


# ---------- Título ----------

def _texto_sin_spans(original, t, spans):
    base = original if len(original or "") == len(t) else t
    for inicio, fin in sorted(spans, key=lambda s: s[0], reverse=True):
        base = base[:inicio] + " " + base[fin:]
    return re.sub(r"\s+", " ", base).strip(" ,.;:¡!¿?\"'«»")


def _limpiar_titulo(texto):
    if not texto:
        return ""
    texto = re.sub(r"\s+", " ", texto).strip(" ,.;:¡!¿?\"'«»")
    while True:
        nuevo = re.sub(
            r"^(?:que|de|del|a|al|para|por\s+favor|porfa)\b[\s,]*", "", texto,
            count=1, flags=re.IGNORECASE)
        if nuevo == texto:
            break
        texto = nuevo.strip()
    texto = re.sub(r"\s+(?:por\s+favor|porfa)$", "", texto, flags=re.IGNORECASE).strip()
    return texto


def _tokens(texto):
    return {p for p in re.findall(r"[a-z0-9]+", normalizar(texto))
            if len(p) >= 3 and p not in _STOP}


def _coincide_titulo(titulo_evento, tokens):
    if not tokens:
        return True
    propios = _tokens(titulo_evento)
    return tokens <= propios or any(t in propios for t in tokens)


# ---------- Extracción de una creación ----------

def _extraer_campos(texto, t, tipo, ahora_l, spans_previos=None):
    spans = list(spans_previos or [])
    hora_info = _parsear_hora(t, permitir_suelto=bool(spans))
    if hora_info:
        spans.append(hora_info["span"])
    t_dias = _enmascarar(t, [hora_info["span"]] if hora_info else [])
    dia = _parsear_dia(t_dias)
    if dia:
        spans.append(dia["span"])

    titulo = _limpiar_titulo(_texto_sin_spans(texto, t, spans))
    datos = {
        "tipo": tipo,
        "titulo": titulo,
        "hora": hora_info["hora"] if hora_info else None,
        "hora_dicha": hora_info["hora"] if hora_info else None,
        "dia": dia,
        "objetivo": None,
    }

    relativo, span_relativo = _relativo_minutos(t)
    if relativo is not None:
        objetivo = ahora_l + timedelta(minutes=relativo)
        datos["objetivo"] = objetivo
        datos["hora"] = f"{objetivo:%H:%M}"
        datos["hora_dicha"] = datos["hora"]
        datos["minutos"] = relativo
        datos["titulo"] = _limpiar_titulo(_texto_sin_spans(
            texto, t, spans + ([span_relativo] if span_relativo else [])))

    return datos


def _span_trigger(t, tipo):
    if tipo == "alarma":
        m = _TRIGGER_ALARMA.search(t)
        if m:
            return m.span(), False
        m = re.search(r"\b(?:una\s+)?alarma\b", t)
        return (m.span(), False) if m else (None, False)
    if tipo == "temporizador":
        m = _TRIGGER_TEMPORIZADOR.search(t) or _TRIGGER_PON_MINUTOS.search(t)
        return (m.span(), False) if m else (None, False)
    m = _TRIGGER_RECORDATORIO.search(t) or _TRIGGER_RECORDAR.search(t)
    return (m.span(), False) if m else (None, False)


# ---------- Estado pendiente ----------

def _clave_de(familia_id, clave):
    return f"{familia_id}:{clave or 'voz'}"


def _guardar_pendiente(clave, datos, falta, pregunta, ahora_l):
    with _lock:
        _PENDIENTES[clave] = {
            "datos": datos,
            "falta": falta,
            "pregunta": pregunta,
            "accion": "elegir_cancelar" if falta == "cancelar" else "crear",
            "vence": ahora_l + timedelta(seconds=VENCE_PENDIENTE),
        }
    return {"respuesta": pregunta, "emocion": "neutral", "pendiente": True}


def _tomar_pendiente(clave, ahora_l):
    with _lock:
        pend = _PENDIENTES.get(clave)
        if not pend:
            return None
        if ahora_l >= pend["vence"]:
            _PENDIENTES.pop(clave, None)
            return None
        return pend


def _borrar_pendiente(clave):
    with _lock:
        _PENDIENTES.pop(clave, None)


def _es_orden_nueva(t):
    return bool(_RECORDAR.search(t) or _TRIGGER_ALARMA.search(t) or _TEMPORIZADOR.search(t)
                or _CANCELAR.search(t) or _QUERY_DIA.search(t) or _SILENCIO.search(t)
                or _REACTIVAR.search(t) or _QUERY_EVENTO.search(t))


def _completar_pendiente(clave, pend, texto, t, familia_id, autor, ahora_l, robot_id):
    datos = dict(pend["datos"])
    if pend["falta"] == "minutos":
        minutos = _parsear_duracion(t) or _num(t)
        if not minutos:
            return _guardar_pendiente(clave, datos, "minutos",
                                      "¿Cuántos minutos quieres que espere?", ahora_l)
        datos["minutos"] = int(minutos)
        return _crear(clave, datos, familia_id, autor, ahora_l, robot_id)

    if _OLVIDAR.search(t):
        _borrar_pendiente(clave)
        return {"respuesta": "Listo, lo olvido.", "emocion": "neutral", "intencion": "olvidar"}

    if _es_orden_nueva(t) and pend["falta"] != "titulo":
        _borrar_pendiente(clave)
        return None

    nuevos = _extraer_campos(texto, t, datos["tipo"], ahora_l)
    if nuevos.get("hora"):
        datos["hora"] = nuevos["hora"]
        datos["hora_dicha"] = nuevos.get("hora_dicha") or nuevos["hora"]
        datos["objetivo"] = nuevos.get("objetivo")
    if nuevos.get("dia"):
        datos["dia"] = nuevos["dia"]
    if nuevos.get("titulo"):
        datos["titulo"] = nuevos["titulo"]
    if nuevos.get("minutos"):
        datos["minutos"] = nuevos["minutos"]

    if len(datos.get("titulo") or "") > MAX_TITULO:
        return _guardar_pendiente(clave, datos, "titulo",
                                  "Es muy largo. Dime el recordatorio en pocas palabras.", ahora_l)
    if datos["tipo"] != "alarma" and not datos.get("titulo"):
        return _guardar_pendiente(clave, datos, "titulo", "¿Qué te recuerdo?", ahora_l)
    if not datos.get("hora") and not datos.get("objetivo"):
        pregunta = "¿A qué hora pongo la alarma?" if datos["tipo"] == "alarma" else "¿A qué hora te lo recuerdo?"
        return _guardar_pendiente(clave, datos, "hora", pregunta, ahora_l)
    return _crear(clave, datos, familia_id, autor, ahora_l, robot_id)


# ---------- Creación ----------

def _puede_crear(clave, ahora_l):
    with _lock:
        recientes = [t for t in _CREACIONES.get(clave, [])
                     if (ahora_l - t).total_seconds() < 60]
        if len(recientes) >= MAX_CREACIONES_MINUTO:
            _CREACIONES[clave] = recientes
            return False
        recientes.append(ahora_l)
        _CREACIONES[clave] = recientes
        return True


def _crear(clave, datos, familia_id, autor, ahora_l, robot_id):
    tipo = datos["tipo"]
    if tipo == "temporizador" or (datos.get("minutos") and not datos.get("titulo")):
        minutos = datos.get("minutos") or _parsear_duracion(datos.get("texto", ""))
        if not minutos:
            return _guardar_pendiente(clave, datos, "minutos",
                                      "¿Cuántos minutos quieres que espere?", ahora_l)
        if not _puede_crear(clave, ahora_l):
            return {"respuesta": "Espera un poquito: ya creaste tres cosas en el último minuto.",
                    "emocion": "neutral", "intencion": "limite"}
        try:
            evento = agenda.crear_temporizador(minutos, familia_id=familia_id,
                                               creado_por=autor, ahora=ahora_l, robot_id=robot_id)
        except (ValueError, PermissionError) as error:
            return {"respuesta": f"No pude poner el temporizador: {error}.", "emocion": "neutral",
                    "intencion": "error"}
        objetivo = _local(datetime.fromisoformat(evento["fecha"] + "T" + evento["hora"]))
        return {"respuesta": f"Listo: te aviso en {minutos} minutos, a las {objetivo:%H:%M}.",
                "emocion": "feliz", "intencion": "temporizador", "evento": evento}

    if not datos.get("titulo") and tipo != "alarma":
        return _guardar_pendiente(clave, datos, "titulo", "¿Qué te recuerdo?", ahora_l)
    if not datos.get("hora"):
        pregunta = "¿A qué hora pongo la alarma?" if tipo == "alarma" else "¿A qué hora te lo recuerdo?"
        return _guardar_pendiente(clave, datos, "hora", pregunta, ahora_l)

    datos = dict(datos)
    if tipo == "alarma" and not datos.get("titulo"):
        datos["titulo"] = "despertarse"
    cuando = _resolver_cuando(datos, ahora_l)
    if cuando is None:
        return {"respuesta": "No pude calcular ese día. ¿Me lo dices con otra fecha?",
                "emocion": "neutral", "intencion": "error"}

    if not _puede_crear(clave, ahora_l):
        return {"respuesta": "Espera un poquito: ya creaste tres cosas en el último minuto.",
                "emocion": "neutral", "intencion": "limite"}
    try:
        evento = agenda.crear_evento(
            tipo, datos["titulo"], hora=datos["hora"], fecha=cuando["fecha"],
            dias=cuando["dias"], creado_por=autor, familia_id=familia_id, robot_id=robot_id)
    except PermissionError:
        return {"respuesta": "Eso no lo puedo cambiar: lo crearon mamá o papá.",
                "emocion": "neutral", "intencion": "error"}
    except ValueError as error:
        return {"respuesta": f"No pude guardarlo: {error}", "emocion": "neutral",
                "intencion": "error"}

    _borrar_pendiente(clave)
    titulo = evento["titulo"]
    rodado = cuando.get("rodado")
    if tipo == "alarma":
        if rodado:
            texto_respuesta = (f"Ya pasaron las {cuando.get('hora_dicha', datos['hora'])}. "
                               f"Puse la alarma para {cuando['etiqueta']}.")
        else:
            texto_respuesta = (f"Listo: alarma para {cuando['etiqueta']}. "
                               f"Si quieres, la cancelas diciendo «cancela mi alarma».")
        emocion = "neutral"
    else:
        if rodado:
            texto_respuesta = (f"Ya pasaron las {cuando.get('hora_dicha', datos['hora'])}. "
                               f"Te lo recuerdo {cuando['etiqueta']} {titulo}.")
        else:
            texto_respuesta = f"Listo: te recuerdo {cuando['etiqueta']} {titulo}."
        emocion = "feliz"
    return {"respuesta": texto_respuesta.strip(), "emocion": emocion,
            "intencion": "crear", "evento": evento}


# ---------- Consultas ----------

def _hay_eventos(familia_id, ahora_l):
    try:
        agenda.asegurar_cumpleanos(familia_id, ahora=ahora_l)
    except Exception:
        pass
    return bool(agenda.listar_eventos(familia_id, incluir_inactivos=False))


def _consultar_dia(intencion, familia_id, ahora_l):
    if not _hay_eventos(familia_id, ahora_l):
        return {"respuesta": "Todavía no sé nada de tu agenda: pídele a mamá o papá que la configuren.",
                "emocion": "neutral", "intencion": "consultar"}
    dia = intencion.get("dia")
    if dia is None:
        texto = agenda.describir_dia(familia_id, "hoy", ahora=ahora_l)
    elif dia["tipo"] == "relativo":
        texto = agenda.describir_dia(familia_id, "manana" if dia["offset"] == 1 else
                                     ("hoy" if dia["offset"] == 0 else
                                      (ahora_l.date() + timedelta(days=dia["offset"])).isoformat()),
                                     ahora=ahora_l)
    elif dia["tipo"] == "dias":
        texto = agenda.describir_proximos(familia_id, dias=7, ahora=ahora_l)
    else:
        objetivo = _fecha_de_dia(dia, ahora_l, para_consulta=True)
        if objetivo is None:
            texto = "No entendí ese día."
        else:
            texto = agenda.describir_dia(familia_id, objetivo.date().isoformat(), ahora=ahora_l)
    return {"respuesta": texto, "emocion": "neutral", "intencion": "consultar"}


def _consultar_semana(familia_id, ahora_l):
    if not _hay_eventos(familia_id, ahora_l):
        return {"respuesta": "Todavía no sé nada de tu agenda: pídele a mamá o papá que la configuren.",
                "emocion": "neutral", "intencion": "consultar"}
    return {"respuesta": agenda.describir_proximos(familia_id, dias=7, ahora=ahora_l),
            "emocion": "neutral", "intencion": "consultar"}


def _consultar_evento(intencion, familia_id, ahora_l):
    tipo = intencion.get("tipo")
    tokens = intencion.get("tokens") or set()
    if not tokens and not tipo:
        return {"respuesta": "¿De qué quieres saber la hora?", "emocion": "neutral",
                "intencion": "consultar"}
    items = agenda.ocurrencias_entre(familia_id, ahora_l, ahora_l + timedelta(days=8), ahora=ahora_l)
    for item in items:
        evento = item["evento"]
        if tipo and evento["tipo"] != tipo:
            continue
        if tokens and not _coincide_titulo(evento["titulo"], tokens):
            continue
        cuando = item["cuando"]
        etiqueta = "hoy" if cuando.date() == ahora_l.date() else (
            "mañana" if cuando.date() == ahora_l.date() + timedelta(days=1)
            else f"el {agenda.fecha_larga(cuando.date())}")
        return {"respuesta": f"{etiqueta.capitalize()} a las {cuando:%H:%M}: {evento['titulo']}.",
                "emocion": "neutral", "intencion": "consultar"}
    if tipo and not tokens:
        nombre = "alarma" if tipo == "alarma" else "evento"
        return {"respuesta": f"No encuentro esa {nombre} en tu agenda.", "emocion": "neutral",
                "intencion": "consultar"}
    return {"respuesta": "No encuentro eso en tu agenda.", "emocion": "neutral",
            "intencion": "consultar"}


def _hora_actual(ahora_l):
    return {"respuesta": f"Son las {ahora_l:%H:%M}.", "emocion": "neutral", "intencion": "hora"}


def _fecha_actual(ahora_l):
    return {"respuesta": f"Hoy es {agenda.fecha_larga(ahora_l.date())} de {ahora_l.year}.",
            "emocion": "neutral", "intencion": "fecha"}


# ---------- Cancelación ----------

_CANCEL_STOP = {
    "cancela", "cancelar", "borra", "borrar", "elimina", "eliminar", "quita", "quitar",
    "suspende", "suspender", "alarma", "alarmas", "recordatorio", "recordatorios",
    "temporizador", "temporizadores", "rutina", "rutinas", "evento", "eventos", "agenda",
}


def _hora_de_cancelacion(t):
    info = _parsear_hora(t)
    if info:
        return info
    m = re.search(
        r"\b(?:de\s+)?las?\s+(\d{1,2})(?:\s*:\s*(\d{2}))?(?:\s+y\s+(media|cuarto))?"
        r"(?:\s+de\s+la\s+(" + _PERIODOS + r"))?\b", t)
    if not m:
        return None
    hora = int(m.group(1))
    minuto = int(m.group(2)) if m.group(2) else 0
    if m.group(3) == "media":
        minuto += 30
    elif m.group(3) == "cuarto":
        minuto += 15
    if not 0 <= hora <= 23 or not 0 <= minuto <= 59:
        return None
    periodo = m.group(4)
    if periodo:
        hora = _aplicar_periodo(hora, periodo)
    elif 1 <= hora <= 7:
        hora += 12
    return {"hora": f"{hora:02d}:{minuto:02d}", "span": m.span()}


def _candidatos_cancelar(t, familia_id):
    tipo = None
    if _ALARMA.search(t):
        tipo = "alarma"
    elif _TEMPORIZADOR.search(t):
        tipo = "temporizador"
    elif re.search(r"\brecordatorio\b", t):
        tipo = "recordatorio"
    elif re.search(r"\brutina\b", t):
        tipo = "rutina"

    hora_info = _hora_de_cancelacion(t)
    spans = [hora_info["span"]] if hora_info else []
    m = _TRIGGER_ALARMA.search(t) or _TRIGGER_RECORDATORIO.search(t) or _TRIGGER_TEMPORIZADOR.search(t)
    if m:
        spans.append(m.span())
    tokens = _tokens(_limpiar_titulo(_texto_sin_spans(t, t, spans))) - _CANCEL_STOP
    eventos = [e for e in agenda.listar_eventos(familia_id, incluir_inactivos=False)
               if e["tipo"] != "cumpleanos"]
    if tipo:
        eventos = [e for e in eventos if e["tipo"] == tipo]
    if hora_info:
        eventos = [e for e in eventos if e["hora"] == hora_info["hora"]]
    if tokens:
        eventos = [e for e in eventos if _coincide_titulo(e["titulo"], tokens)]
    return eventos, tipo, tokens


def _cancelar(t, familia_id, autor="nino"):
    if _CANCELAR_MEMORIA.search(t):
        return None                       # lo maneja el puente antes que la agenda
    eventos, tipo, tokens = _candidatos_cancelar(t, familia_id)
    if not eventos:
        nombre = "esa alarma" if tipo == "alarma" else "eso"
        return {"respuesta": f"No encuentro {nombre} en tu agenda.", "emocion": "neutral",
                "intencion": "cancelar"}
    if len(eventos) == 1:
        return _borrar_evento(eventos[0], autor, familia_id)
    lista = "; ".join(f"a las {e['hora']} {e['titulo']}" for e in eventos[:3])
    return {"respuesta": f"Tienes varios: {lista}. ¿Cuál borro?",
            "emocion": "neutral", "intencion": "elegir_cancelar",
            "_candidatos": eventos}


def _borrar_evento(evento, autor, familia_id):
    try:
        borrados = agenda.borrar_evento(evento["id"], familia_id=familia_id, autor=autor)
    except PermissionError:
        return {"respuesta": "Eso lo crearon mamá o papá; no puedo borrarlo.",
                "emocion": "neutral", "intencion": "cancelar"}
    if not borrados:
        return {"respuesta": "No encontré ese evento.", "emocion": "neutral", "intencion": "cancelar"}
    return {"respuesta": f"Listo: borré {evento['titulo']} de las {evento['hora']}.",
            "emocion": "neutral", "intencion": "cancelar"}


def _elegir_cancelar(clave, pend, t, autor, familia_id):
    eventos = pend["datos"].get("candidatos") or []
    hora_info = _hora_de_cancelacion(t)
    tokens = _tokens(_limpiar_titulo(t)) - _CANCEL_STOP
    elegidos = eventos
    if hora_info:
        elegidos = [e for e in elegidos if e["hora"] == hora_info["hora"]]
    if tokens:
        elegidos = [e for e in elegidos if _coincide_titulo(e["titulo"], tokens)]
    if len(elegidos) == 1:
        _borrar_pendiente(clave)
        return _borrar_evento(elegidos[0], autor, familia_id)
    if not elegidos and _es_orden_nueva(t):
        return None
    if not elegidos:
        return {"respuesta": "No entendí cuál. Dime el nombre o la hora.", "emocion": "neutral",
                "intencion": "elegir_cancelar"}
    lista = "; ".join(f"a las {e['hora']} {e['titulo']}" for e in elegidos[:3])
    return {"respuesta": f"Todavía hay varios: {lista}. ¿Cuál borro?",
            "emocion": "neutral", "intencion": "elegir_cancelar"}


# ---------- Analizar sin ejecutar ----------

def analizar(texto, ahora=None):
    """Convierte el texto en una intención. No toca la base ni guarda pendientes."""
    t = normalizar(texto).strip()
    if not t:
        return None
    ahora_l = _local(ahora)

    # 1. Cumpleaños, hora concreta de un evento, y luego hora/fecha del día.
    if _CUMPLE.search(t):
        return {"accion": "cumple"}
    if _QUERY_EVENTO.search(t):
        m = _QUERY_EVENTO.search(t)
        resto = t[m.end():]
        tipo = "alarma" if _ALARMA.search(t[m.start():]) else (
            "temporizador" if _TEMPORIZADOR.search(resto) else None)
        if tipo:
            resto = re.sub(r"\b(?:mi|el|la|una|alarma|temporizador)\b", " ", resto)
        return {"accion": "consultar_evento", "tipo": tipo, "tokens": _tokens(resto)}
    if _QUERY_FECHA.search(t):
        return {"accion": "fecha"}
    if _QUERY_HORA.search(t):
        return {"accion": "hora"}
    if _AYUDA.search(t) and len(t.split()) <= 6:
        return {"accion": "ayuda"}

    # 2. Silencio temporal y reactivación.
    if _SILENCIO.search(t):
        minutos = _parsear_duracion(t) or 30
        return {"accion": "silencio", "minutos": max(1, min(1440, int(minutos)))}
    if _REACTIVAR.search(t):
        return {"accion": "reactivar"}

    # 3. Cancelar (solo si nombra algo de la agenda o una hora).
    if _CANCELAR.search(t) and (
            _ALARMA.search(t) or re.search(r"\b(?:recordatorio|temporizador|rutina|evento|agenda)\b", t)
            or _hora_de_cancelacion(t)):
        return {"accion": "cancelar"}

    # 4. Rutina cumplida (sin estrellas todavía).
    if _RUTINA_HECHA.search(t):
        return {"accion": "rutina_hecha"}

    # 5. Consultas de la agenda.
    if _QUERY_DIA.search(t):
        dia_t = _enmascarar(t, [])
        dia = _parsear_dia(dia_t)
        if _QUERY_SEMANA.search(t):
            return {"accion": "consultar_semana"}
        return {"accion": "consultar_dia", "dia": dia}
    if re.search(r"\bmi\s+agenda\b", t):
        return {"accion": "consultar_dia", "dia": _parsear_dia(t)}

    # 6. Crear.
    tipo = None
    if _ALARMA.search(t):
        tipo = "alarma"
    elif _TEMPORIZADOR.search(t) or _PON_MINUTOS.search(t):
        tipo = "temporizador"
    elif _RECORDAR.search(t) or _TRIGGER_RECORDATORIO.search(t) or _RELATIVO.search(t) \
            or _RELATIVO_HORA_MEDIA.search(t):
        tipo = "recordatorio"
    if tipo is None:
        return None

    if tipo == "temporizador":
        minutos = _parsear_duracion(t) or _num(t)
        if not minutos:
            return {"accion": "crear", "tipo": "temporizador", "minutos": None,
                    "titulo": "", "hora": None, "dia": None, "objetivo": None}
        return {"accion": "crear", "tipo": "temporizador", "minutos": int(minutos),
                "titulo": "", "hora": None, "dia": None, "objetivo": None}

    span, _ = _span_trigger(t, tipo)
    spans = [span] if span else []
    datos = _extraer_campos(texto, t, tipo, ahora_l, spans_previos=spans)
    datos["accion"] = "crear"

    # «avísame en 10 minutos» sin título es un temporizador, no un recordatorio vacío.
    if datos.get("objetivo") and not datos.get("titulo") and datos["tipo"] == "recordatorio":
        datos["tipo"] = "temporizador"
        datos["minutos"] = int((datos["objetivo"] - ahora_l).total_seconds() // 60)
        datos["hora"] = None
    return datos


# ---------- Ejecutar ----------

def procesar(texto, familia_id="1", autor="nino", ahora=None, robot_id=None, clave=None):
    """Devuelve la respuesta local o None si la frase no es de agenda."""
    t = normalizar(texto).strip()
    if not t:
        return None
    ahora_l = _local(ahora)
    clave = _clave_de(familia_id, clave)

    pend = _tomar_pendiente(clave, ahora_l)
    if pend:
        if pend.get("accion") == "elegir_cancelar":
            elegido = _elegir_cancelar(clave, pend, t, autor, familia_id)
            if elegido is not None:
                return elegido
            _borrar_pendiente(clave)
        else:
            completado = _completar_pendiente(clave, pend, texto, t, familia_id, autor,
                                              ahora_l, robot_id)
            if completado is not None:
                return completado

    intencion = analizar(texto, ahora=ahora_l)
    if not intencion:
        return None
    return _ejecutar(clave, intencion, t, familia_id, autor, ahora_l, robot_id)


def _ejecutar(clave, intencion, t, familia_id, autor, ahora_l, robot_id):
    accion = intencion["accion"]

    if accion == "hora":
        return _hora_actual(ahora_l)
    if accion == "fecha":
        return _fecha_actual(ahora_l)
    if accion == "cumple":
        return {"respuesta": agenda.describir_cumple(familia_id, ahora=ahora_l),
                "emocion": "feliz", "intencion": "cumple"}
    if accion == "ayuda":
        return {"respuesta": "Puedo recordarte cosas, poner alarmas y temporizadores, decirte "
                             "qué tienes hoy o mañana y cuánto falta para tu cumpleaños.",
                "emocion": "feliz", "intencion": "ayuda"}
    if accion == "silencio":
        hasta = agenda.silenciar(intencion["minutos"], familia_id=familia_id, ahora=ahora_l)
        return {"respuesta": f"Listo: no te molesto por {intencion['minutos']} minutos, "
                             f"hasta las {hasta:%H:%M}. Las alarmas siguen sonando.",
                "emocion": "neutral", "intencion": "silencio"}
    if accion == "reactivar":
        agenda.reactivar(familia_id=familia_id, ahora=ahora_l)
        return {"respuesta": "Listo, vuelvo a avisarte.", "emocion": "feliz",
                "intencion": "reactivar"}
    if accion == "rutina_hecha":
        return {"respuesta": "¡Bien hecho!", "emocion": "feliz", "intencion": "rutina_hecha"}
    if accion == "consultar_dia":
        return _consultar_dia(intencion, familia_id, ahora_l)
    if accion == "consultar_semana":
        return _consultar_semana(familia_id, ahora_l)
    if accion == "consultar_evento":
        return _consultar_evento(intencion, familia_id, ahora_l)
    if accion == "cancelar":
        resultado = _cancelar(t, familia_id, autor)
        if resultado and resultado.get("intencion") == "elegir_cancelar":
            candidatos = resultado.pop("_candidatos", [])
            return _guardar_pendiente(clave, {"candidatos": candidatos}, "cancelar",
                                      resultado["respuesta"], ahora_l)
        return resultado
    if accion == "crear":
        return _crear(clave, intencion, familia_id, autor, ahora_l, robot_id)
    return None
