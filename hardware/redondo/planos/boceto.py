#!/usr/bin/env python3
"""Dibuja el boceto del robot "redondo" (planos/boceto.svg).

Usa las mismas curvas que robot.scad (copiadas de parametros.scad), asi que
las proporciones del dibujo son las del modelo 3D.
"""

from __future__ import annotations

import math
from pathlib import Path

SALIDA = Path(__file__).resolve().parent / "boceto.svg"

# --- medidas (iguales a parametros.scad) ---
C_A, C_B, C_N, C_HS, C_Z0, C_TOP = 64, 54, 2.5, 108, 3, 96
H_A, H_B, H_N, H_RIM, H_A0, H_B0, H_ZC, H_HD, H_TOP, H_CARA = 56, 47, 2.6, 115, 40, 34, 131, 65, 194, 42
DISCO_R, PISO_Z, TUBO_TOP = 26, 112, 110


def f_cuerpo(z: float) -> float:
    return (1 - (z / C_HS) ** C_N) ** (1 / C_N)


def cupula(z: float) -> float:
    if z <= H_ZC:
        return 1.0
    t = min((z - H_ZC) / H_HD, 1.0)
    return (1 - t ** H_N) ** (1 / H_N)


def menton(z: float, full: float, base: float) -> float:
    """Curva del menton: sale a 45 grados del borde y termina vertical."""
    d = full - base
    s = min(max((z - H_RIM) / (2 * d), 0.0), 1.0)
    return full - d * (1 - s) ** 2


def cabeza_a(z: float) -> float:
    return min(menton(z, H_A, H_A0), H_A * cupula(z))


def cabeza_b(z: float) -> float:
    return min(menton(z, H_B, H_B0), H_B * cupula(z))


def rango(a: float, b: float, n: int = 60):
    return [a + (b - a) * i / n for i in range(n + 1)]


S = 2.4  # px por mm


class Vista:
    def __init__(self, ox: float, oy: float):
        self.ox, self.oy = ox, oy

    def p(self, x: float, z: float) -> str:
        return f"{self.ox + x * S:.1f},{self.oy - z * S:.1f}"

    def silueta(self, izq, der, zs) -> str:
        pts = [self.p(der(z), z) for z in zs] + [self.p(izq(z), z) for z in reversed(zs)]
        return "M" + " L".join(pts) + " Z"

    def rect(self, x0, z0, x1, z1, clase, r=0) -> str:
        x, y = self.ox + min(x0, x1) * S, self.oy - max(z0, z1) * S
        w, h = abs(x1 - x0) * S, abs(z1 - z0) * S
        return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r * S:.1f}" class="{clase}"/>'

    def circ(self, x, z, r, clase) -> str:
        return f'<circle cx="{self.ox + x * S:.1f}" cy="{self.oy - z * S:.1f}" r="{r * S:.1f}" class="{clase}"/>'

    def texto(self, x, z, t, clase="et", anchor="start") -> str:
        return f'<text x="{self.ox + x * S:.1f}" y="{self.oy - z * S:.1f}" class="{clase}" text-anchor="{anchor}">{t}</text>'

    def flecha(self, x0, z0, x1, z1) -> str:
        return (f'<line x1="{self.ox + x0 * S:.1f}" y1="{self.oy - z0 * S:.1f}" '
                f'x2="{self.ox + x1 * S:.1f}" y2="{self.oy - z1 * S:.1f}" class="guia"/>'
                f'{self.circ(x1, z1, 0.9, "punto")}')


