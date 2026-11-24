#!/usr/bin/env python3
"""Plano de conjunto de la version escritorio (SVG)."""

from __future__ import annotations

import math
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PARAMS = RAIZ / "parametros.scad"
SALIDA = Path(__file__).resolve().parent / "conjunto.svg"

S = 2.0
TINTA = "#1d1d1d"
AZUL = "#2f5d8a"
GRIS = "#8f8f8f"
ORUGA = "#d9d9d9"


def leer() -> dict[str, float]:
    vals: dict[str, float] = {}
    for linea in PARAMS.read_text(encoding="utf-8").splitlines():
        linea = linea.split("//")[0].strip()
        m = re.match(r"([A-Za-z_]\w*)\s*=\s*([^;]+);", linea)
        if not m:
            continue
        try:
            vals[m.group(1)] = float(eval(m.group(2), {"__builtins__": {}}, {"math": math, "PI": math.pi, **vals}))
        except Exception:
            pass
    return vals


P = leer()
ALTO = P["CAB_Z0"] + P["CAB_Z"]
BASE_TOP = P["BASE_Z"] + P["TAPA"]
PLATO_Z = P["PLATO_Z"]
CAB_Z0 = P["CAB_Z0"]
FRENTE = P["CAB_Y"] / 2
FONDO = -P["CAB_Y"] / 2 - 3


def fnum(v: float, dec: int = 1) -> str:
    s = f"{v:.{dec}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s.replace(".", ",")


