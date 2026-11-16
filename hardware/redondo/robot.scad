// =====================================================================
//  Kids Robot - version "redondo" v1
//  Cuerpo de gomita, cuello que gira (SG90) y una cabeza que es un boton
//  gigante: al apretarla baja 2 mm sobre 3 resortes y aprieta un
//  microswitch (reemplaza al TTP223).
//
//  Uso:
//    openscad -D "PARTE=\"cabeza\"" -o stl/cabeza.stl robot.scad
//    PARTE = ensamble | corte | componentes | <pieza>
//    piezas: cuerpo, base, soporte_servo, disco, piso, cabeza, visor, oreja, prueba
//
//  Ejes: X derecha, Y adelante (cara), Z arriba.  Mesa en Z = 0.
// =====================================================================

include <parametros.scad>
include <componentes.scad>

PARTE = "ensamble";
CORTE_X = 0;

// ---------------------------------------------------------------------
//  Utilidades
// ---------------------------------------------------------------------

function sgn(v) = v < 0 ? -1 : 1;
// superelipse |x/a|^m + |y/b|^m = 1
function se(a, b, m, n = NSE) = [for (i = [0:n - 1]) let (t = 360 * i / n, c = cos(t), s = sin(t))
  [a * sgn(c) * pow(abs(c), 2 / m), b * sgn(s) * pow(abs(s), 2 / m)]];

module rodaja(a, b, m, z) translate([0, 0, z]) linear_extrude(0.01) polygon(se(a, b, m));

module caja_r(x, y, h, r) {     // caja redondeada en XY, de Z 0 a h
  hull() for (a = [-1, 1], b = [-1, 1]) translate([a * (x / 2 - r), b * (y / 2 - r), 0]) cylinder(r = r, h = h);
}

module en_polar(r, angs) for (a = angs) translate([r * cos(a), r * sin(a), 0]) children();

// ---------------------------------------------------------------------
//  Formas del cuerpo y la cabeza
// ---------------------------------------------------------------------

// factor del perfil del cuerpo a la altura z (d = desplazamiento hacia adentro)
function fc(z, d) = let (t = max(0, z) / (C_HS - d)) t >= 1 ? 0.01 : pow(1 - pow(t, C_N), 1 / C_N);
function cz(n = 30) = [for (i = [0:n]) C_Z0 + C_CHAF + (C_TOP - C_Z0 - C_CHAF) * (1 - pow(1 - i / n, 1.8))];

module cuerpo_ext() hull() {
  rodaja(C_A - C_CHAF, C_B - C_CHAF, C_M, C_Z0);
  for (z = cz()) rodaja(C_A * fc(z, 0), C_B * fc(z, 0), C_M, z);
}

module cuerpo_int() {
  d = PARED;
  hull() {
    rodaja(C_A - d - C_CHAF / 2, C_B - d - C_CHAF / 2, C_M, C_Z0 - 1);
    for (z = concat(cz(), [C_TOP + 1])) rodaja((C_A - d) * fc(z, d), (C_B - d) * fc(z, d), C_M, z);
  }
}

// cabeza: menton curvo (sale a 45 grados, termina vertical) + cupula
function cup(z, hd) = z <= H_ZC ? 1 : let (t = min((z - H_ZC) / hd, 1)) pow(max(0.0001, 1 - pow(t, H_N)), 1 / H_N);
function ment(z, full, base) = let (dd = full - base, s = min(max((z - H_RIM) / (2 * dd), 0), 1)) full - dd * pow(1 - s, 2);
function ha(z, d) = min(ment(z, H_A - d, H_A0 - d * 1.42), (H_A - d) * cup(z, H_HD - d));
function hb(z, d) = min(ment(z, H_B - d, H_B0 - d * 1.42), (H_B - d) * cup(z, H_HD - d));
function hz(z0, z1, n = 60) = [for (i = [0:n]) z0 + (z1 - z0) * (1 - pow(1 - i / n, 1.4))];

module cabeza_ext() intersection() {
  hull() for (z = hz(H_RIM, H_TOP)) rodaja(ha(z, 0), hb(z, 0), H_M, z);
  translate([-100, -100, 0]) cube([200, 100 + H_CARA, 300]);
}