def vista_frente(v: Vista) -> list[str]:
    o = []
    zc = rango(C_Z0, C_TOP)
    zh = rango(H_RIM, H_TOP, 80)
    # base
    o.append(v.rect(-62.8, 0, 62.8, C_Z0, "base", 1))
    # cuerpo
    o.append(f'<path d="{v.silueta(lambda z: -C_A * f_cuerpo(z), lambda z: C_A * f_cuerpo(z), zc)}" class="cuerpo"/>')
    # barriga: rejilla del parlante
    o.append(v.circ(0, 33, 21, "rejilla"))
    for r, n in ((0, 1), (6, 6), (12, 12), (18, 18)):
        for i in range(n):

            a = 2 * math.pi * i / n
            o.append(v.circ(r * math.cos(a), 33 + r * math.sin(a), 1.5, "hoyo"))
    # cuello
    o.append(v.rect(-DISCO_R, C_TOP, DISCO_R, TUBO_TOP, "cuello", 1.5))
    o.append(v.rect(-H_A0 + 0.3, PISO_Z, H_A0 - 0.3, H_RIM, "piso", 1))
    # cabeza
    o.append(f'<path d="{v.silueta(lambda z: -cabeza_a(z), cabeza_a, zh)}" class="cabeza"/>')
    # orejas
    for s in (-1, 1):
        o.append(v.rect(s * 55, 139, s * 61, 161, "oreja", 3))
    # visor y cara
    o.append(v.rect(-25, 132, 25, 168, "visor", 7))
    o.append(v.circ(0, 76, 11.5, "pir"))
    o.append(v.circ(0, 163, 5, "lente"))
    o.append(v.circ(0, 163, 1.6, "ojo"))
    o.append(v.rect(25.5, 144, 30.5, 148, "mic", 1))
    o.append(v.rect(-12.25, 139.5, 12.25, 152.5, "oled", 1))
    for s in (-1, 1):
        o.append(f'<ellipse cx="{v.ox + s * 5.5 * S:.1f}" cy="{v.oy - 147 * S:.1f}" rx="{2.4 * S:.1f}" ry="{3.2 * S:.1f}" class="ojo"/>')
    o.append(f'<path d="M{v.p(-3.5, 142.5)} Q{v.p(0, 140)} {v.p(3.5, 142.5)}" class="boca"/>')
    o.append(v.circ(-28, 146, 1.2, "mic"))
    # mejillas
    for s in (-1, 1):
        o.append(f'<ellipse cx="{v.ox + s * 34 * S:.1f}" cy="{v.oy - 138 * S:.1f}" rx="{6 * S:.1f}" ry="{3 * S:.1f}" class="mejilla"/>')
    # boton (zona de arriba)
    o.append(f'<path d="M{v.p(-21, H_TOP + 0.2)} L{v.p(21, H_TOP + 0.2)}" class="boton"/>')
    # etiquetas
    o.append(v.flecha(-70, 203, -14, H_TOP))
    o.append(v.texto(-70, 205, "toda la cabeza es el botón", "et", "start"))
    o.append(v.flecha(70, 172, 24, 160))
    o.append(v.texto(70, 174, "visor negro + OLED (cara)", "et", "end"))
    o.append(v.flecha(-80, 128, -29, 145))
    o.append(v.texto(-80, 124, "micrófono", "et", "start"))
    o.append(v.flecha(80, 128, 30, 145))
    o.append(v.texto(80, 124, "sensor de distancia IR", "et", "end"))
    o.append(v.flecha(80, 190, 5, 165))
    o.append(v.texto(80, 192, "cámara ESP32-CAM", "et", "end"))
    o.append(v.flecha(78, 84, 11, 78))
    o.append(v.texto(78, 86, "PIR: detecta movimiento", "et", "end"))
    o.append(v.flecha(-80, 172, -58, 155))
    o.append(v.texto(-80, 174, "orejitas (otro color)", "et", "start"))
    o.append(v.flecha(-80, 104, -20, 104))
    o.append(v.texto(-80, 106, "cuello: gira ±80°", "et", "start"))
    o.append(v.flecha(78, 40, 20, 36))
    o.append(v.texto(78, 42, "barriga = parlante 50 mm", "et", "end"))
    # cotas
    o.append(v.texto(0, -10, "128 mm de ancho · 194 mm de alto", "cota", "middle"))
    o.append(v.texto(0, 220, "FRENTE", "titulo", "middle"))
    return o


