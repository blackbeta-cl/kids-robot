// =====================================================================
//  Modelos simplificados de los componentes del robot (para encajar el
//  case, no para fabricar).  Cada modulo esta en su propio marco:
//  ver el comentario de cada uno.  Medidas en parametros.scad.
//  Requiere: include <parametros.scad> antes.
// =====================================================================

module _caja(x, y, z, c = [0, 0, 0]) { translate(c - [x / 2, y / 2, 0]) cube([x, y, z]); }

// ESP32-S3 DevKit N16R8.  PCB en Z 0..1,6; extremo USB en Y = 0, antena en Y = L.
module c_esp32s3() {
  color("#1d3557") translate([-ESP_W / 2, 0, 0]) cube([ESP_W, ESP_L, ESP_PCB]);
  // modulo WROOM-1 (18 x 25,5) en el extremo de la antena
  color("#c0c4c8") translate([-9, ESP_L - 25.5, ESP_PCB]) cube([18, 19, 3.1]);
  color("#1d3557") translate([-9, ESP_L - 6.5, ESP_PCB]) cube([18, 6.5, 0.8]);
  // dos USB-C (CH343 y nativo)
  for (x = [-6.3, 6.3])
    color("#adb5bd") translate([x - 4.5, -1, ESP_PCB]) cube([9, 7.5, 3.2]);
  // botones BOOT / RST
  for (x = [-9, 9]) color("#495057") translate([x - 2, 8, ESP_PCB]) cube([4, 3, 1.6]);
  // LED RGB
  color("white") translate([-1, 12, ESP_PCB]) cube([2, 2, 0.8]);
  // pines hacia abajo: 2 filas de 22 a 22,86 mm
  for (s = [-1, 1], i = [0:21]) {
    color("#111") translate([s * 11.43 - 1.27, 5 + i * 2.54 - 1.27, -2.5]) cube([2.54, 2.54, 2.5]);
    color("gold") translate([s * 11.43 - 0.32, 5 + i * 2.54 - 0.32, -8.5]) cube([0.64, 0.64, 8.5]);
  }
}

// OLED 0,96" I2C.  PCB en el plano XY, vidrio hacia +Z, conector arriba (+Y).
module c_oled() {
  color("#1d4ed8") difference() {
    _caja(OLED_W, OLED_H, 1.2);
    for (a = [-1, 1], b = [-1, 1]) translate([a * 11.75, b * 11.75, -1]) cylinder(d = 2, h = 3, $fn = 16);
  }
  color("#111") translate([0, -1.2, 1.2]) _caja(26.7, 19.3, OLED_T - 1.2 - 0.6);
  color("#0b2545") translate([0, OLED_VDZ, OLED_T - 0.6]) _caja(OLED_AA[0], OLED_AA[1], 0.6);
  for (i = [0:3]) color("gold") translate([(i - 1.5) * 2.54, OLED_H / 2 - 1.5, -6]) cylinder(d = 0.64, h = 6, $fn = 8);
}

// INMP441.  PCB en XY, cara del agujero del micro hacia +Z (va contra la pared).
module c_inmp441() {
  color("#1f6f8b") difference() {
    _caja(MIC_W, MIC_H, 1.6);
    translate([0, 0, -1]) cylinder(d = 1, h = 4, $fn = 12);
  }
  color("#999") translate([0, 0, -1]) _caja(4, 3, 1);           // capsula al reverso
  color("#ffcf99", 0.7) translate([0, 0, 1.6]) difference() {  // anillo de espuma
    cylinder(d = 7, h = MIC_T - 1.6, $fn = 24);
    translate([0, 0, -1]) cylinder(d = 3, h = 4, $fn = 16);
  }
  for (i = [0:5]) color("gold") translate([(i - 2.5) * 2.54, -MIC_H / 2 + 1.3, -7]) cylinder(d = 0.64, h = 7, $fn = 8);
}

// MAX98357A.  PCB en XY; bornera del parlante en +Y, pines en -Y.
module c_max98357() {
  color("#6a0dad") _caja(AMP_W, AMP_L, 1.6);
  color("#222") translate([0, 0, 1.6]) _caja(3, 3, 0.9);
  color("#2e86de") translate([0, AMP_L / 2 - 4, 1.6]) _caja(7.6, 7.5, 8);
  for (i = [0:6]) color("gold") translate([(i - 3) * 2.54, -AMP_L / 2 + 1.3, -8]) cylinder(d = 0.64, h = 8, $fn = 8);
}