module cabeza_int() intersection() {
  hull() for (z = hz(H_RIM + H_PEST, H_TOP - PARED)) rodaja(ha(z, PARED), hb(z, PARED), H_M, z);
  translate([-100, -100, 0]) cube([200, 100 + H_CARA - PARED, 300]);
}

// zona de aire bajo el labio: cono de 45 grados (para imprimir sin soporte)
module aire_labio(extra = 0) {
  translate([0, 0, LABIO_Z - 60]) cylinder(h = 60, r1 = LABIO_R + 60 - extra, r2 = LABIO_R - extra, $fn = 96);
  translate([0, 0, LABIO_Z - 1]) cylinder(h = C_TOP - LABIO_Z + 2, r = LABIO_R - extra, $fn = 96);
}

USB_Z = ESP_Z + ESP_PCB + 1.6;

// espacio del PIR y sus componentes de atras, con techo a 45 grados
module hueco_pir() hull() {
  // el techo sube a 45 grados hacia la pared: no corta el anillo de arriba
  y0 = PIR_Y - PIR_ATRAS - 1;
  translate([-PIR_W / 2 - 2, y0, PIR_Z - PIR_H / 2 - 4]) cube([PIR_W + 4, 40, PIR_H + 4.5]);
  translate([-PIR_W / 2 - 2, y0 + 40, PIR_Z - PIR_H / 2 - 4]) cube([PIR_W + 4, 0.1, PIR_H + 4.5 + 40]);
}

// ---------------------------------------------------------------------
//  CUERPO: cascara, labio del cuello, parlante, USB, torres de la base
// ---------------------------------------------------------------------

module cuerpo() {
  difference() {
    union() {
      difference() { cuerpo_ext(); cuerpo_int(); }

      // labio del cuello: el disco gira apoyado aqui; abajo cuelga el servo
      intersection() {
        cuerpo_int();
        difference() {
          translate([0, 0, LABIO_Z - 60]) cylinder(r = 90, h = 60 + C_TOP - LABIO_Z);
          aire_labio();
          hueco_pir();
        }
      }

      // torres de la base (inserto M3 desde abajo)
      intersection() {
        cuerpo_ext();
        for (p = BOSS_XY) translate([p[0], p[1], C_Z0]) cylinder(d = 9, h = BOSS_H);
      }

      // nervios donde apoya el PCB del PIR (fondo a 45 grados)
      intersection() {
        cuerpo_int();
        for (sx = [-1, 1]) difference() {
          translate([sx * 14.25 - 2.25, PIR_Y, PIR_Z - PIR_H / 2]) cube([4.5, 20, PIR_H + 4]);
          // quitar lo que queda bajo la linea de 45 grados que sube hacia adentro
          translate([0, PIR_Y + 9, PIR_Z - PIR_H / 2]) rotate([45, 0, 0]) translate([-20, -100, -100]) cube([40, 100, 200]);
        }
      }

      // asiento del parlante: deflector hasta la pared + aro que lo centra
      intersection() {
        cuerpo_ext();
        translate([0, PARL_Y, PARL_Z]) rotate([-90, 0, 0]) difference() {
          cylinder(r = PARL_D / 2 + 3.5, h = 30);
          translate([0, 0, -1]) cylinder(r = PARL_D / 2 - 3.5, h = 32);
        }
      }
      translate([0, PARL_Y, PARL_Z]) rotate([90, 0, 0]) difference() {
        cylinder(r = PARL_D / 2 + 3.5, h = 4);
        translate([0, 0, -1]) cylinder(r = PARL_D / 2 + 0.3, h = 6);
      }
    }

    // PIR: lente que asoma y tornillos M2 del PCB
    translate([0, PIR_Y - 1, PIR_Z]) rotate([-90, 0, 0]) cylinder(d = PIR_LENTE_D + 0.6, h = 30, $fn = 64);
    translate([0, PIR_Y - 1, PIR_Z]) rotate([-90, 0, 0]) translate([-12, -12, 0]) cube([24, 24, 3.6]);
    for (sx = [-1, 1]) translate([sx * PIR_AG / 2, PIR_Y - 1, PIR_Z]) rotate([-90, 0, 0]) cylinder(d = 1.7, h = 7, $fn = 16);

    // rejilla del parlante (la "barriga")
    for (r = [0, 6.5, 13, 19.5]) let (n = r == 0 ? 1 : round(r * 6.3 / 6.5))
      for (i = [0:n - 1]) let (a = 360 * i / n + (r == 13 ? 15 : 0))
        translate([r * cos(a), PARL_Y - 1, PARL_Z + r * sin(a)]) rotate([-90, 0, 0]) cylinder(d = 3.4, h = 25, $fn = 20);

    // tornillos del soporte del servo (avellanados desde arriba)
    en_polar(SOP_R, SOP_ANG) {
      translate([0, 0, LABIO_Z - 20]) cylinder(d = M3, h = 30, $fn = 24);
      translate([0, 0, C_TOP - 1.8]) cylinder(d1 = M3, d2 = 6.8, h = 1.81, $fn = 24);
    }

    // insertos de las torres
    for (p = BOSS_XY) translate([p[0], p[1], C_Z0 - 0.1]) cylinder(d = INS_D, h = INS_L, $fn = 24);

    // ventana de los USB-C (atras) con rebaje para la funda del cable
    yint = (C_B - PARED) * fc(USB_Z, PARED);
    translate([ESP_X, -yint - 20, USB_Z]) cube([USB_ANCHO, 40, USB_ALTO], center = true);
    translate([ESP_X, -yint - 1.2 - 15, USB_Z]) rotate([90, 0, 0])
      translate([0, 0, -15]) caja_r(USB_ANCHO + 7, USB_ALTO + 6, 30, 3);
  }
}