def vista_corte(v: Vista) -> list[str]:
    o = []
    zc = rango(C_Z0, C_TOP)
    zh = rango(H_RIM, H_TOP, 80)
    # silueta (Y: atras = izquierda, adelante = derecha)
    o.append(v.rect(-52.8, 0, 52.8, C_Z0, "base", 1))
    o.append(f'<path d="{v.silueta(lambda z: -C_B * f_cuerpo(z), lambda z: C_B * f_cuerpo(z), zc)}" class="cuerpo corte"/>')
    o.append(f'<path d="{v.silueta(lambda z: -cabeza_b(z), lambda z: min(cabeza_b(z), H_CARA), zh)}" class="cabeza corte"/>')
    # componentes
    o.append(v.rect(-49.5, 23, 19.5, 26.5, "esp"))                       # ESP32
    o.append(v.rect(-49.5, 26.5, -42, 29.5, "usb"))
    o.append(v.rect(-8, 3, 4, 23, "soporte"))                            # cuna
    o.append(v.rect(-49, 3, -43, 23, "soporte"))
    o.append(v.rect(28.6, 8, 46.6, 58, "parl"))                          # parlante
    o.append(v.rect(29.4, 64, 31, 88, "pirpcb"))                         # PIR
    o.append(f'<path d="M{v.p(31, 87.5)} A{11.5 * S},{11.5 * S} 0 0 1 {v.p(31, 64.5)} Z" class="pir"/>')
    o.append(v.rect(28.6, 134.5, 29.8, 175, "cam"))                     # ESP32-CAM
    o.append(v.rect(29.8, 158.8, 39.3, 167.2, "cam"))
    o.append(v.rect(-6.1, 67.3, 6.1, 89.8, "servo"))                     # servo
    o.append(v.rect(-27, 80.1, 27, 83.1, "soporte"))                     # soporte servo
    o.append(v.rect(-DISCO_R, 96, DISCO_R, 100, "cuello"))               # disco
    o.append(v.rect(-DISCO_R, 100, -DISCO_R + 2, TUBO_TOP, "cuello"))    # tubo
    o.append(v.rect(DISCO_R - 2, 100, DISCO_R, TUBO_TOP, "cuello"))
    o.append(v.rect(-H_B0 + 0.3, PISO_Z, H_B0 - 0.3, H_RIM, "piso"))     # piso
    for y in (-17, 8.5):                                                  # resortes
        o.append(f'<path d="M{v.p(y, 104)} l{2*S},{-1.3*S} l{-4*S},{-1.3*S} l{4*S},{-1.3*S} l{-4*S},{-1.3*S} l{4*S},{-1.3*S} l{-2*S},{-1.3*S}" class="resorte"/>')
    o.append(v.rect(-2.9, PISO_Z - 6.5, 2.9, PISO_Z, "sw"))              # microswitch
    o.append(v.circ(0, PISO_Z - 6.5 - 2.4, 2.4, "sw"))
    o.append(v.rect(-4.5, 100, 4.5, 101.7, "dedo"))
    o.append(v.rect(35.8, 130.1, 39.6, 157.9, "oledlado"))                 # OLED
    o.append(v.rect(-24, 18, -4, 21, "amp"))                             # (amp va a un lado, x=32)
    # cables
    o.append(f'<path d="M{v.p(-12, 115)} C{v.p(-14, 100)} {v.p(-18, 80)} {v.p(-22, 60)} S{v.p(-30, 30)} {v.p(-30, 27)}" class="cable"/>')
    # etiquetas
    L = []
    L.append((-95, 196, 0, 186, "cabeza: cáscara impresa (con soporte adentro)"))
    L.append((95, 168, 38, 150, "OLED atornillado a la cara"))
    L.append((95, 188, 29, 172, "ESP32-CAM detrás del OLED"))
    L.append((95, 78, 36, 76, "PIR en el pecho"))
    L.append((-95, 128, -2, PISO_Z - 9, "microswitch bajo el piso"))
    L.append((-95, 118, -17, 101, "3 resortes de lápiz + tornillos guía"))
    L.append((95, 110, 4, 101, "\"dedo\" fijo en el disco"))
    L.append((95, 100, 25, 105, "tubo = tope (2 mm de recorrido)"))
    L.append((95, 88, 8, 78, "servo SG90 colgado del labio"))
    L.append((95, 50, 38, 40, "parlante 50 mm contra la barriga"))
    L.append((-95, 78, -20, 64, "cables al ESP32 (lazo)"))
    L.append((-95, 44, -30, 25, "ESP32-S3 sobre la base"))
    L.append((-95, 8, -48, 28, "USB-C atrás (luz + programar)"))
    L.append((95, 14, -14, 20, "amplificador (va a la derecha)"))
    for x0, z0, x1, z1, t in L:
        o.append(v.flecha(x0 + (4 if x0 < 0 else -4), z0 + 1, x1, z1))
        o.append(v.texto(x0, z0 + 2, t, "et", "start" if x0 < 0 else "end"))
    o.append(v.texto(-60, -10, "atrás", "cota", "middle"))
    o.append(v.texto(60, -10, "adelante", "cota", "middle"))
    o.append(v.texto(0, 220, "CORTE LATERAL", "titulo", "middle"))
    return o


