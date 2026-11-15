"""Cambios de texto para que la voz pronuncie bien onomatopeyas.

Medido con edge-tts + Whisper: "Grrr" se deletrea (G-R-R-R) y "Zzz" se lee
"cita cita". Estos reemplazos hacen que suenen como sonidos.

Los emojis también se leen por su nombre ("cara feliz con ojos sonrientes"), y el modelo
los agrega solo al final de las frases: se quitan antes de sintetizar. La cara del robot
ya muestra la emoción; la voz no tiene que decirla.
"""

import re

# Emojis y pictogramas: bloques de emoticonos, símbolos y banderas, más los
# caracteres invisibles que los componen (selector de variación, unión de cero ancho).
EMOJIS = r"[\U0001F000-\U0001FAFF☀-➿⬀-⯿←-⇿⌀-⏿︎️‍⃣]"

# (patrón, reemplazo). Se aplican en orden y sin distinguir mayúsculas.
CAMBIOS = [
    (EMOJIS, ""),                # 😄 -> nada (si no, la voz dice "cara sonriendo con ojos sonrientes")
    (r"\bgrr+\w*", "groar"),     # Grrr / Grrrr -> groar (gruñido)
    (r"\bz{2,}\b", ""),          # Zzz -> silencio (la frase ya dice "sueño")
    (r"\bm{2,}\b", ""),          # Mmm -> silencio (se leía "eme eme")
]


def preparar_para_voz(texto):
    """Devuelve el texto listo para el sintetizador. Puede quedar vacío."""
    salida = texto
    for patron, reemplazo in CAMBIOS:
        salida = re.sub(patron, reemplazo, salida, flags=re.IGNORECASE)
    salida = re.sub(r"\s{2,}", " ", salida).strip()
    return re.sub(r"^[\s.·…-]+", "", salida).strip()