// ---------------------------------------------------------------------
//  BASE: tapa de abajo con la cuna del ESP32, el amplificador y patas
// ---------------------------------------------------------------------

module base() {
  difference() {
    union() {
      hull() {
        rodaja(C_A - C_CHAF - 0.8, C_B - C_CHAF - 0.8, C_M, 0);
        translate([0, 0, 0.8]) linear_extrude(BASE_H - 0.8) polygon(se(C_A - C_CHAF, C_B - C_CHAF, C_M));
      }
      // cuna del ESP32: extremo USB (atras) y extremo antena (adelante)
      translate([ESP_X - 8, ESP_Y0 + 0.6, BASE_H]) cube([16, 5, ESP_Z - BASE_H]);
      for (s = [-1, 1])     // guias laterales en el extremo USB, por fuera del PCB
        translate([ESP_X + s * (ESP_W / 2 + HOLG + 1.25) - 1.25, ESP_Y0 + 0.6, BASE_H])
          cube([2.5, 5, ESP_Z + ESP_PCB + 1.5 - BASE_H]);
      translate([ESP_X - 8, ESP_Y0 + ESP_L - 5, BASE_H]) difference() {
        cube([16, 5 + HOLG + 2.5, ESP_Z + ESP_PCB + 1.5 - BASE_H]);
        translate([-1, -1, ESP_Z - BASE_H]) cube([18, 6 + HOLG, 10]);
      }
      // pedestal del amplificador (va pegado con cinta doble faz)
      translate([AMP_XY[0], AMP_XY[1] + 3, BASE_H]) caja_r(10, 9, 13, 2);
      // anillo del condensador
      translate([CAP_XY[0], CAP_XY[1], BASE_H]) difference() {
        cylinder(d = CAP_D + 3.2, h = 6);
        translate([0, 0, 1]) cylinder(d = CAP_D + 0.5, h = 7);
      }
    }
    // tornillos M3 a las torres del cuerpo (avellanados por abajo)
    for (p = BOSS_XY) translate([p[0], p[1], -0.1]) {
      cylinder(d = M3, h = 10, $fn = 24);
      cylinder(d1 = 6.8, d2 = M3, h = 1.8, $fn = 24);
    }
    // patas de goma de 10 mm
    for (a = [-1, 1], b = [-1, 1]) translate([a * 40, b * 26, -0.1]) cylinder(d = 10.5, h = 1.1, $fn = 32);
    // ranuras para una brida o elastico que sujeta el ESP32
    for (s = [-1, 1]) translate([ESP_X + s * 16.5 - 1.5, ESP_Y0 + 34, -1]) cube([3, 5, 10]);
  }
}

// ---------------------------------------------------------------------
//  SOPORTE DEL SERVO: cuelga del labio con 3 tornillos
// ---------------------------------------------------------------------