module c_condensador() {
  color("#14213d") cylinder(d = CAP_D, h = CAP_H, $fn = 32);
  color("#adb5bd") translate([0, 0, CAP_H - 0.5]) cylinder(d = CAP_D - 1, h = 0.6, $fn = 32);
}

// Parlante 50 mm.  Borde frontal en Z = 0, mirando a +Z; el cuerpo va hacia -Z.
module c_parlante() {
  color("#343a40") difference() {
    translate([0, 0, -2]) cylinder(d = PARL_D, h = 2, $fn = 64);
    translate([0, 0, -3]) cylinder(d = PARL_D - 7, h = 4, $fn = 64);
  }
  color("#212529") translate([0, 0, -10]) cylinder(d1 = 22, d2 = PARL_D - 6, h = 9, $fn = 64);
  color("#6c757d") translate([0, 0, -PARL_P]) cylinder(d = 28, h = 8, $fn = 48);
  color("#adb5bd") translate([0, 0, -3]) cylinder(d = 14, h = 1.5, $fn = 32);
}

// SG90.  Eje de salida en X = Y = 0; fondo de la caja en Z = 0.
module c_sg90(brazo = true) {
  color("#3a86ff") {
    translate([SV_OFF, 0, 0]) _caja(SV_X, SV_Y, SV_Z);
    translate([SV_OFF, 0, SV_OREJA_Z]) difference() {
      _caja(SV_OREJA_L, SV_Y, SV_OREJA_E);
      for (s = [-1, 1]) translate([s * SV_OREJA_AG / 2, 0, -1]) cylinder(d = 2, h = 5, $fn = 12);
    }
    cylinder(r = 5.9, h = SV_Z + 4, $fn = 40);
    translate([7, 0, 0]) cylinder(r = 3, h = SV_Z + 4, $fn = 24);
  }
  color("white") cylinder(d = 4.8, h = SV_EJE_TOP, $fn = 24);
  if (brazo) color("white") {
    translate([0, 0, SV_CUERNO_TOP - 4]) cylinder(d = 7, h = 4, $fn = 32);
    translate([0, 0, SV_CUERNO_TOP - 1.6]) linear_extrude(1.6) hull() {
      for (s = [-1, 1]) translate([s * 16, 0]) circle(d = 4, $fn = 20);
      circle(d = 7, $fn = 24);
    }
  }
  color("#ff8c00") translate([SV_OFF - SV_X / 2 - 6, -1.5, 3]) cube([6, 3, 1.2]);   // cable
}

// Microswitch con palanca y rodillo.  Cara de terminales en Z = 0; la palanca
// sale por +Z; el rodillo esta en X = +SW_ROD_X.
module c_microswitch() {
  color("#222") difference() {
    _caja(SW_L, SW_E, SW_H);
    for (s = [-1, 1]) translate([s * SW_AG / 2, 0, SW_AG_Z]) rotate([90, 0, 0])
      cylinder(d = SW_AG_D, h = SW_E + 2, center = true, $fn = 16);
  }
  color("#e63946") translate([-0.5, 0, SW_H]) _caja(1.5, 1.5, 0.8);
  color("#ced4da") translate([-SW_L / 2 + 0.5, -2, SW_H + 0.2]) cube([SW_L / 2 + SW_ROD_X, 4, 0.4]);
  color("#f1f3f5") translate([SW_ROD_X, 0, SW_H + SW_ROD_H - SW_ROD_D / 2]) rotate([90, 0, 0])
    cylinder(d = SW_ROD_D, h = 3, center = true, $fn = 24);
  for (x = [-5, 0, 5]) color("silver") translate([x - 0.4, -1.6, -SW_TERM]) cube([0.8, 3.2, SW_TERM]);
}

