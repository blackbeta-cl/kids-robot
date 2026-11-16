#!/usr/bin/env python3
"""Exporta las piezas de escritorio.scad a STL."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SCAD = RAIZ / "escritorio.scad"
STL = RAIZ / "stl"

PIEZAS = [
    ("base", 1),
    ("tapa_base", 1),
    ("cajon", 1),
    ("plato_giro", 1),
    ("cabeza", 1),
    ("tapa_cabeza", 1),
    ("rejilla", 1),
    ("calibracion", 1),
]


def buscar() -> str | None:
    env = os.environ.get("OPENSCAD")
    if env and Path(env).exists():
        return env
    for nombre in ("openscad.com", "openscad.exe", "openscad"):
        r = shutil.which(nombre)
        if r:
            return r
    for ruta in (
        Path(r"C:\Program Files\OpenSCAD\openscad.exe"),
        Path(r"C:\Program Files (x86)\OpenSCAD\openscad.exe"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "OpenSCAD" / "openscad.exe",
    ):
        if ruta.is_file():
            return str(ruta)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--openscad")
    ap.add_argument("--solo")
    args = ap.parse_args()

    exe = args.openscad or buscar()
    if not exe or not Path(exe).is_file():
        print("No encuentro OpenSCAD. Instálalo desde https://openscad.org")
        print('o usa: python exportar_stl.py --openscad "C:\\...\\openscad.exe"')
        return 1

    STL.mkdir(exist_ok=True)
    solo = {p.strip() for p in args.solo.split(",")} if args.solo else None
    piezas = [p for p in PIEZAS if solo is None or p[0] in solo]

    print(f"OpenSCAD: {exe}\nSalida:   {STL}\n")
    errores = []
    for nombre, cant in piezas:
        salida = STL / f"{nombre}.stl"
        print(f"[{nombre}] ... ", end="", flush=True)
        r = subprocess.run(
            [exe, "-D", f'PARTE="{nombre}"', "-o", str(salida), str(SCAD)],
            capture_output=True, text=True,
        )
        texto = (r.stdout or "") + (r.stderr or "")
        if r.returncode != 0 or not salida.is_file() or salida.stat().st_size < 1000:
            print("ERROR")
            errores.append((nombre, texto.strip()[-800:]))
        else:
            print(f"OK ({salida.stat().st_size/1024:.0f} KB)")

    if errores:
        print("\nFallaron:")
        for n, t in errores:
            print(f"\n--- {n} ---\n{t}")
        return 1
    print("\nListo:", STL)
    return 0


if __name__ == "__main__":
    sys.exit(main())
