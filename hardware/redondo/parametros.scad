// =====================================================================
//  Kids Robot - version "redondo" v1 : todas las medidas (mm)
//  Ejes: X derecha, Y adelante (cara), Z arriba.  Mesa en Z = 0.
//  Las medidas marcadas MEDIR son tipicas del modulo, no medidas.
// =====================================================================

$fn   = 64;
NSE   = 96;      // puntos de cada rodaja superelipse
HOLG  = 0.25;    // holgura de encaje
PARED = 2.4;     // pared de cuerpo y cabeza (6 perimetros de 0,4)

// ---------------- Cuerpo (tipo "gomita") ----------------
C_A    = 64;     // semiancho maximo  -> 128 de ancho
C_B    = 54;     // semifondo maximo  -> 108 de fondo
C_M    = 2.6;    // seccion horizontal: 2 = elipse, mas = mas cuadrado
C_N    = 2.5;    // perfil vertical (barriga)
C_HS   = 108;    // altura del "huevo" completo antes del corte
C_Z0   = 3;      // el cuerpo apoya sobre la base
C_TOP  = 96;     // corte plano de arriba (asiento del cuello)
C_CHAF = 1.2;    // chaflan del borde de abajo

// ---------------- Base ----------------
BASE_H  = 3;
BOSS_XY = [[45, 38], [-45, 38], [45, -38], [-45, -38]];   // torres del cuerpo
BOSS_H  = 7;
INS_D   = 4.2;   // inserto M3 de calor (probar 4.0 / 4.4 en la prueba)
INS_L   = 6;
M3      = 3.4;

// ---------------- Cuello: labio, soporte, disco ----------------
LABIO_R  = 21;    // abertura del labio (pasa el brazo del servo)
LABIO_Z  = 94;    // donde empieza el cono de 45 grados bajo el labio
DISCO_R  = 26;
DISCO_H  = 4;
DISCO_Z  = C_TOP;            // el disco apoya en el labio
CUERNO_REC = 2.0;            // rebaje del brazo del servo bajo el disco
TUBO_E   = 2;
RECORRIDO = 2.0;             // lo que baja la cabeza al apretarla
PISO_Z   = 112;              // piso de la cabeza en reposo (cara de abajo)
PISO_H   = 3;
TUBO_TOP = PISO_Z - RECORRIDO;   // el tubo es el tope del boton
POSTE_R  = 17;               // radio de los 3 postes guia
POSTE_ANG = [30, 150, 270];
POSTE_D  = 7.5;
POSTE_H  = 4;
CABLE_XY = [-9, -11];        // paso de cables en disco y piso
CABLE_D  = 11;
SOP_ANG  = [60, 180, 300];   // columnas del soporte del servo
SOP_R    = 24;
SOP_PLACA_R = 27;

// ---------------- Cabeza (burbuja con cara plana) ----------------
H_A   = 56;      // semiancho -> 112
H_B   = 47;      // semifondo -> 94
H_M   = 3;       // seccion horizontal
H_N   = 2.6;     // cupula
H_RIM = PISO_Z + PISO_H;     // 115, borde inferior de la cascara
H_A0  = 40;      // semiejes en el borde inferior (sube a 45 grados)
H_B0  = 34;
H_ZC  = 131;     // donde empieza la cupula
H_HD  = 65;
H_TOP = 194;     // corte plano arriba: la zona del "boton"
H_CARA = 42;     // la cara es plana en Y = +42
H_PEST = 3;      // pestana interior del borde (alli atornilla el piso)
H_PEST_W = 6;
H_TORRES = [[32, 12], [-32, 12], [32, -12], [-32, -12]];
VISOR_W = 50; VISOR_H = 36; VISOR_R = 7; VISOR_P = 1.6;
VISOR_Z = 150;
OREJA_Z = 150; OREJA_D = 22; OREJA_E = 5; OREJA_PERNO = 8;

