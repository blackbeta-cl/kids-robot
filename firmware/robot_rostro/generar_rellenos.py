"""Genera firmware/robot_rostro/rellenos.h: interjecciones cortas («a ver…», «veamos…») con la voz del robot.

El robot toca una de ellas apenas termina de enviar el audio, mientras el servidor transcribe y piensa.
No baja la latencia real, pero evita el silencio de 2 a 5 s que un niño nota más que nada.

Se ejecuta desde un PC con las dependencias de server/requirements.txt (edge-tts, numpy, soundfile).
Usa los mismos ajustes de voz que el servidor (VOZ_TTS, VOZ_TONO, VOZ_RITMO, VOZ_ROBOT): si los cambias allí, regenera esto.
"""
import os
import sys
import tempfile

import numpy as np
import soundfile as sf

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(BASE, "server"))
from voz_robot import sello_robot, sintetizar   # noqa: E402

SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rellenos.h")
TEXTOS = ["A ver...", "Veamos...", "Pues..."]
VOZ = os.getenv("VOZ_TTS", "es-CL-CatalinaNeural")
TONO = os.getenv("VOZ_TONO", "+35Hz")
RITMO = os.getenv("VOZ_RITMO", "+6%")
ROBOT = max(0.0, min(1.0, float(os.getenv("VOZ_ROBOT", "0.45"))))


def clip(texto, indice):
    mp3 = os.path.join(tempfile.gettempdir(), f"relleno_{indice}.mp3")
    sintetizar(texto, mp3, VOZ, TONO, RITMO)
    datos, tasa = sf.read(mp3, dtype="float32")
    if datos.ndim > 1:
        datos = datos.mean(axis=1)
    datos = sello_robot(datos, tasa, ROBOT)
    fuerte = np.flatnonzero(np.abs(datos) > 0.004)            # recorta el silencio que agrega el TTS
    if len(fuerte):
        datos = datos[max(0, fuerte[0] - int(tasa * 0.02)):fuerte[-1] + int(tasa * 0.05)]
    datos = np.concatenate([datos, np.zeros(int(tasa * 0.05), dtype=np.float32)])
    datos = datos / (float(np.max(np.abs(datos))) or 1.0) * 0.92
    wav = os.path.join(tempfile.gettempdir(), f"relleno_{indice}.wav")
    sf.write(wav, datos, tasa, subtype="PCM_16")
    return open(wav, "rb").read(), len(datos) / tasa


def main():
    clips = [clip(t, i) for i, t in enumerate(TEXTOS)]
    with open(SALIDA, "w", encoding="utf-8", newline="\n") as f:
        f.write("// Generado por generar_rellenos.py: " + ", ".join("«%s»" % t for t in TEXTOS) + ".\n")
        f.write("// No editar a mano; regenerar si cambia la voz o los textos.\n")
        f.write("#pragma once\n#include <stdint.h>\n\n")
        for i, (datos, _) in enumerate(clips):
            f.write(f"const char RELLENO_{i}_WAV[] =\n")
            for j in range(0, len(datos), 32):
                f.write('  "' + "".join("\\x%02x" % b for b in datos[j:j + 32]) + '"\n')
            f.write(";\n")
        f.write(f"\nconst unsigned int RELLENOS_N = {len(clips)};\n")
        f.write("const char* const RELLENOS_WAV[] = {" + ", ".join(f"RELLENO_{i}_WAV" for i in range(len(clips))) + "};\n")
        f.write("const unsigned int RELLENOS_LEN[] = {" +
                ", ".join(f"sizeof(RELLENO_{i}_WAV) - 1" for i in range(len(clips))) + "};\n")
    for t, (datos, seg) in zip(TEXTOS, clips):
        print(f"{t!r}: {len(datos)} bytes, {seg:.2f} s")
    print(f"{SALIDA}: {os.path.getsize(SALIDA)} bytes de fuente")


if __name__ == "__main__":
    main()