module soporte_servo() {
  pz = SV_Z0 + SV_OREJA_Z;     // las orejas del servo apoyan aqui
  difference() {
    union() {
      translate([0, 0, pz - 3]) cylinder(r = SOP_PLACA_R, h = 3, $fn = 96);
      intersection() {
        en_polar(SOP_R, SOP_ANG) translate([0, 0, pz - 3]) cylinder(d = 8, h = 20, $fn = 32);
        aire_labio(0.3);
      }
    }
    translate([SV_OFF, 0, pz - 2]) cube([SV_X + 0.6, SV_Y + 0.6, 10], center = true);
    for (s = [-1, 1]) translate([SV_OFF + s * SV_OREJA_AG / 2, 0, pz - 4]) cylinder(d = 1.8, h = 6, $fn = 16);
    en_polar(SOP_R, SOP_ANG)
      translate([0, 0, LABIO_Z - (SOP_R - LABIO_R) - 0.3 - INS_L]) cylinder(d = INS_D, h = 20, $fn = 24);
    // paso del cable del servo y de la cabeza
    translate([-SV_X / 2 + SV_OFF - 9, -6, pz - 4]) cube([9, 12, 6]);
  }
}

// ---------------------------------------------------------------------
//  DISCO DEL CUELLO: gira con el servo; postes guia, tubo-tope y "dedo"
// ---------------------------------------------------------------------

module disco() {
  ztop = DISCO_Z + DISCO_H;
  difference() {
    union() {
      translate([0, 0, DISCO_Z]) cylinder(r = DISCO_R, h = DISCO_H, $fn = 96);
      translate([0, 0, ztop]) difference() {
        cylinder(r = DISCO_R, h = TUBO_TOP - ztop, $fn = 96);
        translate([0, 0, -1]) cylinder(r = DISCO_R - TUBO_E, h = 30, $fn = 96);
      }
      en_polar(POSTE_R, POSTE_ANG) translate([0, 0, ztop]) cylinder(d = POSTE_D, h = POSTE_H, $fn = 32);
      translate([0, 0, ztop]) cylinder(d = DEDO_D, h = DEDO_H, $fn = 40);
    }
    // rebaje del brazo doble del servo (por abajo)
    translate([0, 0, DISCO_Z - 0.01]) linear_extrude(CUERNO_REC + HOLG) offset(r = HOLG) hull() {
      for (s = [-1, 1]) translate([s * 16, 0]) circle(d = 4, $fn = 20);
      circle(d = 7.5, $fn = 32);
    }
    // tornillo central del brazo + acceso del destornillador por el dedo
    translate([0, 0, DISCO_Z - 1]) cylinder(d = 2.6, h = 20, $fn = 16);
    translate([0, 0, DISCO_Z + CUERNO_REC + 1.5]) cylinder(d = 5.5, h = 20, $fn = 24);
    // insertos de los postes
    en_polar(POSTE_R, POSTE_ANG) translate([0, 0, ztop + POSTE_H - INS_L]) cylinder(d = INS_D, h = 10, $fn = 24);
    // cables de la cabeza
    translate([CABLE_XY[0], CABLE_XY[1], DISCO_Z - 1]) cylinder(d = CABLE_D, h = 20, $fn = 32);
  }
}

// ---------------------------------------------------------------------
//  PISO DE LA CABEZA: flota sobre los resortes y lleva el microswitch
// ---------------------------------------------------------------------