def detalle_boton(ox: float, oy: float) -> list[str]:
    """Esquema del boton: reposo y apretado."""
    o = []
    k = 3.2
    def r(x0, y0, x1, y1, c):
        return f'<rect x="{ox + x0 * k:.1f}" y="{oy - y1 * k:.1f}" width="{(x1 - x0) * k:.1f}" height="{(y1 - y0) * k:.1f}" class="{c}"/>'
    for i, (baja, titulo) in enumerate(((0, "en reposo"), (2.0, "apretado"))):
        dx = i * 120
        o.append(r(dx - 30, 0, dx + 30, 4, "cuello"))                    # disco
        o.append(r(dx - 30, 4, dx - 28, 14, "cuello"))                   # tubo
        o.append(r(dx + 28, 4, dx + 30, 14, "cuello"))
        o.append(r(dx - 4.5, 4, dx + 4.5, 5.7, "dedo"))
        y = 16 - baja
        o.append(r(dx - 36, y, dx + 36, y + 3, "piso"))
        o.append(r(dx - 2.9, y - 6.5, dx + 2.9, y, "sw"))
        rod = y - 6.5 - (2.4 if not baja else 2.4 - 1.7)
        o.append(f'<circle cx="{ox + dx * k:.1f}" cy="{oy - rod * k:.1f}" r="{2.4 * k:.1f}" class="sw"/>')
        o.append(f'<text x="{ox + dx * k:.1f}" y="{oy + 18:.1f}" class="et" text-anchor="middle">{titulo}</text>')
        if baja:
            o.append(f'<text x="{ox + dx * k:.1f}" y="{oy - 24 * k:.1f}" class="et" text-anchor="middle">el piso toca el tubo: tope firme · el switch hace clic</text>')
            o.append(f'<path d="M{ox + dx * k:.1f},{oy - 34 * k:.1f} v{6 * k:.1f}" class="empuje"/>')
    o.append(f'<text x="{ox - 30 * k:.1f}" y="{oy - 30 * k:.1f}" class="titulo2">Cómo funciona la cabeza-botón</text>')
    return o


