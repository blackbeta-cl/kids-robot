// =====================================================================
//  Kids Robot - version escritorio v1
//  Base con bateria + servo, cabeza con OLED, parlante, micro y tacto.
//
//  Uso:
//    openscad -D "PARTE=\"cabeza\"" -o stl/cabeza.stl escritorio.scad
//    (o cambiar PARTE abajo y exportar desde OpenSCAD)
//
//  Ejes: X derecha, Y adelante, Z arriba.  Suelo en Z = 0.
// =====================================================================

include <parametros.scad>

PARTE = "ensamble";

// ---------------------------------------------------------------------
//  Utilidades
// ---------------------------------------------------------------------

module caja_redonda(x, y, z, r = 3) {
  if (r > 0.01)
    hull() for (a = [-1, 1], b = [-1, 1])
      translate([a * (x / 2 - r), b * (y / 2 - r), 0]) cylinder(r = r, h = z, $fn = fn);
  else
    translate([-x / 2, -y / 2, 0]) cube([x, y, z]);
}

module caja_redonda_c(x, y, z, r = 3) {
  translate([0, 0, -z / 2]) caja_redonda(x, y, z, r);
}

// ---------------------------------------------------------------------
//  Base: carcasa, tapa con servo, cajon de bateria
// ---------------------------------------------------------------------

module base() {
  difference() {
    caja_redonda(BASE_X, BASE_Y, BASE_Z, BASE_R);

    // vaciado
    translate([0, 0, piso])
      caja_redonda(BASE_X - 2 * pared, BASE_Y - 2 * pared, BASE_Z + 1, BASE_R - pared);

    // boca del cajon (frente)
    translate([0, BASE_Y / 2 - 1.2, 18]) cube([112, 4, 30], center = true);

    // interruptor y conector de carga (atras)
    translate([25, -BASE_Y / 2, 20]) cube([14, 6, 9], center = true);
    translate([45, -BASE_Y / 2, 30]) rotate([90, 0, 0])
      cylinder(d = 9, h = 6, center = true, $fn = 32);

    // alojamientos de las patas de goma
    for (a = [-1, 1], b = [-1, 1])
      translate([a * 50, b * 50, -0.1]) cylinder(d = 22, h = 2.0, $fn = 32);
  }

  // torres de la tapa
  for (a = [-1, 1], b = [-1, 1])
    translate([a * 60, b * 60, BASE_Z - 8])
      difference() {
        cylinder(d = 9, h = 8, $fn = 32);
        translate([0, 0, -0.1]) cylinder(d = 2.7, h = 8.2, $fn = 24);
      }
}

module tapa_base() {
  difference() {
    caja_redonda(BASE_X, BASE_Y, TAPA, BASE_R);

    // alojamiento del servo
    translate([0, 0, -0.1]) cube([SG_X + 1, SG_Y + 1, 6], center = true);
    for (y = [-SG_AGUJ / 2, SG_AGUJ / 2])
      translate([0, y, 1.0]) cylinder(d = 2.1, h = 3.0, $fn = 20);

    // ranura en arco para el cable
    translate([0, 0, -0.1]) rotate([0, 0, 170])
      rotate_extrude(angle = 200, $fn = 96)
        translate([21, 0]) square([6, 6]);

    // tornillos a la carcasa
    for (a = [-1, 1], b = [-1, 1])
      translate([a * 60, b * 60, -0.1]) cylinder(d = 3.4, h = 5, $fn = 20);
  }

  // anillo de apoyo del plato
  translate([0, 0, TAPA]) difference() {
    cylinder(d = ANILLO_D, h = ANILLO_H, $fn = fn);
    cylinder(d = ANILLO_ID, h = ANILLO_H + 1, center = true, $fn = fn);
  }
}

module cajon() {
  difference() {
    union() {
      // fondo
      translate([0, 30, 1.2]) cube([110, 66, 2.4], center = true);
      // laterales
      for (s = [-1, 1]) translate([s * 53.8, 30, 14]) cube([2.4, 66, 28], center = true);
      // trasera
      translate([0, -1.8, 14]) cube([110, 2.4, 28], center = true);
      // frente
      translate([0, 64, 16]) cube([111, 2, 32], center = true);
    }

    // paso de cables
    translate([0, -1.8, 14]) cube([20, 4, 8], center = true);
    // ranuras de la correa
    for (x = [-40, 40], y = [-10, 10])
      translate([x, 30 + y, 1.2]) cube([20, 4, 3], center = true);
    // uñero
    translate([0, 64, 31]) cube([30, 4, 6], center = true);
  }
}

// ---------------------------------------------------------------------
//  Plato giratorio (va sobre el cuerno del servo)
// ---------------------------------------------------------------------