module piso() {
  sx = -SW_ROD_X;              // centro del switch (el rodillo queda en X = 0)
  difference() {
    union() {
      translate([0, 0, PISO_Z]) linear_extrude(PISO_H) polygon(se(H_A0 - 0.3, H_B0 - 0.3, H_M));
      // pestana donde se atornilla el microswitch (cuelga del piso)
      translate([sx - SW_L / 2 - 1, SW_E / 2 + HOLG, PISO_Z - SW_H]) cube([SW_L + 2, 2.6, SW_H + 0.1]);
    }
    for (s = [-1, 1]) translate([sx + s * SW_AG / 2, 0, PISO_Z - SW_AG_Z]) rotate([-90, 0, 0])
      cylinder(d = 1.9, h = 20, $fn = 16);
    // ranura para los terminales del switch (se sueldan por arriba)
    translate([sx, 0, PISO_Z - 1]) cube([SW_L - 1.5, SW_E - 1.5, 10], center = true);
    // tornillos guia (la cabeza desliza sobre ellos)
    en_polar(POSTE_R, POSTE_ANG) translate([0, 0, PISO_Z - 1]) cylinder(d = M3 + 0.2, h = 10, $fn = 24);
    // tornillos a la cascara (avellanados por abajo)
    for (p = H_TORRES) translate([p[0], p[1], PISO_Z - 0.1]) {
      cylinder(d = M3, h = 10, $fn = 24);
      cylinder(d1 = 6.8, d2 = M3, h = 1.8, $fn = 24);
    }
    translate([CABLE_XY[0], CABLE_XY[1], PISO_Z - 1]) cylinder(d = CABLE_D, h = 10, $fn = 32);
  }
}

// ---------------------------------------------------------------------
//  CABEZA: cascara con cara plana, visor, rieles del OLED y del micro
// ---------------------------------------------------------------------

YIN = H_CARA - PARED;          // cara interior plana
CAM_Y = YIN - CAM_FRENTE - 0.3;                  // cara del PCB de la camara
CAM_ZC = CAM_LENTE_Z + CAM_LENTE_TOP - CAM_L / 2; // centro del PCB de la camara

// Bolsillo en U (izquierda, derecha, abajo) pegado a la cara interior.  El
// modulo entra desde atras y se fija con un punto de silicona caliente.
// La pared de abajo tiene cuna de 45 grados para imprimir sin soporte.
module bolsillo(cx, cz, w, h, t, e = 1.6) {
  p = t + 1.2;                 // profundidad desde la cara
  xs = [cx - w / 2 - HOLG - e, cx + w / 2 + HOLG];
  for (x0 = xs) hull() {
    translate([x0, YIN - p, cz - h / 2 - HOLG - e]) cube([e, p + 0.5, h * 0.75]);
    translate([x0, YIN, cz - h / 2 - HOLG - e - p]) cube([e, 0.5, 0.01]);
  }
  hull() {
    translate([cx - w / 2 - HOLG - e, YIN - p, cz - h / 2 - HOLG - e]) cube([w + 2 * HOLG + 2 * e, p + 0.5, e]);
    translate([cx - w / 2 - HOLG - e, YIN, cz - h / 2 - HOLG - e - p]) cube([w + 2 * HOLG + 2 * e, 0.5, 0.01]);
  }
}

// OLED: 4 torres cortas con tornillo M2 por detras; el vidrio queda contra la cara
module torres_oled(hueco = false) {
  for (a = [-1, 1], b = [-1, 1])
    translate([a * OLED_AG / 2, YIN + 0.5, OLED_CZ + b * OLED_AG / 2]) rotate([90, 0, 0])
      if (hueco) translate([0, 0, -1]) cylinder(d = 1.7, h = OLED_T + 4, $fn = 16);
      else cylinder(d = OLED_BOSS_D, h = OLED_T - 1.2 + 0.5, $fn = 24);
}

// Camara: dos paredes laterales con tope; el PCB apoya en los topes
module guias_camara() {
  zb = CAM_ZC - CAM_L / 2;
  p = YIN - CAM_Y + 1.2;
  for (sx = [-1, 1]) {
    x0 = sx < 0 ? -CAM_W / 2 - HOLG - 1.8 - 0.5 : CAM_W / 2 + HOLG + 0.5;
    hull() {      // pared
      translate([x0, CAM_Y - 1.2, zb]) cube([1.8, p + 0.5, CAM_L - 4]);
      translate([x0, YIN, zb - p]) cube([1.8, 0.5, 0.01]);
    }
    // tope donde apoya la cara del PCB (detras del OLED)
    x1 = sx < 0 ? -CAM_W / 2 - HOLG - 0.5 : CAM_W / 2 - 1.5;
    hull() {
      translate([x1, CAM_Y, zb]) cube([2.25, YIN - OLED_T - 0.5 - CAM_Y, CAM_L - 4]);
      translate([x1, CAM_Y, zb - 4]) cube([2.25, 0.5, 0.01]);
    }
  }
  // repisa de abajo (puente entre las dos paredes)
  translate([-CAM_W / 2 - HOLG - 0.6, CAM_Y - 1.2, zb - 1.6]) cube([CAM_W + 2 * HOLG + 1.2, 4, 1.6]);
}