def main() -> None:
    estilo = """
    <style>
      text { font-family: 'Segoe UI', Arial, sans-serif; }
      .titulo { font-size: 20px; font-weight: 700; fill: #333; letter-spacing: 2px; }
      .titulo2 { font-size: 16px; font-weight: 700; fill: #333; }
      .et { font-size: 12.5px; fill: #444; }
      .cota { font-size: 12px; fill: #777; }
      .guia { stroke: #999; stroke-width: 1; }
      .punto { fill: #999; }
      .base { fill: #6c7a89; stroke: #3b4652; stroke-width: 1.5; }
      .cuerpo { fill: #ffd166; stroke: #b8860b; stroke-width: 2.5; }
      .cabeza { fill: #fff3d6; stroke: #b8860b; stroke-width: 2.5; }
      .corte { fill-opacity: 0.35; stroke-dasharray: 0; }
      .rejilla { fill: #ffc233; stroke: #b8860b; stroke-width: 1.5; }
      .hoyo { fill: #8a6200; }
      .cuello { fill: #7bdff2; stroke: #2a8ca0; stroke-width: 1.5; }
      .piso { fill: #f4a261; stroke: #b3602a; stroke-width: 1.5; }
      .oreja { fill: #ef476f; stroke: #a32a4a; stroke-width: 1.5; }
      .visor { fill: #2b2d42; stroke: #111; stroke-width: 1.5; }
      .oled { fill: #10151f; stroke: #4cc9f0; stroke-width: 1; }
      .ojo { fill: #4cc9f0; }
      .boca { fill: none; stroke: #4cc9f0; stroke-width: 2; stroke-linecap: round; }
      .mic { fill: #2b2d42; }
      .mejilla { fill: #ef476f; opacity: 0.35; }
      .boton { stroke: #ef476f; stroke-width: 5; stroke-linecap: round; opacity: 0.7; }
      .esp { fill: #1d3557; stroke: #0b1a2e; }
      .usb { fill: #adb5bd; stroke: #495057; }
      .soporte { fill: #b0b8c1; stroke: #6c757d; }
      .parl { fill: #495057; stroke: #212529; }
      .servo { fill: #3a86ff; stroke: #1f4fa0; }
      .sw { fill: #e63946; stroke: #8d1d26; }
      .dedo { fill: #06d6a0; stroke: #04875f; }
      .oledlado { fill: #10151f; stroke: #4cc9f0; }
      .amp { fill: #8338ec; stroke: #4b1d8f; }
      .pir { fill: #ffffff; stroke: #999; stroke-width: 1.5; }
      .pirpcb { fill: #2a9d8f; stroke: #1d6f65; }
      .lente { fill: #111; stroke: #555; stroke-width: 1.5; }
      .cam { fill: #2d6a4f; stroke: #1b4332; }
      .resorte { fill: none; stroke: #555; stroke-width: 1.5; }
      .cable { fill: none; stroke: #e76f51; stroke-width: 2; stroke-dasharray: 5 3; }
      .empuje { stroke: #ef476f; stroke-width: 4; marker-end: url(#punta); }
    </style>
    <defs><marker id="punta" markerWidth="8" markerHeight="8" refX="3" refY="4" orient="auto">
      <path d="M0,0 L6,4 L0,8 Z" fill="#ef476f"/></marker></defs>
    """
    frente = vista_frente(Vista(330, 600))
    corte = vista_corte(Vista(1010, 600))
    boton = detalle_boton(470, 805)
    ancho, alto = 1400, 870
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{ancho}" height="{alto}" viewBox="0 0 {ancho} {alto}">',
        estilo,
        f'<rect width="{ancho}" height="{alto}" fill="#fffdf7"/>',
        '<text x="30" y="40" class="titulo2">Kids Robot · versión "redondo" · boceto v1</text>',
        '<text x="30" y="60" class="cota">Medidas en mm, sacadas de redondo/parametros.scad. La fuente de verdad es robot.scad.</text>',
        *frente, *corte, *boton,
        "</svg>",
    ]
    SALIDA.write_text("\n".join(svg), encoding="utf-8")
    print("Escrito", SALIDA)


if __name__ == "__main__":
    main()
