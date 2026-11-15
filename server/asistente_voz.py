"""Asistente de voz para el robot (push-to-talk en el PC, 100% offline).

Cómo funciona:
  1. Aprietas Enter en la consola.
  2. Hablas normal. Cuando callas ~0.8 s (o a los 10 s) se corta la grabación.
  3. faster-whisper transcribe el audio en tu PC, en español, sin internet.
  4. Se interpreta el texto y se manda a POST /cmd del servidor, que mueve el
     robot y lo hace hablar con edge-tts.

No escucha de forma permanente a propósito: así no reacciona a la tele, ni a
las conversaciones de la casa, ni a su propia voz.

Necesita el servidor corriendo en otra consola:
    python puente.py

Uso:
    python asistente_voz.py
"""

import entorno  # noqa: F401  (carga server/.env antes de leer la configuración)
import difflib
import os
import random
import re
import sys
import unicodedata

import numpy as np
import requests
from faster_whisper import WhisperModel

# sounddevice (micrófono del PC) solo lo usa grabar(). En un servidor sin audio ni PortAudio no debe romper
# la importación: el puente reutiliza transcribir() y las reglas de este archivo sin grabar nada.
try:
    import sounddevice as sd
except (ImportError, OSError):
    sd = None

# La consola de Windows usa cp1252 por defecto cuando la salida no es una
# terminal, y ahí cualquier emoji revienta con UnicodeEncodeError.
for _flujo in (sys.stdout, sys.stderr):
    if hasattr(_flujo, "reconfigure"):
        try:
            _flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

SERVIDOR = os.getenv("ROBOT_URL", "http://127.0.0.1:8081")
MODELO = os.getenv("WHISPER_MODELO", "small")       # tiny, base, small, medium
MAX_SEGUNDOS = float(os.getenv("MAX_SEGUNDOS", "15"))
SILENCIO_SEGUNDOS = float(os.getenv("SILENCIO_SEGUNDOS", "1.0"))
ESPERA_MAX = float(os.getenv("ESPERA_MAX", "6"))      # cuánto espera a que empieces a hablar

FREQ = 16000          # whisper espera 16 kHz mono
BLOQUE = 0.1          # se analiza el audio en trozos de 100 ms

# ---------- Interpretación de lo que dijiste ----------

# Nombres exactos que entiende el firmware (emociones.h). No cambiar sin tocar el .ino.
NOMBRES_EMOCION = [
    "neutral", "feliz", "triste", "enojado", "sorprendido", "sueno",
    "enamorado", "pensando", "verguenza", "suplicando", "emocionado",
    "nervioso", "cargando",
]

# (trozos de palabra que lo activan, emoción del firmware, frase del robot)
REGLAS_EMOCION = [
    (("feliz", "alegre", "content", "buena onda", "sonri", "risa", "jubil"), "feliz", "¡Qué alegría verte!"),
    (("triste", "pena", "llorar", "decaid", "bajon", "melancol"), "triste", "Me siento un poco triste."),
    (("enojad", "enfadad", "molest", "rabia", "furi", "grr"), "enojado", "Grrr... estoy enojado."),
    (("sorpres", "asombr", "increibl", "guau", "wow", "sorprendid"), "sorprendido", "¡Guau, no me lo esperaba!"),
    (("sueno", "dormir", "cansad", "dormid", "bostezo", "somnol"), "sueno", "Tengo mucho sueño..."),
    (("enamorad", "amor", "corazon", "carino"), "enamorado", "¡Te quiero mucho!"),
    (("pensand", "pensar", "piensa", "duda"), "pensando", "Déjame pensar..."),
    (("verguenza", "timid"), "verguenza", "Me da un poco de vergüenza."),
    (("nervios", "miedo", "asustad", "ansios"), "nervioso", "Estoy un poco nervioso."),
    (("suplic",), "suplicando", "Por favor..."),    # "por favor" solo es cortesía, no una orden de cara
    (("emocionad",), "emocionado", "¡Estoy muy emocionado!"),    # no "emocion": "algo emocionante" no es una orden
    (("cargand", "cargar", "bateria", "energia"), "cargando", "Cargando energía..."),
    (("neutral", "normal", "tranquil", "serio"), "neutral", "Me quedo tranquilo."),
]

FRASES = {nombre: frase for _, nombre, frase in REGLAS_EMOCION}