module cabeza() {
  difference() {
    union() {
      difference() { cabeza_ext(); cabeza_int(); }
      intersection() {
        cabeza_ext();
        union() {
          torres_oled();
          guias_camara();
          bolsillo(MIC_X, MIC_Z, MIC_W, MIC_H, MIC_T);
          bolsillo(VL_X, VL_Z, VL_W, VL_H, VL_T);
          for (p = H_TORRES) translate([p[0], p[1], H_RIM]) cylinder(d = 8, h = H_PEST + 6, $fn = 32);
        }
      }
    }
    torres_oled(true);
    // abertura de la pestana inferior
    translate([0, 0, H_RIM - 1]) linear_extrude(H_PEST + 2)
      polygon(se(H_A0 - 1.42 * PARED - H_PEST_W, H_B0 - 1.42 * PARED - H_PEST_W, H_M));
    for (p = H_TORRES) translate([p[0], p[1], H_RIM - 0.1]) cylinder(d = INS_D, h = INS_L, $fn = 24);
    // bolsillo del visor
    translate([0, H_CARA - VISOR_P, VISOR_Z]) rotate([-90, 0, 0]) caja_r(VISOR_W, VISOR_H, 5, VISOR_R);
    // ventana del OLED (con bisel hacia afuera)
    translate([0, YIN - 0.5, OLED_CZ + OLED_VDZ]) rotate([-90, 0, 0])
      linear_extrude(PARED + 1, scale = [1.15, 1.25]) square(OLED_VENT, center = true);
    // lente de la camara
    translate([0, YIN - 1, CAM_LENTE_Z]) rotate([-90, 0, 0]) cylinder(d = CAM_LENTE_D, h = 10, $fn = 40);
    // microfono y ventana del sensor de distancia
    translate([MIC_X, YIN - 1, MIC_Z]) rotate([-90, 0, 0]) cylinder(d = 2, h = 10, $fn = 16);
    translate([VL_X, YIN - 1, VL_Z + VL_SENS_DZ]) rotate([-90, 0, 0])
      linear_extrude(10) offset(r = 1) square(VL_VENT - [2, 2], center = true);
    // agujeros de las orejas
    for (s = [-1, 1]) translate([s * (H_A - 10), 0, OREJA_Z]) rotate([0, s * 90, 0])
      cylinder(d = OREJA_PERNO + 0.4, h = 20, $fn = 32);
  }
}

module visor() {
  difference() {
    caja_r(VISOR_W - 0.4, VISOR_H - 0.4, VISOR_P, VISOR_R - 0.2);
    translate([0, OLED_CZ + OLED_VDZ - VISOR_Z, -1]) linear_extrude(VISOR_P + 2) square(OLED_VENT, center = true);
    translate([0, CAM_LENTE_Z - VISOR_Z, -1]) cylinder(d = CAM_LENTE_D, h = VISOR_P + 2, $fn = 40);
  }
}

module oreja() {
  hull() {
    cylinder(d = OREJA_D - 3, h = 0.01, $fn = 64);
    translate([0, 0, 1.5]) cylinder(d = OREJA_D, h = OREJA_E - 1.5, $fn = 64);
  }
  translate([0, 0, OREJA_E - 0.01]) cylinder(d = OREJA_PERNO, h = 6, $fn = 32);
}

// cupon para calibrar insertos, guias y rieles antes de imprimir todo
module prueba() {
  difference() {
    translate([0, 0, 0]) cube([70, 22, 7]);
    for (i = [0:2]) translate([8 + i * 10, 7, 1]) cylinder(d = [4.0, 4.2, 4.4][i], h = 10, $fn = 24);
    translate([38, 7, -1]) cylinder(d = M3, h = 10, $fn = 24);
    translate([46, 7, -1]) cylinder(d = M3 + 0.2, h = 10, $fn = 24);
    translate([54, 7, -1]) cylinder(d = 1.9, h = 10, $fn = 16);
    translate([62, 7, -1]) cylinder(d = 2.6, h = 10, $fn = 16);
    // ranuras de los rieles (OLED y micro)
    translate([4, 14, 2]) cube([30, OLED_T + HOLG, 10]);
    translate([40, 14, 2]) cube([26, MIC_T + HOLG, 10]);
  }
}