// ---------------- Componentes (MEDIR antes de imprimir) ----------------
// ESP32-S3 N16R8 DevKit (dos USB-C en el mismo extremo)
ESP_L = 69;   ESP_W = 25.4;  ESP_PCB = 1.6;          // MEDIR largo
ESP_X = -10;  ESP_Y0 = -49.5;                        // extremo USB atras
ESP_Z = C_Z0 + BASE_H - 3 + 20;                      // cara de abajo del PCB = 23
USB_ANCHO = 26; USB_ALTO = 8.5;                      // ventana para los dos USB-C

// OLED 0,96" SSD1306
OLED_W = 27.3; OLED_H = 27.8; OLED_T = 3.8;          // T: vidrio + PCB, MEDIR
OLED_AA = [21.7, 10.9];                              // area activa
OLED_VENT = [24.5, 13];
OLED_CZ = 144;                                       // centro del modulo
OLED_AG = 23.5; OLED_BOSS_D = 3.8;                   // agujeros de las esquinas, M2
OLED_VDZ = 2;                                        // area activa sobre el centro, MEDIR

// INMP441
MIC_W = 14; MIC_H = 14; MIC_T = 2.8;                 // T: PCB + espuma, MEDIR
MIC_X = 28; MIC_Z = 146;

// MAX98357A + condensador 470 uF
AMP_W = 17.8; AMP_L = 19.3; AMP_XY = [32, -2];
CAP_D = 10; CAP_H = 13; CAP_XY = [32, -24];

// Parlante 50 mm 4 ohm
PARL_D = 50; PARL_P = 18;                            // P: profundidad, MEDIR
PARL_Z = 33;
PARL_Y = 46.6;                                       // plano del borde del parlante

// SG90
SV_X = 22.8; SV_Y = 12.2; SV_Z = 22.5;
SV_OFF = 5.3;                                        // eje corrido del centro de la caja
SV_OREJA_L = 32.4; SV_OREJA_E = 2.5; SV_OREJA_Z = 15.8; SV_OREJA_AG = 27.8;
SV_EJE_TOP = 29.7;                                   // punta del eje desde abajo
SV_CUERNO_TOP = 30.7;
SV_Z0 = DISCO_Z + CUERNO_REC - SV_CUERNO_TOP;        // fondo de la caja del servo

// Microswitch con rodillo (tipo KW12 mini), MEDIR
SW_L = 12.8; SW_E = 5.8; SW_H = 6.5;
SW_AG = 6.5; SW_AG_D = 2.3; SW_AG_Z = 2.0;           // agujeros desde la cara de terminales
SW_ROD_X = 4.5; SW_ROD_D = 4.8; SW_ROD_H = 3.5;      // rodillo: posicion y cuanto sobresale
SW_TERM = 3.5;
DEDO_D = 9;
DEDO_H = (PISO_Z - SW_H - SW_ROD_H) - (DISCO_Z + DISCO_H) - 0.3;   // ~1,7

// ESP32-CAM (AI-Thinker, camara doblada sobre el modulo).  Va en la cabeza,
// detras del OLED, con el lente asomando por el visor.  MEDIR.
CAM_W = 27; CAM_L = 40.5; CAM_PCB = 1.2;
CAM_FRENTE = 9.5;          // de la cara del PCB a la punta del lente
CAM_LENTE_TOP = 12;        // centro del lente bajo el borde superior del PCB
CAM_LENTE_Z = 163; CAM_LENTE_D = 10;

// VL53L0X (distancia por laser infrarrojo), modulo negro de 6 pines.  MEDIR.
VL_W = 10.7; VL_H = 25; VL_T = 2.8;  // T: PCB + sensor
VL_X = -28; VL_Z = 146; VL_SENS_DZ = 0; VL_VENT = [6, 4];

// PIR HC-SR501 en el pecho.  MEDIR (si llega AM312, cambiar a 12 x 12).
PIR_W = 32; PIR_H = 24; PIR_LENTE_D = 23; PIR_LENTE_P = 12; PIR_ATRAS = 8;
PIR_Z = 76; PIR_Y = 31;     // cara del PCB (la pared se inclina: no adelantar)
PIR_AG = 28;               // agujeros M2 de la placa

// Resortes de lapiz (3)
RES_D = 5; RES_L = 12;