# Palabras que no cuentan al medir lo larga que es la frase (el nombre del robot, cortesías).
NOMBRE_ROBOT = os.getenv("ROBOT_NOMBRE", "Robi")   # cómo se llama el robot (mismo valor que en persona.py)
PALABRAS_DE_RELLENO = {"robot", NOMBRE_ROBOT.lower(), "por", "favor", "porfa", "oye", "hey"}
# Si el niño habla de sí mismo no es una orden de cara para el robot.
HABLA_DE_SI = ("estoy", "me siento", "tengo", "me dan", "me da", "me pone", "me gusta", "yo", "mi")
# Frases que sí piden una cara.
ORDEN_DE_CARA = ("ponte", "pon cara", "pon la cara", "pon una cara", "pon tu cara", "haz cara", "hazte",
                 "cara de", "ten cara", "muestra", "estate")

# El cuello solo tiene un servo: 35 = mira arriba, 145 = mira abajo.
# Se piden frases completas para no confundir "el cielo es azul" con una orden.
REGLAS_CABEZA = [
    (("mira arriba", "mira para arriba", "mira al cielo", "mira el techo",
      "levanta la cabeza", "levanta la cara", "sube la cabeza", "cabeza arriba"), 35),
    (("mira abajo", "mira para abajo", "mira al suelo", "mira el piso",
      "baja la cabeza", "baja la cara", "cabeza abajo"), 145),
    (("al centro", "mira al centro", "mira al frente", "mira de frente",
      "mira al medio", "mira derecho", "cabeza al medio", "cabeza al centro"), 90),
    # Pedidos genéricos sin dirección: va a un ángulo al azar (None). Va al final para no tapar a los de arriba.
    (("mueve la cabeza", "mueve tu cabeza", "mueve cabeza", "gira la cabeza", "gira tu cabeza",
      "menea la cabeza", "mueve el cuello", "mueve tu cuello", "gira el cuello", "gira tu cuello"), None),
]

# "gira la cabeza a 45 grados", "pon la cabeza en 120 grados": el ángulo que se dice (el firmware limita 10 a 170).
ANGULO_DICHO = re.compile(r"(?:cabeza|cuello).*?\b(\d{2,3})\s*grados")

REGLAS_ESPECIALES = [
    (("quien eres", "como te llamas", "tu nombre"), "feliz", f"Soy {NOMBRE_ROBOT}, tu robot. ¡Mucho gusto!"),
    (("hola", "buenos dias", "buenas tardes", "buenas noches"), "feliz", "¡Hola! Me alegra escucharte."),
    (("adios", "chao", "hasta luego", "nos vemos"), "triste", "Chao, nos vemos pronto."),
    (("gracias",), "feliz", "¡De nada!"),
]

# Vocabulario que se le pasa a Whisper: los nombres propios de las emociones
# se reconocen mucho mejor si sabe de antes que existen.
PROMPT_ASR = (
    f"El niño habla con su robot, que se llama {NOMBRE_ROBOT}: «Robot, ¿me ayudas?», «Oye, Robot», «Robot {NOMBRE_ROBOT}». "
    "Comandos para un robot: ponte feliz, ponte triste, ponte enojado, "
    "sorprendido, sueño, enamorado, pensando, vergüenza, nervioso, "
    "emocionado, cargando, mira arriba, mira abajo, al centro, busca actualizaciones para ti. "
    "Cosas que dice un niño: Minecraft, Roblox, Among Us, Fortnite, Pokémon, "
    "YouTube, TikTok, WhatsApp, Lego, dinosaurios, fútbol."
)

# Palabras que Whisper debe preferir cuando suenan parecido a otra cosa.
HOTWORDS = (
    f"Robot {NOMBRE_ROBOT} Minecraft Roblox Among Us Fortnite Pokémon YouTube TikTok WhatsApp Lego actualizaciones"
)


def normalizar(texto):
    """Minúsculas y sin tildes, para comparar palabras."""
    plano = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in plano if unicodedata.category(c) != "Mn")


def _emocion_por_parecido(t):
    """Si Whisper escribió la emoción distinto, busca la más parecida."""
    for palabra in t.replace(",", " ").replace(".", " ").replace("?", " ").split():
        if len(palabra) < 4:
            continue
        # Solo nombres que empiezan con las mismas 4 letras: así "felis" llega a
        # "feliz" pero "suelo" no se confunde con "sueno".
        candidatos = [n for n in NOMBRES_EMOCION if n[:4] == palabra[:4]]
        cerca = difflib.get_close_matches(palabra, candidatos, n=1, cutoff=0.75)
        if cerca:
            return cerca[0], FRASES.get(cerca[0], "¡Listo!")
    return None, None


