"""Genera firmware/robot_rostro/anuncio_ota.h: tres beeps + voz para los avisos de OTA.

Se ejecuta desde un PC con las dependencias de server/requirements.txt (edge-tts, numpy, soundfile).
"""
import os
import sys
import tempfile

import numpy as np
import soundfile as sf

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(BASE, "server"))
from voz_robot import sello_robot, sintetizar   # noqa: E402

SR = 16000
SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "anuncio_ota.h")
WAV = os.path.join(tempfile.gettempdir(), "anuncio_ota.wav")
TEXTO = "Actualizando en tres, dos, uno."


def beep(frecuencia=880.0, duracion=0.16, amplitud=0.25):
    n = int(SR * duracion)
    t = np.arange(n) / SR
    fundido = int(SR * 0.01)
    env = np.ones(n, dtype=np.float32)
    env[:fundido] = np.linspace(0, 1, fundido, dtype=np.float32)
    env[-fundido:] = np.linspace(1, 0, fundido, dtype=np.float32)
    return (amplitud * np.sin(2 * np.pi * frecuencia * t) * env).astype(np.float32)


def voz():
    mp3 = os.path.join(tempfile.gettempdir(), "anuncio_ota.mp3")
    sintetizar(TEXTO, mp3, "es-CL-CatalinaNeural", "+35Hz", "+6%")
    datos, tasa = sf.read(mp3, dtype="float32")
    if datos.ndim > 1:
        datos = datos.mean(axis=1)
    if tasa != SR:
        n = int(len(datos) * SR / tasa)
        datos = np.interp(np.linspace(0, len(datos) - 1, n), np.arange(len(datos)), datos).astype(np.float32)
    datos = sello_robot(datos, SR, 0.45)
    # Recorta el silencio inicial y final que agrega el TTS.
    fuerte = np.flatnonzero(np.abs(datos) > 0.004)
    if len(fuerte):
        datos = datos[max(0, fuerte[0] - int(SR * 0.02)):fuerte[-1] + int(SR * 0.05)]
    return datos.astype(np.float32)


def main():
    pausa = np.zeros(int(SR * 0.12), dtype=np.float32)
    tres = np.concatenate([beep(), pausa, beep(), pausa, beep(), np.zeros(int(SR * 0.25), dtype=np.float32)])
    audio = np.concatenate([np.zeros(int(SR * 0.10), dtype=np.float32), tres, voz(),
                            np.zeros(int(SR * 0.25), dtype=np.float32)])
    pico = float(np.max(np.abs(audio))) or 1.0
    audio = audio / pico * 0.92
    sf.write(WAV, audio, SR, subtype="PCM_16")
    datos = open(WAV, "rb").read()

    with open(SALIDA, "w", encoding="utf-8", newline="\n") as f:
        f.write("// Generado por generar_anuncio_ota.py: tres beeps + «Actualizando en tres, dos, uno».\n")
        f.write("// No editar a mano; regenerar si cambia la voz o el texto.\n")
        f.write("#pragma once\n#include <stdint.h>\n\n")
        f.write("const char ANUNCIO_OTA_WAV[] =\n")
        for i in range(0, len(datos), 32):
            f.write('  "' + "".join("\\x%02x" % b for b in datos[i:i + 32]) + '"\n')
        f.write(";\n")
        f.write("const unsigned int ANUNCIO_OTA_WAV_LEN = sizeof(ANUNCIO_OTA_WAV) - 1;\n")
    print(f"{WAV}: {len(datos)} bytes, {len(audio) / SR:.2f} s")
    print(f"{SALIDA}: {os.path.getsize(SALIDA)} bytes de fuente")


if __name__ == "__main__":
    main()