module plato_giro() {
  difference() {
    union() {
      caja_redonda(PLATO, PLATO, PLATO_T, 6);
      translate([0, 0, -LIP_H]) difference() {
        cylinder(d = LIP_D, h = LIP_H, $fn = fn);
        cylinder(d = LIP_ID, h = LIP_H + 1, center = true, $fn = fn);
      }
    }

    // paso de cables
    translate([0, -24, -LIP_H - 1]) cylinder(d = 12, h = LIP_H + PLATO_T + 2, $fn = 32);

    // alojamiento del cuerno
    translate([0, 0, -0.6]) cylinder(d = 21, h = 1.2, $fn = 48);
    for (x = [-7, 7]) translate([x, 0, -0.1])
      cylinder(d = 2.2, h = PLATO_T + 0.2, $fn = 16);

    // tornillos a la cabeza (dentro del anillo, sin tocar el anillo)
    for (a = [-1, 1], b = [-1, 1])
      translate([a * 20, b * 20, -LIP_H - 1])
        cylinder(d = 3.4, h = LIP_H + PLATO_T + 2, $fn = 20);
  }
}

// ---------------------------------------------------------------------
//  Cabeza
// ---------------------------------------------------------------------

module cabeza() {
  difference() {
    caja_redonda(CAB_X, CAB_Y, CAB_Z, CAB_R);

    // vaciado, abierta por atras
    translate([0, -36, piso])
      cube([CAB_X - 2 * pared, 68.6, CAB_Z - 2 * pared], center = false);

    // ventana OLED
    translate([0, CAB_Y / 2 - 1, OLED_Z]) cube([VENT_W, 4, VENT_H], center = true);

    // parlante
    translate([0, CAB_Y / 2, PARLANTE_Z]) rotate([90, 0, 0])
      cylinder(d = PARLANTE_D, h = 6, center = true, $fn = fn);

    // micro (costado izquierdo)
    translate([-CAB_X / 2, MIC_Y, MIC_Z]) rotate([0, 90, 0])
      cylinder(d = 2, h = 6, center = true, $fn = 24);

    // almohadilla de tacto
    translate([PAD_X, 0, CAB_Z - 1.6]) cylinder(d = PAD_D, h = 1.7, $fn = fn);

    // paso de cables por el fondo
    translate([0, -24, -0.1]) cylinder(d = 12, h = piso + 0.2, $fn = 32);
  }

  // jefes del plato (tornillos desde abajo)
  for (a = [-1, 1], b = [-1, 1])
    translate([a * 20, b * 20, piso]) difference() {
      cylinder(d = 9, h = 6, $fn = 32);
      translate([0, 0, -0.1]) cylinder(d = 2.5, h = 8, $fn = 20);
    }

  // soportes de la OLED
  for (a = [-1, 1], b = [-1, 1])
    translate([a * OLED_AGUJ / 2, CAB_Y / 2 - 4.4, OLED_Z + b * OLED_AGUJ / 2])
      rotate([90, 0, 0]) difference() {
        cylinder(d = 7, h = 4, center = true, $fn = 24);
        cylinder(d = 1.8, h = 5.2, center = true, $fn = 16);
      }

  // anillo del parlante
  translate([0, CAB_Y / 2 - pared, PARLANTE_Z]) rotate([90, 0, 0])
    difference() {
      cylinder(d = 46, h = 3, $fn = fn);
      cylinder(d = 40, h = 4, center = true, $fn = fn);
    }

  // postes del micro
  for (y = [MIC_Y - 8, MIC_Y + 8], z = [MIC_Z - 8, MIC_Z + 8])
    translate([-CAB_X / 2 + pared + 3, y, z]) rotate([0, 90, 0])
      cylinder(d = 3, h = 4, $fn = 16);

  // postes del TTP223
  for (a = [-1, 1], b = [-1, 1])
    translate([PAD_X + a * 7, b * 9, CAB_Z - pared - 2])
      cylinder(d = 3, h = 2, $fn = 16);

  // bloques traseros para el panel
  for (a = [-1, 1], z = [10, 72])
    translate([a * 50, -CAB_Y / 2 + 4, z])
      difference() {
        cube([10, 8, 8], center = true);
        rotate([90, 0, 0]) cylinder(d = 2.5, h = 10, center = true, $fn = 20);
      }
}

// ---------------------------------------------------------------------
//  Panel trasero con bandeja del ESP32
// ---------------------------------------------------------------------

module tapa_cabeza() {
  difference() {
    // panel
    translate([0, -CAB_Y / 2 - 1.5, (CAB_Z) / 2 + 1]) cube([108, 3, 80], center = true);

    // USB del ESP32
    translate([0, -CAB_Y / 2 - 1.5, 63]) cube([12, 5, 5], center = true);

    // ventilacion
    for (x = [-20, 20]) translate([x, -CAB_Y / 2 - 1.5, 76])
      cube([6, 5, 8], center = true);

    // tornillos
    for (a = [-1, 1], z = [10, 72])
      translate([a * 50, -CAB_Y / 2 - 1.5, z]) rotate([90, 0, 0])
        cylinder(d = 3.4, h = 6, center = true, $fn = 20);
  }