// ---------------------------------------------------------------------
//  Ensamble
// ---------------------------------------------------------------------

C_CUERPO = "#ffd166";
C_CABEZA = "#fff1d0";

module componentes_puestos() {
  translate([ESP_X, ESP_Y0, ESP_Z]) c_esp32s3();
  translate([AMP_XY[0], AMP_XY[1], BASE_H + 13]) c_max98357();
  translate([CAP_XY[0], CAP_XY[1], BASE_H + 1]) c_condensador();
  translate([0, PARL_Y, PARL_Z]) rotate([-90, 0, 0]) c_parlante();
  translate([0, 0, SV_Z0]) c_sg90();
  translate([-SW_ROD_X, 0, PISO_Z]) mirror([0, 0, 1]) c_microswitch();
  en_polar(POSTE_R, POSTE_ANG) translate([0, 0, DISCO_Z + DISCO_H + POSTE_H]) c_resorte(PISO_Z - (DISCO_Z + DISCO_H + POSTE_H));
  translate([0, YIN - OLED_T, OLED_CZ]) rotate([0, 0, 180]) rotate([90, 0, 0]) c_oled();
  translate([MIC_X, YIN - MIC_T, MIC_Z]) rotate([0, 0, 180]) rotate([90, 0, 0]) c_inmp441();
  translate([VL_X, YIN - VL_T, VL_Z]) rotate([0, 0, 180]) rotate([90, 0, 0]) c_vl53l0x();
  translate([0, CAM_Y, CAM_ZC]) rotate([0, 0, 180]) rotate([90, 0, 0]) c_esp32cam();
  translate([0, PIR_Y, PIR_Z]) rotate([0, 0, 180]) rotate([90, 0, 0]) c_pir();
}

module ensamble(apretado = false) {
  dz = apretado ? -RECORRIDO : 0;
  color("#8d99ae") base();
  color(C_CUERPO) cuerpo();
  color("#adb5bd") soporte_servo();
  color("#7bdff2") disco();
  translate([0, 0, dz]) {
    color("#f4a261") piso();
    color(C_CABEZA) cabeza();
    color("#2b2d42") translate([0, H_CARA, VISOR_Z]) rotate([90, 0, 0]) visor();
    for (s = [-1, 1]) color("#ef476f")
      translate([s * (ha(OREJA_Z, 0) + OREJA_E - 0.6), 0, OREJA_Z]) rotate([0, -s * 90, 0]) oreja();
  }
  componentes_puestos();
}

if (PARTE == "ensamble") ensamble();
else if (PARTE == "apretado") ensamble(true);
else if (PARTE == "corte") difference() { ensamble(); translate([0, -150, -1]) cube([150, 300, 300]); }
else if (PARTE == "corte_lado") difference() { ensamble(); translate([-150, 0, -1]) cube([300, 150, 300]); }
else if (PARTE == "componentes") lamina_componentes();
else if (PARTE == "puestos") componentes_puestos();
// piezas sueltas, ya orientadas para imprimir
else if (PARTE == "cuerpo") cuerpo();
else if (PARTE == "base") base();
else if (PARTE == "soporte_servo") translate([0, 0, -(SV_Z0 + SV_OREJA_Z - 3)]) soporte_servo();
else if (PARTE == "disco") translate([0, 0, -DISCO_Z]) disco();
else if (PARTE == "piso") translate([0, 0, PISO_Z + PISO_H]) mirror([0, 0, 1]) piso();
else if (PARTE == "cabeza") translate([0, 0, -H_RIM]) cabeza();
else if (PARTE == "visor") visor();
else if (PARTE == "oreja") oreja();
else if (PARTE == "prueba") prueba();
else if (PARTE == "corte_cabeza") intersection() { ensamble(); translate([-150, 0, 100]) cube([150, 150, 120]); }
else if (PARTE == "corte_x") difference() { ensamble(); translate([CORTE_X, -150, -1]) cube([150, 300, 300]); }
else if (PARTE == "corte_apretado") difference() { ensamble(true); translate([0, -150, -1]) cube([150, 300, 300]); }