def interpretar(texto):
    """Convierte la frase en un comando para el robot. Devuelve {} si no entendió."""
    t = normalizar(texto)
    if not t.strip():
        return {}

    comando = {}

    dicho = ANGULO_DICHO.search(t)
    if dicho:
        comando["angulo_cuello"] = max(10, min(170, int(dicho.group(1))))
    else:
        for palabras, angulo in REGLAS_CABEZA:
            if any(p in t for p in palabras):
                comando["angulo_cuello"] = random.randint(55, 125) if angulo is None else angulo
                break

    # La frase fija de emoción solo se dice ante una orden clara. Si el niño cuenta algo suyo
    # ("me dan miedo las arañas", "estoy triste") o hace una frase larga, contesta el modelo.
    palabras_utiles = [w for w in re.findall(r"[a-z]+", t) if w not in PALABRAS_DE_RELLENO]
    habla_de_si = any(re.search(r"\b" + c + r"\b", t) for c in HABLA_DE_SI)
    es_orden = any(c in t for c in ORDEN_DE_CARA)
    corta = len(palabras_utiles) <= 3

    emocion, frase = None, None
    if not habla_de_si:
        if len(palabras_utiles) <= 3:           # "hola", "gracias", "hola Robi, ¿cómo estás?"
            for palabras, nombre, texto_voz in REGLAS_ESPECIALES:
                if any(p in t for p in palabras):
                    emocion, frase = nombre, texto_voz
                    break
        if emocion is None and (es_orden or corta):
            for palabras, nombre, texto_voz in REGLAS_EMOCION:
                if any(p in t for p in palabras):
                    emocion, frase = nombre, texto_voz
                    break
            if emocion is None and (es_orden or len(palabras_utiles) <= 2):   # errata de Whisper: "felis"
                emocion, frase = _emocion_por_parecido(t)

    if emocion:
        comando["emocion"] = emocion
        comando["mensaje_voz"] = frase

    return comando


# ---------- Audio ----------

def grabar():
    """Graba hasta que calles. Devuelve un array float32 de 16 kHz, o None."""
    input("\n🎙️  Enter para hablar (Ctrl+C para salir)...")

    if sd is None:
        raise RuntimeError("No hay micrófono: falta la librería sounddevice (o PortAudio) en este equipo.")
    tamaño = int(FREQ * BLOQUE)

    def nivel(datos):
        return float(np.sqrt(np.mean(np.square(datos))))

    with sd.InputStream(samplerate=FREQ, channels=1, dtype="float32") as flujo:
        # Mide el ruido de la sala para no confundirlo con tu voz.
        ruido = max(nivel(flujo.read(tamaño)[0]) for _ in range(6))
        umbral = max(0.010, 3.0 * ruido)
        if os.getenv("VOZ_DEBUG"):
            print(f"\n   [nivel ruido {ruido:.4f} | umbral {umbral:.4f}]", end="")

        print("   🔴 grabando...", end="", flush=True)
        trozos, hablado, silencio, transcurrido = [], False, 0.0, 0.0
        seguidos = 0          # bloques seguidos sobre el umbral

        while True:
            datos, _ = flujo.read(tamaño)
            trozos.append(datos.copy())
            transcurrido += BLOQUE

            n = nivel(datos)
            if os.getenv("VOZ_DEBUG"):
                print(f"{n:.4f} ", end="", flush=True)

            if n > umbral:
                seguidos += 1
                silencio = 0.0
                if seguidos >= 2:      # dos bloques seguidos: es voz, no un golpe
                    hablado = True
            else:
                seguidos = 0
                if hablado:
                    silencio += BLOQUE
            if (hablado and silencio >= SILENCIO_SEGUNDOS) or transcurrido >= MAX_SEGUNDOS:
                break
            if not hablado and transcurrido >= ESPERA_MAX:
                break

    print(" ✔" if hablado else " (silencio)")

    if not hablado:
        return None

    audio = np.concatenate(trozos).flatten()
    inicio = max(0, len(audio) - int((silencio + 0.2) * FREQ))   # recorta la cola
    return audio[: inicio] if inicio > FREQ // 2 else audio


_LLAMADA_SUELTA = re.compile(r"^[\s¡!¿?.,]*(?:(?:ro[bv]lo[xk]s?|rolls?|robox|robots?)[\s,.!?¡¿]*){1,5}$", re.I)


def corregir_robot(texto):
    """Si el niño dijo SOLO «Robot» (a menudo oído como «Roblox», «Rolls»…), es una llamada al robot, no el juego.
    Solo corrige cuando la frase entera es esa palabra repetida; «jugué Roblox» o «Roblox es genial» no se tocan."""
    return "Robot" if texto and _LLAMADA_SUELTA.match(texto) else texto


