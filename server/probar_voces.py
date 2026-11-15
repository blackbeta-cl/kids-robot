"""Escucha varias voces para el robot y elige la que más te guste.

Genera la misma frase con distintas voces y efectos, las guarda en muestras/
y las reproduce en orden. Después se cambia la elegida con variables de entorno
(en puente.py o en el .env).
"""

import argparse
import sys
from pathlib import Path

from voz_robot import preparar_wav, reproducir, sintetizar

FRASE = (
    "Hola, soy tu robot. ¿Qué quieres que dibuje en mi cara hoy? "
    "Te puedo contar un chiste o mostrar la hora."
)

# (archivo, voz, tono, ritmo, robot, descripción)
VARIANTES = [
    ("01_como_estaba", "es-CL-CatalinaNeural", "+0Hz", "+0%", 0.0, "como estaba antes"),
    ("02_infantil", "es-CL-CatalinaNeural", "+35Hz", "+6%", 0.0, "más aguda, sin efecto"),
    ("03_robot_suave", "es-CL-CatalinaNeural", "+35Hz", "+6%", 0.45, "la que dejé puesta"),
    ("04_robot_marcado", "es-CL-CatalinaNeural", "+30Hz", "+4%", 0.80, "más metálica"),
    ("05_nino", "es-CL-LorenzoNeural", "+60Hz", "+6%", 0.45, "voz masculina subida de tono"),
    ("06_otro_acento", "es-MX-DaliaNeural", "+35Hz", "+6%", 0.45, "acento mexicano"),
]

for _flujo in (sys.stdout, sys.stderr):
    if hasattr(_flujo, "reconfigure"):
        try:
            _flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Escuchar voces para el robot.")
    parser.add_argument("--solo", type=int, help="reproducir solo la variante N (1-6)")
    parser.add_argument("--sin-audio", action="store_true", help="generar sin reproducir")
    args = parser.parse_args()

    carpeta = Path(__file__).resolve().parent / "muestras"
    carpeta.mkdir(exist_ok=True)

    elegidas = VARIANTES
    if args.solo:
        elegidas = [VARIANTES[args.solo - 1]]

    print("=" * 64)
    print("  Voces del robot — se guardan en muestras/")
    print("=" * 64)

    for numero, (nombre, voz, tono, ritmo, fuerza, descripcion) in enumerate(VARIANTES, start=1):
        if (nombre, voz, tono, ritmo, fuerza, descripcion) not in elegidas:
            continue
        mp3 = carpeta / f"{nombre}.mp3"
        wav = carpeta / f"{nombre}.wav"
        print(f"\n[{numero}] {descripcion}")
        print(f"     {voz} · tono {tono} · ritmo {ritmo} · robot {fuerza}")
        try:
            sintetizar(FRASE, str(mp3), voz, tono, ritmo)
            if fuerza > 0:
                preparar_wav(str(mp3), str(wav), fuerza)
                suena = wav
                mp3.unlink(missing_ok=True)      # el mp3 ya no hace falta
            else:
                suena = mp3
            print(f"     guardado en {suena.name}")
            if not args.sin_audio:
                reproducir(str(suena), "waveaudio" if suena.suffix == ".wav" else "mpegvideo")
        except Exception as error:
            print(f"     [FALLA] {error}")

    print("\n" + "=" * 64)
    print("  Para quedarte con otra: en iniciar_puente.bat, antes de arrancar,")
    print("  define VOZ_TTS, VOZ_TONO, VOZ_RITMO y VOZ_ROBOT con los valores")
    print("  de la variante elegida. Ejemplo:")
    print('    set VOZ_TTS=es-CL-CatalinaNeural')
    print('    set VOZ_TONO=+35Hz')
    print('    set VOZ_RITMO=+6%')
    print('    set VOZ_ROBOT=0.45')
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
