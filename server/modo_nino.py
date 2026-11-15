"""Filtros para que el robot converse de forma apropiada con un niño.

Son dos capas:
  1. Temas que se cortan antes de llegar al modelo (casos claros: contenido
     sexual, autolesión, insultos).
  2. Palabras que no deben salir en la respuesta, por si el modelo se escapa.

Lo demás (violencia en general, drogas, tristeza) no se bloquea: el modelo lo
responde con cuidado gracias a las instrucciones de personalidad, y bloquearlo
haría al robot tonto para preguntas normales ("por qué hay guerras").
"""

import re
import unicodedata

RESPUESTA_BLOQUEO = (
    "Eso no lo sé contar. ¿Me preguntas de animales, del espacio o de mis caras?"
)

TEMAS_BLOQUEADOS = [
    ("sexual", ("porno", "pornografia", "sexo", "desnudo", "desnuda", "violacion")),
    ("autolesion", ("suicidio", "suicidarme", "matarme", "cortarme",
                    "quiero matar", "quiero morir", "morirme")),
    ("insultos", ("puta", "puto", "mierda", "culiao", "weon", "hueon",
                  "imbecil", "idiota", "estupido", "estupida")),
]

# "matar" no está aquí a propósito: una explicación amable sobre la guerra o los
# dinosaurios puede usarlo, y reemplazarla entera haría al robot tonto.
PALABRAS_SALIDA = (
    "porno", "pornografia", "sexo", "desnudo", "desnuda", "violacion",
    "suicidio", "puta", "puto", "mierda", "culiao", "weon", "hueon", "imbecil",
)


def _plano(texto):
    """Minúsculas y sin tildes, para comparar."""
    sin_tildes = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn")


def _contiene(texto_plano, palabras):
    return any(re.search(r"\b" + re.escape(p) + r"\b", texto_plano) for p in palabras)


def revisar_entrada(texto):
    """Devuelve el nombre del tema bloqueado, o None si se puede conversar."""
    plano = _plano(texto)
    for tema, palabras in TEMAS_BLOQUEADOS:
        if _contiene(plano, palabras):
            return tema
    return None


def revisar_salida(frase):
    """Devuelve (frase_segura, fue_bloqueada)."""
    if _contiene(_plano(frase), PALABRAS_SALIDA):
        return RESPUESTA_BLOQUEO, True
    return frase, False