// ESP32-CAM (AI-Thinker).  PCB en XY, lente hacia +Z; borde superior en +Y.
// El centro del lente queda a CAM_LENTE_TOP bajo el borde superior.
module c_esp32cam() {
  ly = CAM_L / 2 - CAM_LENTE_TOP;
  color("#2d6a4f") _caja(CAM_W, CAM_L, CAM_PCB);
  color("#c0c4c8") translate([0, -4, CAM_PCB]) _caja(18, 25.5, 3.2);          // modulo ESP32-S
  color("#111") translate([0, ly, CAM_PCB + 3.2]) _caja(8.5, 8.5, 3.6);        // camara OV2640
  color("#333") translate([0, ly, CAM_PCB + 6.8]) cylinder(d = 7.5, h = CAM_FRENTE - CAM_PCB - 6.8, $fn = 32);
  color("#4cc9f0") translate([0, ly, CAM_FRENTE - 0.2]) cylinder(d = 3, h = 0.2, $fn = 24);
  color("#adb5bd") translate([0, -CAM_L / 2 + 6, -2.2]) _caja(14, 12, 2.2);     // zocalo microSD
  color("gold") translate([9.5, 14, CAM_PCB]) cylinder(d = 2, h = 1, $fn = 12);  // IPEX antena
  for (sx = [-1, 1], i = [0:7]) color("gold")
    translate([sx * (CAM_W / 2 - 1.27), -CAM_L / 2 + 6 + i * 2.54, -7]) cylinder(d = 0.64, h = 7, $fn = 8);
}

// VL53L0X.  PCB en XY, sensor hacia +Z; pines en el extremo +Y.
module c_vl53l0x() {
  color("#111") _caja(VL_W, VL_H, 1.6);
  color("#222") translate([0, VL_SENS_DZ, 1.6]) _caja(4.4, 2.4, 1.0);
  for (x = [-1.3, 1.3]) color("#555") translate([x, VL_SENS_DZ, 2.6]) cylinder(d = 0.9, h = 0.05, $fn = 12);
  for (i = [0:5]) color("gold") translate([(i - 2.5) * 1.6, VL_H / 2 - 1.3, -6]) cylinder(d = 0.64, h = 6, $fn = 8);
}

// PIR HC-SR501.  PCB en XY, lente (cupula) hacia +Z.
module c_pir() {
  color("#2a9d8f") difference() {
    _caja(PIR_W, PIR_H, 1.6);
    for (sx = [-1, 1]) translate([sx * PIR_AG / 2, 0, -1]) cylinder(d = 2, h = 4, $fn = 12);
  }
  color("white") translate([0, 0, 1.6]) _caja(23.5, 23.5, 2.5);
  color("white", 0.9) translate([0, 0, 4.1]) intersection() {
    sphere(d = PIR_LENTE_D, $fn = 48);
    translate([0, 0, 0]) cylinder(d = PIR_LENTE_D + 1, h = PIR_LENTE_P, $fn = 48);
  }
  color("#264653") translate([0, 0, -PIR_ATRAS]) _caja(9, 6, PIR_ATRAS);        // BISS0001
  for (sx = [-1, 1]) color("#e9c46a") translate([sx * 9, 4, -6]) cylinder(d = 6, h = 6, $fn = 20);  // potenciometros
}

// Resorte de lapiz: cilindro rayado (solo para ver donde va).
module c_resorte(largo) {
  color("#888") for (i = [0:8]) translate([0, 0, i * largo / 9])
    difference() {
      cylinder(d = RES_D, h = largo / 18, $fn = 24);
      translate([0, 0, -1]) cylinder(d = RES_D - 1, h = largo, $fn = 24);
    }
}

// Lamina con todos los componentes, para revisar medidas.
module lamina_componentes() {
  module et(t) color("#333") translate([0, -26, 0]) linear_extrude(0.6)
    text(t, size = 4, halign = "center", font = "Liberation Sans:style=Bold");
  translate([0, 0, 0])   { c_esp32s3(); et("ESP32-S3 N16R8"); }
  translate([60, 20, 0])  { c_oled(); et("OLED 0,96\""); }
  translate([100, 20, 0]) { c_inmp441(); et("INMP441"); }
  translate([150, 20, 0]) { c_max98357(); translate([20, 0, 0]) c_condensador(); translate([8, 0, 0]) et("MAX98357A + 470uF"); }
  translate([225, 20, 18]) { c_parlante(); translate([0, 0, -18]) et("Parlante 50 mm"); }
  translate([290, 20, 0]) { c_sg90(); et("SG90"); }
  translate([400, 20, 0]) { c_esp32cam(); et("ESP32-CAM"); }
  translate([445, 20, 0]) { c_vl53l0x(); et("VL53L0X (IR)"); }
  translate([490, 20, 8]) { c_pir(); translate([0, 0, -8]) et("PIR HC-SR501"); }
  translate([345, 20, 0]) { c_microswitch(); translate([20, 0, 0]) c_resorte(RES_L); et("Microswitch + resorte"); }
}