  // bandeja del ESP32 (hacia adentro de la cabeza)
  translate([0, -CAB_Y / 2 + 15, 48]) {
    difference() {
      cube([60, 30, 2], center = true);
      for (x = [-12, 12]) translate([x, 0, 0]) cube([4, 10, 4], center = true);
    }
    for (s = [-1, 1]) translate([s * 10, 0, 4])
      cube([3, 30, 5], center = true);
  }
}

// ---------------------------------------------------------------------
//  Rejilla del parlante y cupon de calibracion
// ---------------------------------------------------------------------

module rejilla() {
  difference() {
    cylinder(d = 39.4, h = 3, $fn = fn);
    for (r = [5 : 6 : 17], a = [0 : 30 : 330])
      rotate([0, 0, a]) translate([r, 0, -0.1])
        cylinder(d = 3.5, h = 4, $fn = 16);
  }
}

module calibracion() {
  difference() {
    translate([0, 0, 0]) cube([60, 30, 4], center = true);

    // agujeros de prueba: 1,8 / 2,1 / 2,2 / 2,5 / 2,7 / 3,4 / 4,2
    for (i = [0 : 6])
      translate([-24 + i * 8, 6, -2])
        cylinder(d = [1.8, 2.1, 2.2, 2.5, 2.7, 3.4, 4.2][i], h = 6, $fn = 24);

    // alojamiento del inserto M3
    translate([-18, -8, 0]) cylinder(d = 4.2, h = 6, center = true, $fn = 24);
    translate([0, -8, 0]) cylinder(d = 3.4, h = 6, center = true, $fn = 24);
    translate([18, -8, 0]) cylinder(d = 2.1, h = 6, center = true, $fn = 20);
  }
}

// ---------------------------------------------------------------------
//  Ensamble
// ---------------------------------------------------------------------

module ensamble() {
  // base
  color("dimgray") base();
  color("gray") translate([0, 0, BASE_Z]) tapa_base();
  color("darkgray") translate([0, 0, CAJON_Z0]) cajon();

  // servo (cuerpo y cuerno)
  color("dodgerblue") translate([0, 0, 37.5]) cube([12.2, 22.8, 22.5], center = false);
  color("steelblue") translate([0, 0, 60]) cube([12.2, 32.6, 2.2], center = false);
  color("white") translate([0, 0, 64]) cylinder(d = 20, h = 2, $fn = 32);
  color("white") translate([0, 0, 60]) cylinder(d = 12, h = 4, $fn = 32);

  // plato y cabeza
  color("dimgray") translate([0, 0, PLATO_Z]) plato_giro();
  color("lightgray") translate([0, 0, CAB_Z0]) cabeza();
  color("gray") translate([0, 0, CAB_Z0]) tapa_cabeza();

  // rejilla, parlante y OLED
  color("gray") translate([0, CAB_Y / 2, CAB_Z0 + PARLANTE_Z]) rotate([90, 0, 0]) rejilla();
  color("black") translate([0, CAB_Y / 2 - 6, CAB_Z0 + PARLANTE_Z]) rotate([90, 0, 0])
    cylinder(d = 40, h = 12, center = true, $fn = fn);
  color("black") translate([0, CAB_Y / 2 - 6, CAB_Z0 + OLED_Z])
    cube([27.3, 2, 27.3], center = true);

  // ESP32
  color("green") translate([0, (ESP_Y0 + ESP_Y0 + ESP_L) / 2, CAB_Z0 + ESP_Z0 + ESP_W / 2])
    cube([ESP_H, ESP_L, ESP_W], center = true);

  // tacto y micro
  color("red") translate([PAD_X, 0, CAB_Z0 + CAB_Z - 3])
    cube([11, 15, 1.6], center = true);
  color("orange") translate([-CAB_X / 2 + 1.6, MIC_Y, CAB_Z0 + MIC_Z])
    cube([3, 14, 14], center = true);

  // bateria y buck dentro del cajon
  color("silver") translate([0, 31, 12.8]) cube([100, 62, 16], center = true);
  color("royalblue") translate([0, -35, 9]) cube([45, 25, 10], center = true);

  // patas
  for (a = [-1, 1], b = [-1, 1])
    color("black") translate([a * 50, b * 50, -1]) cylinder(d = 20, h = 2, $fn = 32);
}

// ---------------------------------------------------------------------
//  Selector y orientacion de impresion
// ---------------------------------------------------------------------

module imprimir(p) {
  if (p == "base") base();
  else if (p == "tapa_base") tapa_base();
  else if (p == "cajon") cajon();
  else if (p == "plato_giro") translate([0, 0, LIP_H + 1]) rotate([180, 0, 0]) plato_giro();
  else if (p == "cabeza") translate([0, 0, CAB_Y / 2]) rotate([-90, 0, 0]) cabeza();
  else if (p == "tapa_cabeza") translate([0, 0, 38]) rotate([90, 0, 0]) tapa_cabeza();
  else if (p == "rejilla") rejilla();
  else if (p == "calibracion") calibracion();
  else echo("Pieza desconocida: ", p);
}

if (PARTE == "ensamble") ensamble();
else imprimir(PARTE);