class D:
    def __init__(self):
        self.e = ['<?xml version="1.0" encoding="UTF-8"?>',
                  '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="950" viewBox="0 0 1200 950">',
                  '<rect width="1200" height="950" fill="#fff"/>']

    def l(self, x1, y1, x2, y2, c=TINTA, w=1.2, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.e.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{c}" stroke-width="{w}"{d}/>')

    def r(self, x1, y1, x2, y2, fill="#fff", c=TINTA, w=1.2, rx=0, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.e.append(f'<rect x="{min(x1,x2):.1f}" y="{min(y1,y2):.1f}" width="{abs(x2-x1):.1f}" height="{abs(y2-y1):.1f}" rx="{rx:.1f}" fill="{fill}" stroke="{c}" stroke-width="{w}"{d}/>')

    def c(self, x, y, r, fill="none", c=TINTA, w=1.2, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.e.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{fill}" stroke="{c}" stroke-width="{w}"{d}/>')

    def t(self, x, y, txt, size=13, c=TINTA, anchor="start", bold=False):
        w = ' font-weight="bold"' if bold else ""
        self.e.append(f'<text x="{x:.1f}" y="{y:.1f}" font-family="Segoe UI, Arial, sans-serif" font-size="{size}" fill="{c}" text-anchor="{anchor}"{w} paint-order="stroke" stroke="#fff" stroke-width="4">{txt}</text>')

    def ch(self, x1, x2, y, txt, arriba=True, c=AZUL):
        self.l(x1, y, x2, y, c, 1)
        for x in (x1, x2):
            self.l(x, y - 4, x, y + 4, c, 1)
        self.t((x1 + x2) / 2, y - 7 if arriba else y + 16, txt, 12, c, "middle")

    def cv(self, x, y1, y2, txt, c=AZUL, lado="der"):
        self.l(x, y1, x, y2, c, 1)
        for y in (y1, y2):
            self.l(x - 4, y, x + 4, y, c, 1)
        if lado == "der":
            self.t(x + 7, (y1 + y2) / 2 + 4, txt, 12, c)
        else:
            self.t(x - 7, (y1 + y2) / 2 + 4, txt, 12, c, "end")

    def guardar(self):
        self.e.append("</svg>")
        SALIDA.write_text("\n".join(self.e), encoding="utf-8")


d = D()

# fondo cuadriculado
for x in range(0, 1200, 20):
    d.l(x, 0, x, 780, "#f3f3f3", 0.4)
for y in range(0, 780, 20):
    d.l(0, y, 1200, y, "#f3f3f3", 0.4)

# =====================================================================
#  FRONTAL
# =====================================================================
CX, GY = 270, 720
X = lambda x: CX + x * S
Y = lambda z: GY - z * S


def fr(x1, x2, z1, z2, **kw):
    d.r(X(x1), Y(z2), X(x2), Y(z1), **kw)


# suelo
d.l(110, GY, 430, GY, TINTA, 2)
for x in range(120, 430, 16):
    d.l(x, GY, x - 8, GY + 8, "#777", 0.6)

# base y cajon
fr(-P["BASE_X"] / 2, P["BASE_X"] / 2, 0, P["BASE_Z"], fill="#eeeeee")
fr(-111 / 2 - 0.5, 111 / 2 + 0.5, 2.4, 34.4, fill="#dcdcdc")
fr(-15, 15, 30.4, 34.4, fill="#eeeeee", c="#777", w=0.8)
d.t(X(0), Y(20), "cajón", 11, "#555", "middle")

# tapa, anillo y plato
fr(-P["BASE_X"] / 2, P["BASE_X"] / 2, P["BASE_Z"], BASE_TOP, fill="#f7f7f7")
fr(-P["ANILLO_D"] / 2, P["ANILLO_D"] / 2, BASE_TOP, BASE_TOP + P["ANILLO_H"], fill="#e2e2e2")
fr(-P["PLATO"] / 2, P["PLATO"] / 2, PLATO_Z, PLATO_Z + P["PLATO_T"], fill="#e8e8e8")
fr(-P["LIP_D"] / 2, P["LIP_D"] / 2, PLATO_Z - 3, PLATO_Z, fill="#e8e8e8")

# cabeza
fr(-P["CAB_X"] / 2, P["CAB_X"] / 2, CAB_Z0, CAB_Z0 + P["CAB_Z"], fill="#fbfbfb", w=1.5)

# OLED y parlante
fr(-P["VENT_W"] / 2, P["VENT_W"] / 2,
   CAB_Z0 + P["OLED_Z"] - P["VENT_H"] / 2,
   CAB_Z0 + P["OLED_Z"] + P["VENT_H"] / 2, fill="#fff", w=1.2)
spx, spy = X(0), Y(CAB_Z0 + P["PARLANTE_Z"])
d.c(spx, spy, P["PARLANTE_D"] / 2 * S, "#f3f3f3", "#444", 1.2)
for r in (5, 11, 17):
    for a in range(0, 360, 30):
        d.c(spx + math.cos(math.radians(a)) * r * S, spy + math.sin(math.radians(a)) * r * S, 1.5 * S, "#fff", "#888", 0.6)

# tacto arriba
d.c(X(P["PAD_X"]), Y(CAB_Z0 + P["CAB_Z"]), P["PAD_D"] / 2 * S, "none", "#888", 0.8, "3 2")

# cotas
d.ch(X(-P["BASE_X"] / 2), X(P["BASE_X"] / 2), GY + 40, f"{fnum(P["BASE_X"],0)}", arriba=False)
d.ch(X(-P["CAB_X"] / 2), X(P["CAB_X"] / 2), Y(ALTO) - 46, f"{fnum(P["CAB_X"],0)}")
d.cv(455, Y(0), Y(ALTO), f"{fnum(ALTO,0)}")
d.cv(100, Y(0), Y(P["BASE_Z"]), f"{fnum(P["BASE_Z"],0)}", lado="izq")
d.cv(100, Y(CAB_Z0), Y(ALTO), f"{fnum(P["CAB_Z"],0)}", lado="izq")
d.ch(X(-P["PARLANTE_D"] / 2), X(P["PARLANTE_D"] / 2), spy + 55, f"{fnum(P["PARLANTE_D"],0)}")
d.t(X(0) + 32, Y(CAB_Z0 + P["OLED_Z"]) - 2, f'{fnum(P["VENT_W"],0)} × {fnum(P["VENT_H"],1)}', 11, "#555")
d.t(X(0) + 58, spy + 4, "parlante", 11, "#555")
d.t(X(P["PAD_X"]) + 38, Y(ALTO) + 4, "tacto 30", 11, "#555")
d.t(X(0), Y(CAB_Z0 + P["OLED_Z"]) - 25, "OLED 0,96\"", 11, "#555", "middle")

# =====================================================================
#  LATERAL
# =====================================================================
CX2 = 650
X2 = lambda y: CX2 + y * S


def sd(y1, y2, z1, z2, **kw):
    d.r(X2(y1), Y(z2), X2(y2), Y(z1), **kw)


d.l(500, GY, 800, GY, TINTA, 2)
for x in range(510, 800, 16):
    d.l(x, GY, x - 8, GY + 8, "#777", 0.6)

sd(-P["BASE_Y"] / 2, P["BASE_Y"] / 2, 0, P["BASE_Z"], fill="#eeeeee")
sd(-3, 65, 2.4, 34.4, fill="#dcdcdc")
sd(-P["BASE_Y"] / 2, P["BASE_Y"] / 2, P["BASE_Z"], BASE_TOP, fill="#f7f7f7")
sd(-P["ANILLO_D"] / 2, P["ANILLO_D"] / 2, BASE_TOP, BASE_TOP + P["ANILLO_H"], fill="#e2e2e2")
sd(-P["PLATO"] / 2, P["PLATO"] / 2, PLATO_Z, PLATO_Z + P["PLATO_T"], fill="#e8e8e8")

# cabeza
sd(FONDO, FRENTE, CAB_Z0, CAB_Z0 + P["CAB_Z"], fill="#fbfbfb", w=1.5)
sd(-P["CAB_Y"] / 2 - 3, -P["CAB_Y"] / 2, CAB_Z0, CAB_Z0 + P["CAB_Z"], fill="#e6e6e6")

# parlante y OLED de perfil
sd(P["CAB_Y"] / 2 - 20, P["CAB_Y"] / 2, CAB_Z0 + P["PARLANTE_Z"] - 20,
   CAB_Z0 + P["PARLANTE_Z"] + 20, fill="#f2f2f2", dash="3 2")
d.l(X2(P["CAB_Y"] / 2), Y(CAB_Z0 + P["OLED_Z"] - P["VENT_H"] / 2),
    X2(P["CAB_Y"] / 2), Y(CAB_Z0 + P["OLED_Z"] + P["VENT_H"] / 2), "#333", 2)

# ESP32 y bandeja
sd(-31, 24.5, 49, 77.5, fill="none", c="#3b7a3b", w=1, dash="3 2")
d.t(X2(-2), Y(CAB_Z0 + 74), "ESP32", 10, "#3b7a3b", "middle")

# cotas
d.ch(X2(-P["BASE_Y"] / 2), X2(P["BASE_Y"] / 2), GY + 40, f"{fnum(P["BASE_Y"],0)}", arriba=False)
d.ch(X2(FONDO), X2(FRENTE), Y(ALTO) - 22, f"{fnum(FRENTE - FONDO,0)}")
d.cv(825, Y(0), Y(ALTO), f"{fnum(ALTO,0)}")
d.cv(825, Y(P["BASE_Z"]), Y(BASE_TOP), f"{fnum(P["TAPA"],0)}")
d.ch(X2(-3), X2(65), Y(34.4) + 26, f"{fnum(68,0)}")
d.t(X2(-40), Y(20), "cajón", 11, "#555", "end")
d.t(X2(0), Y(CAB_Z0 + 48), "cabeza", 11, "#555", "middle")
d.t(X2(-52), Y(CAB_Z0 + 45), "panel", 11, "#555", "end")

# =====================================================================
#  SUPERIOR
# =====================================================================
CX3, CY3 = 1010, 390
X3 = lambda x: CX3 + x * S
Y3 = lambda y: CY3 + y * S


def sp(x1, x2, y1, y2, **kw):
    d.r(X3(x1), Y3(y1), X3(x2), Y3(y2), **kw)


# base
sp(-P["BASE_X"] / 2, P["BASE_X"] / 2, -P["BASE_Y"] / 2, P["BASE_Y"] / 2, fill="#eeeeee")
# cajon
sp(-111 / 2, 111 / 2, -3, 65, fill="#dcdcdc")
# cabeza
sp(-P["CAB_X"] / 2, P["CAB_X"] / 2, -P["CAB_Y"] / 2, P["CAB_Y"] / 2, fill="#fbfbfb", w=1.5)
# plato / anillo (ocultos)
sp(-P["PLATO"] / 2, P["PLATO"] / 2, -P["PLATO"] / 2, P["PLATO"] / 2, fill="none", c="#999", w=0.8, rx=4, dash="4 3")
# parlante al frente
d.c(X3(0), Y3(P["CAB_Y"] / 2), P["PARLANTE_D"] / 2 * S, "none", "#888", 0.8, "3 2")
# OLED / tacto
d.c(X3(P["PAD_X"]), Y3(0), P["PAD_D"] / 2 * S, "none", "#888", 0.8, "3 2")
d.l(X3(-P["VENT_W"] / 2), Y3(P["CAB_Y"] / 2), X3(P["VENT_W"] / 2), Y3(P["CAB_Y"] / 2), "#333", 2)
# micro
d.c(X3(-P["CAB_X"] / 2), Y3(P["MIC_Y"]), 2 * S, "#fff", "#c07030", 1.2)
d.t(X3(-P["CAB_X"] / 2) - 8, Y3(P["MIC_Y"]) + 4, "micro", 11, "#a35a20", "end")

# cotas
d.ch(X3(-P["BASE_X"] / 2), X3(P["BASE_X"] / 2), Y3(-P["BASE_Y"] / 2) - 18, f"{fnum(P["BASE_X"],0)}")
d.ch(X3(-P["CAB_X"] / 2), X3(P["CAB_X"] / 2), Y3(-P["CAB_Y"] / 2) - 38, f"{fnum(P["CAB_X"],0)}")
d.cv(1160, Y3(-P["BASE_Y"] / 2), Y3(P["BASE_Y"] / 2), f"{fnum(P["BASE_Y"],0)}")
d.cv(1135, Y3(-P["CAB_Y"] / 2), Y3(P["CAB_Y"] / 2), f"{fnum(P["CAB_Y"],0)}")
d.t(X3(0), Y3(72), "cajón", 11, "#555", "middle")
d.t(X3(0), Y3(-50), "chasis", 11, "#555", "middle")
d.t(X3(0), Y3(10), "cabeza", 11, "#555", "middle")


# =====================================================================
#  TITULO
# =====================================================================
d.r(40, 790, 1160, 920, "#fff", TINTA, 1.3)
d.l(820, 790, 820, 920, "#999", 1)
d.t(60, 820, "KIDS ROBOT — ESCRITORIO v1", 24, TINTA, bold=True)
d.t(60, 847, "Base con batería y servo + cabeza con OLED, parlante, micro y tacto", 13, "#333")
d.t(60, 870, f"{fnum(P["BASE_X"],0)} × {fnum(P["BASE_Y"],0)} × {fnum(ALTO,0)} mm · 7 piezas impresas + calibración", 13, "#333")
d.t(60, 893, "Batería: power bank 100 × 62 × 16 o pack 2S 18650 + buck 5 V. Sin ruedas ni cuerpo.", 12, "#555")
d.t(840, 820, "v1 · 2026-10-31", 13, TINTA, bold=True)
d.t(840, 845, "Plano de conjunto · cotas mm", 12, "#333")
d.t(840, 868, "Modelo orientativo: las piezas", 12, "#555")
d.t(840, 888, "salen de escritorio.scad.", 12, "#555")
d.t(60, 910, "Antes de imprimir todo: calibración + un plato + la base. Medir servo, OLED y parlante.", 11, "#7a2e2e")

d.guardar()
print("Listo:", SALIDA)