def transcribir(modelo, audio):
    segmentos, _ = modelo.transcribe(
        audio,               # array numpy: no pasa por ffmpeg ni por archivos
        language="es",
        beam_size=5,
        temperature=0.0,
        condition_on_previous_text=False,
        initial_prompt=PROMPT_ASR,
        hotwords=HOTWORDS,
        vad_filter=False,
    )
    partes = list(segmentos)
    if os.getenv("VOZ_DEBUG"):
        for s in partes:
            print(f"\n   [confianza {s.avg_logprob:.2f} · ruido {s.no_speech_prob:.2f}]", end="")
    return corregir_robot(" ".join(s.text.strip() for s in partes).strip())


# ---------- Servidor ----------

def enviar(comando):
    respuesta = requests.post(f"{SERVIDOR}/cmd", json=comando, timeout=10)
    respuesta.raise_for_status()
    return respuesta.json()


def conversar(texto):
    """Pide una respuesta al modelo (el puente la dice en voz alta)."""
    respuesta = requests.post(f"{SERVIDOR}/conversar", json={"texto": texto}, timeout=90)
    respuesta.raise_for_status()
    return respuesta.json()


# Caras que usa al conversar con el modelo.
CARA_PENSANDO = "pensando"
CARA_RESPUESTA = "neutral"      # cámbialo por "feliz" si prefieres que sonría al responder


def conversar_con_cara(texto):
    """Muestra cara de pensar mientras el modelo responde y vuelve a la normal.

    Si el robot no está conectado, igual conversa: los fallos de cara se ignoran.
    """
    try:
        enviar({"emocion": CARA_PENSANDO})
    except Exception:
        pass
    try:
        respuesta = conversar(texto)
        print(f"   💬 {respuesta.get('respuesta', '')}  ({respuesta.get('segundos', '?')} s)")
    except Exception as error:
        print(f"   ⚠️  No pude conversar: {error}")
        try:
            requests.post(f"{SERVIDOR}/hablar",
                          json={"texto": "Ay, me quedé pensando. ¿Me lo repites?"},
                          timeout=10)
        except Exception:
            pass
    finally:
        try:
            enviar({"emocion": CARA_RESPUESTA})
        except Exception:
            pass


def main():
    print("=" * 60)
    print("  Asistente de voz del robot")
    print("=" * 60)

    try:
        info = requests.get(f"{SERVIDOR}/", timeout=3)
        info.raise_for_status()
        info = info.json()
    except Exception:
        print(f"\n⚠️  No encuentro el servidor en {SERVIDOR}.")
        print("    Arráncalo primero en otra consola:")
        print("      voz\\iniciar_puente.bat\n")
        return 1

    if "/conversar" not in (info.get("rutas") or []):
        print("\n⚠️  El puente está con código viejo: no sabe conversar.")
        print("    Ciérralo y vuelve a abrir  voz\\iniciar_puente.bat\n")

    print(f"🧠 Cargando Whisper '{MODELO}' (la primera vez descarga el modelo)...")
    modelo = WhisperModel(MODELO, device="cpu", compute_type="int8")
    print("✅ Listo. Di «ponte feliz», «mira arriba» o cualquier pregunta.")

    while True:
        try:
            audio = grabar()
        except KeyboardInterrupt:
            print("\n👋 Hasta luego.")
            return 0

        if audio is None:
            continue

        texto = transcribir(modelo, audio)
        if not texto:
            print("   (no entendí nada)\n")
            continue

        print(f"👤 {texto}")

        palabras = normalizar(texto).split()
        if len(palabras) <= 3 and any(p in palabras for p in ("salir", "terminar", "apagar")):
            print("👋 Hasta luego.")
            return 0

        if any(p in normalizar(texto) for p in ("olvidalo", "olvida eso", "borra la memoria",
                                               "olvida la conversacion")):
            try:
                requests.post(f"{SERVIDOR}/olvidar", timeout=5)
                print("   🧽 Olvidé la conversación.")
            except Exception as error:
                print(f"   ⚠️  No pude borrar la memoria: {error}")
            continue

        comando = interpretar(texto)

        if not comando:
            # No es una orden conocida: pone cara de pensar, contesta el modelo
            # y después vuelve a la cara normal.
            conversar_con_cara(texto)
            continue

        try:
            respuesta = enviar(comando)
            enviado = ", ".join(f"{k}={v}" for k, v in comando.items())
            print(f"   📤 {enviado}")

            dijo = respuesta.get("robot_dijo") or []
            if dijo:
                for linea in dijo:
                    print(f"   🤖 {linea}")
                if any("No conozco" in l for l in dijo):
                    print("   ⚠️  El robot no conoce esa emoción (revisa emociones.h).")
            elif "emocion" in comando:
                print("   ⚠️  El robot no confirmó nada: ¿está conectado el cable?")
        except Exception as e:
            print(f"   ⚠️  No pude hablar con el servidor: {e}")


if __name__ == "__main__":
    sys.exit(main())
