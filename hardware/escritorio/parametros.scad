// =====================================================================
//  Kids Robot - version escritorio v1
//  Cabeza sobre una base con bateria y servo.  Sin ruedas ni cuerpo.
//  Medidas en milimetros.  Ejes: X derecha, Y adelante, Z arriba.
// =====================================================================

// --- Impresion
pared   = 2.4;
piso    = 2.4;
holgura = 0.3;
fn      = 48;

// --- Base
BASE_X = 130;
BASE_Y = 130;
BASE_Z = 56;          // carcasa de la base
BASE_R = 10;
TAPA   = 4;           // tapa de la base
BASE_TOP = BASE_Z + TAPA;   // 60

// --- Servo SG90 (giro del cuello)
SG_X      = 12.2;
SG_Y      = 22.8;
SG_Z      = 22.5;
SG_OREJAS = 32.6;
SG_AGUJ   = 27.8;

// --- Anillo de apoyo y plato giratorio
ANILLO_D  = 70;
ANILLO_ID = 60;
ANILLO_H  = 3;        // 60..63
PLATO     = 70;
PLATO_T   = 4;        // 66..70
PLATO_Z   = 66;
LIP_D     = 80;
LIP_ID    = 62;
LIP_H     = 3;        // 63..66

// --- Cabeza
CAB_X = 110;
CAB_Y = 70;
CAB_Z = 82;
CAB_R = 8;
CAB_Z0 = 70;          // altura de la base de la cabeza

// --- Pantalla OLED 0.96"
OLED_W = 27.3;
OLED_H = 27.3;
OLED_T = 1.6;
OLED_AGUJ = 23.5;
VENT_W = 24.0;
VENT_H = 12.5;
OLED_Z = 61;          // centro de la ventana en la cabeza

// --- Parlante, micro y tacto
PARLANTE_D = 40;
PARLANTE_Z = 28;      // centro del parlante
MIC_Z = 65;
MIC_Y = 18;
MIC   = 14;           // placa INMP441
TTP_W = 11;
TTP_H = 15;
PAD_D = 30;
PAD_X = -10;

// --- ESP32 DevKit 38 pines (dentro de la cabeza)
ESP_L = 55.5;
ESP_W = 28.5;
ESP_H = 14;
ESP_Z0 = 49;          // borde inferior de la placa
ESP_Y0 = -31;         // borde trasero
ESP_X  = 7;           // mitad del espesor

// --- Cajon de bateria / power bank
CAJON_X = 110;
CAJON_Y = 68;
CAJON_Z = 28;         // altura del cuerpo
CAJON_Z0 = piso;      // se apoya en el piso de la base
