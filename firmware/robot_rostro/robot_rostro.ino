/*
  Robot — Rostro v1 (prueba de hardware)
  ---------------------------------------
  Dibuja la cara del robot en la OLED, parpadea, cambia de emoción con
  transición suave y mueve el cuello (servo) sin tirones.
  Se controla desde el Monitor Serie o por Wi-Fi (POST /cmd con el token;
  ver wifi_config.h).

  Placa en Arduino IDE: "ESP32S3 Dev Module" (PSRAM: OPI PSRAM, Flash 16MB)
  Librerías (Herramientas > Administrar bibliotecas):
    - Adafruit SSD1306
    - Adafruit GFX Library
    - ArduinoJson (versión 7)

  Conexiones:
    OLED  VCC -> 3V3     GND -> GND     SDA -> GPIO8    SCL -> GPIO9
    Servo rojo -> VIN (5V)   marrón/negro -> GND   naranjo/amarillo -> GPIO13

  Comandos en el Monitor Serie (115200, "Nueva línea"):
    feliz                         cambia de emoción (cualquier nombre de emociones.h)
    cabeza 120                    gira el cuello (10 a 170 grados)
    demo                          pasa por todas las emociones
    lista                         muestra las emociones disponibles
    {"rostro":"feliz","cabeza":60}  el mismo formato que usa el servidor
    {"pantalla":{"grande":"14:32","medio":"18°C","chico":"Ciudad","seg":8}}
                                  muestra un texto unos segundos y vuelve a la cara
    wifi                          muestra el estado del Wi-Fi y la dirección del robot
    vol 30                        volumen del parlante (0 a 100)
    repetir                       vuelve a decir la última respuesta de voz

  Voz por toque (voz.h): mantén tocado el TTP223 (GPIO 14), habla, suelta; el servidor contesta por el
  parlante. Necesita el servidor (server/puente.py) y su dirección: voz_config.h o el comando "servidor" (ver servidor_cfg.h).

  Wi-Fi: escribe el nombre y la clave de tu red en wifi_config.h (misma carpeta).
  El robot queda en http://<NOMBRE_ROBOT>.local/  (POST /cmd, GET /estado; exigen el token).
*/

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ArduinoJson.h>
#include <WiFi.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include "emociones.h"
#include "wifi_config.h"
#include "redes.h"      // redes Wi-Fi guardadas en NVS (wifi_config.h queda como respaldo de desarrollo)
#include "voz.h"

#define ANCHO 128
#define ALTO 64
#define PIN_SDA 8    // ESP32-S3 (en el ESP32 clásico era 21)
#define PIN_SCL 9    // ESP32-S3 (en el ESP32 clásico era 22)
#define PIN_SERVO 13
#define BLANCO SSD1306_WHITE
#define NEGRO SSD1306_BLACK

Adafruit_SSD1306 pantalla(ANCHO, ALTO, &Wire, -1);

// Servo del cuello con el PWM nativo (LEDC) del core 3.x.
// ESP32Servo 3.2.1 pide más de 14 bits a 50 Hz, el S3 no puede y la librería se queda
// colgada en un while(1) sin avisar; con 14 bits funciona.
struct Cuello {
  static const uint8_t BITS = 14;
  uint8_t pin = 0;
  bool listo = false;
  void attach(uint8_t p) { pin = p; listo = ledcAttach(p, 50, BITS); }
  void write(int grados) {
    if (!listo) return;
    uint32_t us = map(constrain(grados, 0, 180), 0, 180, 500, 2400);   // mismo rango que antes
    ledcWrite(pin, (uint32_t)((uint64_t)us * ((1 << BITS) - 1) / 20000));
  }
};
Cuello cuello;
WebServer servidor(80);

// Cara "viva": mismos campos que Emocion, pero con decimales para las transiciones
struct Cara {
  float ancho, alto, redondez, separacion, altura, cejas, risa, miraX, miraY;
  uint8_t boca, extra, anim, velocidad, efecto;
};

Cara actual, desde, hacia;
bool enTransicion = false;
uint32_t inicioTransicion = 0;
const uint16_t DURACION_TRANSICION = 220;

bool parpadeando = false;
uint32_t inicioParpadeo = 0, proximoParpadeo = 0;
const uint16_t DURACION_PARPADEO = 160;

int anguloActual = 90, anguloObjetivo = 90;
uint32_t ultimoPasoServo = 0;
const uint8_t MS_POR_GRADO = 12;   // más alto = más lento y menos consumo de corriente

bool modoDemo = false;
uint32_t proximoDemo = 0;
int emocionActual = 0;
char nombreActual[24] = "";

// Cara y efecto "en vivo": el Taller los manda por Wi-Fi sin tener que recompilar
Efecto efectoVivo;
const uint8_t EFECTO_VIVO = 250;
bool servidorIniciado = false;
uint32_t ultimoRevisoWifi = 0;

// Pantalla de texto temporal (hora, temperatura...)
char textoGrande[24] = "", textoMedio[24] = "", textoChico[32] = "";
uint32_t textoHasta = 0;
bool hayTexto = false;

void agendaAgregarEstado(JsonDocument& doc);   // lo implementa agenda.h, incluido más abajo

#include "estado.h"   // feedback en pantalla: arranque, Wi-Fi y OTA (usa las variables de arriba)
#include "portal.h"       // portal cautivo para configurar el Wi-Fi (gesto de arranque, AP "Robot-XXXX", página)
#include "actualizar.h"   // actualización desde el servidor: consulta, cuenta regresiva de 30 s, descarga verificada
#include "agenda.h"       // avisos programados: GET /pendientes, reproduce y confirma (núcleo 0)

// Un firmware nuevo queda "pendiente" hasta que actAtender() lo da por bueno (45 s sin reiniciarse);
// si se cuelga antes, el bootloader vuelve al firmware anterior. (El core llama a esta función al iniciar.)
extern "C" bool verifyRollbackLater() { return true; }

uint32_t ultimoCuadro = 0;
char linea[200];
uint8_t largoLinea = 0;

// ---------- Emociones ----------

Cara caraDe(const Emocion& e) {
  Cara c = {(float)e.ancho, (float)e.alto, (float)e.redondez, (float)e.separacion, (float)e.altura,
            (float)e.cejas, (float)e.risa, (float)e.miraX, (float)e.miraY, e.boca, e.extra, e.anim, e.velocidad, e.efecto};
  return c;
}

int buscarEmocion(const char* nombre) {
  for (uint8_t i = 0; i < NUM_EMOCIONES; i++)
    if (strcasecmp(nombre, EMOCIONES[i].nombre) == 0) return i;
  return -1;
}

void ponerEmocion(int i) {
  if (i < 0 || i >= NUM_EMOCIONES) return;
  emocionActual = i;
  strncpy(nombreActual, EMOCIONES[i].nombre, sizeof(nombreActual) - 1);
  desde = actual;
  hacia = caraDe(EMOCIONES[i]);
  inicioTransicion = millis();
  enTransicion = true;
  Serial.printf("Rostro: %s\n", EMOCIONES[i].nombre);
}

float mezclar(float a, float b, float p) { return a + (b - a) * p; }

void avanzarTransicion(uint32_t ahora) {
  if (!enTransicion) return;
  float p = (ahora - inicioTransicion) / (float)DURACION_TRANSICION;
  if (p >= 1) { actual = hacia; enTransicion = false; return; }
  p = p * p * (3 - 2 * p);
  actual.ancho = mezclar(desde.ancho, hacia.ancho, p);
  actual.alto = mezclar(desde.alto, hacia.alto, p);
  actual.redondez = mezclar(desde.redondez, hacia.redondez, p);
  actual.separacion = mezclar(desde.separacion, hacia.separacion, p);
  actual.altura = mezclar(desde.altura, hacia.altura, p);
  actual.cejas = mezclar(desde.cejas, hacia.cejas, p);
  actual.risa = mezclar(desde.risa, hacia.risa, p);
  actual.miraX = mezclar(desde.miraX, hacia.miraX, p);
  actual.miraY = mezclar(desde.miraY, hacia.miraY, p);
  actual.boca = p < 0.5f ? desde.boca : hacia.boca;
  actual.extra = p < 0.5f ? desde.extra : hacia.extra;
  actual.anim = p < 0.5f ? desde.anim : hacia.anim;
  actual.velocidad = p < 0.5f ? desde.velocidad : hacia.velocidad;
  actual.efecto = p < 0.5f ? desde.efecto : hacia.efecto;
}

float aperturaOjos(uint32_t ahora) {
  if (!parpadeando && ahora >= proximoParpadeo) { parpadeando = true; inicioParpadeo = ahora; }
  if (!parpadeando) return 1;
  float p = (ahora - inicioParpadeo) / (float)DURACION_PARPADEO;
  if (p >= 1) { parpadeando = false; proximoParpadeo = ahora + random(2500, 5500); return 1; }
  return fabsf(1 - 2 * p);
}

// ---------- Dibujo (igual que la vista previa del Taller) ----------

int redondear(double v) { return (int)lround(v); }

void dibujarCorazon(int cx, int cy, int s, uint16_t col = BLANCO) {
  int q = s >> 2, yb = cy - s / 6;
  pantalla.fillCircle(cx - q, yb, q, col);
  pantalla.fillCircle(cx + q, yb, q, col);
  pantalla.fillTriangle(cx - 2 * q, yb, cx + 2 * q, yb, cx, yb + 2 * q + 2, col);
}

void dibujarEstrella(int cx, int cy, int s, double giro, uint16_t col = BLANCO) {
  int ro = (s >> 1) - 1, ri = (int)lround(ro * 0.45);
  int px[10], py[10];
  for (int k = 0; k < 10; k++) {
    int rad = (k & 1) ? ri : ro;
    double a = -PI / 2 + giro + k * PI / 5;
    px[k] = (int)lround(cx + rad * cos(a));
    py[k] = (int)lround(cy + rad * sin(a));
  }
  for (int k = 0; k < 10; k++) {
    int j = (k + 1) % 10;
    pantalla.fillTriangle(cx, cy, px[k], py[k], px[j], py[j], col);
  }
}

void dibujarMejilla(int cx, int cy) {
  for (int dy = -3; dy <= 3; dy++)
    for (int dx = -7; dx <= 7; dx++)
      if (9 * dx * dx + 49 * dy * dy <= 441 && ((cx + dx + cy + dy) & 1) == 0)
        pantalla.drawPixel(cx + dx, cy + dy, BLANCO);
}

void dibujarZ(int x, int y, int s, uint16_t col = BLANCO) {
  pantalla.drawLine(x, y, x + s, y, col);
  pantalla.drawLine(x + s, y, x, y + s, col);
  pantalla.drawLine(x, y + s, x + s, y + s, col);
}

// ---------- Efectos propios (piezas definidas en emociones.h) ----------

void dibujarParte(const Parte& p, const Cara& c, uint32_t t, const int ax[5], const int ay[5]) {
  uint16_t col = p.color ? BLANCO : NEGRO;
  uint64_t tp = (uint64_t)t * c.velocidad * p.vel / 25;   // cada pieza tiene su propia velocidad
  int dx = p.dx, dy = p.dy, tam = p.tam, tam2 = p.tam2;
  double giro = 0;
  switch (p.anim) {
    case 1: if ((tp / 300) % 2) return; break;                                    // parpadea
    case 9: case 10: case 11: if ((tp / 400) % 4 < (uint64_t)(p.anim - 8)) return; break;  // aparece en el paso 1, 2 o 3
    case 2: dy += redondear(3 * sin(tp / 250.0)); break;                          // flota
    case 3: dy += (int)((tp / 60) % 30); break;                                   // cae
    case 4: dy -= (int)((tp / 60) % 30); break;                                   // sube
    case 5: { double f = 1 + 0.3 * sin(tp / 200.0); tam = redondear(tam * f); tam2 = redondear(tam2 * f); break; }  // late
    case 6: {                                                                     // órbita
      double a = tp / 500.0, ca = cos(a), sa = sin(a);
      int nx = redondear(dx * ca - dy * sa), ny = redondear(dx * sa + dy * ca);
      dx = nx; dy = ny; break;
    }
    case 7: giro = tp / 500.0; break;                                             // gira
    case 8: { uint64_t n = tp / 33; dx += (int)((n * n * 37 + n * 11) % 3) - 1; break; }  // tiembla
  }
  int x = ax[p.ancla] + dx, y = ay[p.ancla] + dy;
  int a1 = max(1, abs(tam)), a2 = max(1, abs(tam2));
  switch (p.forma) {
    case 0: pantalla.fillCircle(x, y, a1, col); break;
    case 1: pantalla.drawCircle(x, y, a1, col); break;
    case 2: pantalla.fillRect(x - (a1 >> 1), y - (a2 >> 1), a1, a2, col); break;
    case 3: {
      int vx = tam, vy = tam2;
      if (giro != 0) {
        double ca = cos(giro), sa = sin(giro);
        int nx = redondear(vx * ca - vy * sa), ny = redondear(vx * sa + vy * ca);
        vx = nx; vy = ny;
      }
      pantalla.drawLine(x, y, x + vx, y + vy, col);
      break;
    }
    case 4: {
      int h = a1 >> 1, hh = a2 >> 1;
      if (tam2 < 0) hh = -hh;
      pantalla.fillTriangle(x - h, y + hh, x + h, y + hh, x, y - hh, col);
      break;
    }
    case 5: dibujarCorazon(x, y, a1, col); break;
    case 6: dibujarEstrella(x, y, a1, giro, col); break;
    case 7:
      pantalla.fillCircle(x, y, a1, col);
      pantalla.fillTriangle(x - a1, y - 1, x + a1, y - 1, x, y - 2 * a1 - 1, col);
      break;
    case 8: dibujarZ(x, y, a1, col); break;
  }
}

void dibujarEfecto(const Efecto& ef, const Cara& c, uint32_t t, const int ax[5], const int ay[5]) {
  for (uint8_t i = 0; i < ef.n && i < 8; i++) dibujarParte(ef.p[i], c, t, ax, ay);
}

void dibujarCara(const Cara& c, uint32_t t, float abreIn) {  // abreIn: 1 = ojos abiertos, 0 = cerrados
  pantalla.clearDisplay();
  double abre = abreIn;

  // El tiempo de los movimientos corre más rápido o más lento según la velocidad
  uint32_t ts = (uint32_t)((uint64_t)t * c.velocidad / 5);
  int dx = 0, dy = 0, mx = redondear(c.miraX), wj = 0;
  double bostezo = 0;
  if (c.anim == 1) { uint64_t n = ts / 33; dx = (int)((n * n * 37 + n * 11) % 3) - 1; }   // temblar
  if (c.anim == 2) dy = redondear(2 * sin(ts / 250.0));                                    // saltar
  if (c.anim == 3) mx += redondear(6 * sin(ts / 700.0));                                   // mirar a los lados
  if (c.anim == 4) { wj = redondear(2 * sin(ts / 120.0)); dx = redondear(sin(ts / 120.0 + 1.6)); }  // gelatina
  if (c.anim == 5) {                                                                       // bostezo cada 4 s
    double u = (ts % 4000) / 4000.0;
    if (u < 0.45) { bostezo = sin(PI * u / 0.45); dy = -redondear(2 * bostezo); abre *= 1 - 0.75 * bostezo; }
  }

  int w = redondear(c.ancho) + wj, h = redondear(c.alto) - wj, r = redondear(c.redondez);
  int sep = redondear(c.separacion), e = redondear(c.cejas), risa = redondear(c.risa);
  int cy = 32 + redondear(c.altura) + redondear(c.miraY) + dy;
  int ojoIzqX = 0, ojoDerX = 0;

  for (int lado = -1; lado <= 1; lado += 2) {
    int cx = 64 + lado * ((sep >> 1) + (w >> 1)) + mx + dx;
    if (lado < 0) ojoIzqX = cx; else ojoDerX = cx;
    if (c.extra == 1 && abre > 0.6) { dibujarCorazon(cx, cy, w); continue; }
    if ((c.extra == 6 || c.extra == 7) && abre > 0.6) { dibujarEstrella(cx, cy, w, c.extra == 7 ? ts / 600.0 : 0); continue; }

    int hh = max(2, redondear(h * abre));
    int x0 = cx - (w >> 1), arriba = cy - (hh >> 1);
    int rr = min(r, min(w >> 1, hh >> 1));
    pantalla.fillRoundRect(x0, arriba, w, hh, rr, BLANCO);

    if (c.extra == 5 && abre > 0.6) {  // ojos brillantes: pupila grande, brillos y agua
      int pr = min(w, hh) / 2 - 2;
      if (pr >= 4) {
        int pcy = cy + 1, b = redondear(sin(ts / 150.0));
        pantalla.fillCircle(cx, pcy, pr, NEGRO);
        pantalla.fillCircle(cx - pr / 3 + b, pcy - pr / 3, max(1, pr / 3), BLANCO);
        pantalla.fillCircle(cx + pr / 3, pcy + pr / 3 - b, max(1, pr / 6), BLANCO);
        for (int x = -pr + 3; x <= pr - 3; x++)
          pantalla.drawPixel(cx + x, pcy + pr - 3 + redondear(sin((x * 2 + ts / 40.0) / 3.0)), BLANCO);
      }
    }

    if (e != 0) {  // cejas: se "corta" una esquina del ojo con un triángulo negro
      int interior = lado < 0 ? x0 + w : x0 - 1;
      int exterior = lado < 0 ? x0 - 1 : x0 + w;
      int bajo = e > 0 ? interior : exterior;
      int alto2 = e > 0 ? exterior : interior;
      pantalla.fillTriangle(bajo, arriba - 1, alto2, arriba - 1, bajo, arriba + abs(e), NEGRO);
    }

    int ri = min(redondear(risa * abre), hh - 3);  // ojos sonrientes: se tapa la parte de abajo
    if (ri > 0) pantalla.fillRoundRect(x0 - 1, arriba + hh - ri, w + 2, hh, rr, NEGRO);

    if (c.extra == 3) dibujarMejilla(cx, cy + (h >> 1) + 5);
  }

  if (c.extra == 2) {  // lágrima que cae
    int tx = ojoIzqX - (w >> 1) + 3;
    int ty = cy + (h >> 1) + 4 + (int)((t / 180) % 9);
    pantalla.fillCircle(tx, ty, 2, BLANCO);
    pantalla.fillTriangle(tx - 2, ty - 1, tx + 2, ty - 1, tx, ty - 5, BLANCO);
  }

  if (c.extra == 4) {  // Zzz
    int n = (t / 450) % 4;
    const int z[3][3] = {{100, 16, 3}, {107, 9, 4}, {115, 1, 5}};
    for (int i = 0; i < n; i++) dibujarZ(z[i][0], z[i][1], z[i][2]);
  }

  int bx = 64 + (mx >> 1) + dx, by = 52 + dy;
  if (bostezo > 0.05) {
    int mh = 4 + redondear(10 * bostezo);
    pantalla.fillRoundRect(bx - 6, by + 3 - (mh >> 1), 13, mh, min(6, mh >> 1), BLANCO);
  } else switch (c.boca) {
    case 1:
      for (int x = -10; x <= 10; x++) { int y = by + 4 - (4 * x * x + 50) / 100; pantalla.drawPixel(bx + x, y, BLANCO); pantalla.drawPixel(bx + x, y + 1, BLANCO); }
      break;
    case 2:
      pantalla.drawCircle(bx, by + 2, 4, BLANCO);
      pantalla.drawCircle(bx, by + 2, 3, BLANCO);
      break;
    case 3:
      pantalla.fillRect(bx - 8, by + 2, 17, 2, BLANCO);
      break;
    case 4:
      for (int x = -10; x <= 10; x++) { int y = by + (4 * x * x + 50) / 100; pantalla.drawPixel(bx + x, y, BLANCO); pantalla.drawPixel(bx + x, y + 1, BLANCO); }
      break;
  }

  const Efecto* ef = nullptr;                      // efecto propio, encima de todo
  if (c.efecto == EFECTO_VIVO) ef = &efectoVivo;
  else if (c.efecto > 0 && c.efecto < NUM_EFECTOS) ef = &EFECTOS[c.efecto];
  if (ef) {
    const int ax[5] = {64, ojoIzqX, ojoDerX, bx, 64 + mx + dx};
    const int ay[5] = {32, cy, cy, by + 3, cy};
    dibujarEfecto(*ef, c, t, ax, ay);
  }

  estSuperposicion(t);   // icono de Wi-Fi si no hay red
  pantalla.display();
}

// ---------- Cuello ----------

void moverCabeza(int grados) {
  anguloObjetivo = constrain(grados, 10, 170);
  Serial.printf("Cabeza -> %d grados\n", anguloObjetivo);
}

void avanzarServo(uint32_t ahora) {
  if (anguloActual == anguloObjetivo || ahora - ultimoPasoServo < MS_POR_GRADO) return;
  ultimoPasoServo = ahora;
  anguloActual += anguloObjetivo > anguloActual ? 1 : -1;
  cuello.write(anguloActual);
}

// ---------- Comandos ----------

void mostrarLista() {
  Serial.print("Emociones:");
  for (uint8_t i = 0; i < NUM_EMOCIONES; i++) { Serial.print(' '); Serial.print(EMOCIONES[i].nombre); }
  Serial.println();
}

void mostrarWifi();

int limitar(JsonVariantConst v, int minimo, int maximo, int porDefecto);

// Convierte UTF-8 a la tabla de la pantalla: quita tildes y deja el símbolo de grados (°)
void limpiarTexto(const char* src, char* dst, size_t n) {
  size_t k = 0;
  for (size_t i = 0; src[i] && k + 1 < n; i++) {
    uint8_t c = src[i];
    if (c < 0x80) { dst[k++] = c; continue; }
    uint8_t d = src[i + 1];
    if (c == 0xC2 && d == 0xB0) { dst[k++] = (char)0xF8; i++; continue; }
    if (c == 0xC3 && d) {
      i++;
      const char* de = "\xA1\xA9\xAD\xB3\xBA\xB1\xBC\x81\x89\x8D\x93\x9A\x91";
      const char* a = "aeiounuAEIOUN";
      for (int j = 0; de[j]; j++) if ((uint8_t)de[j] == d) { dst[k++] = a[j]; break; }
    }
    // cualquier otro símbolo se ignora; los bytes de continuación UTF-8 se saltan solos
  }
  dst[k] = 0;
}

void mostrarTexto(JsonObjectConst o) {
  limpiarTexto(o["grande"] | "", textoGrande, sizeof(textoGrande));
  limpiarTexto(o["medio"] | "", textoMedio, sizeof(textoMedio));
  limpiarTexto(o["chico"] | "", textoChico, sizeof(textoChico));
  int seg = limitar(o["seg"], 1, 30, 8);
  hayTexto = textoGrande[0] || textoMedio[0] || textoChico[0];
  textoHasta = millis() + (uint32_t)seg * 1000;
  Serial.printf("Pantalla de texto: %s | %s | %s\n", textoGrande, textoMedio, textoChico);
}

void lineaCentrada(const char* t, int tam, int y) {
  int w = (int)strlen(t) * 6 * tam;
  pantalla.setTextSize(tam);
  pantalla.setCursor(max(0, (ANCHO - w) / 2), y);
  pantalla.print(t);
}

void dibujarTexto() {
  pantalla.clearDisplay();
  pantalla.setTextColor(BLANCO);
  pantalla.setTextWrap(false);
  int lg = strlen(textoGrande), lm = strlen(textoMedio), lc = strlen(textoChico);
  int tg = lg ? constrain(ANCHO / (6 * lg), 1, 4) : 0;
  int tm = lm ? constrain(ANCHO / (6 * lm), 1, 2) : 0;
  int hg = 8 * tg, hm = 8 * tm, hc = lc ? 8 : 0;
  int total = hg + hm + hc + ((hg && hm) ? 4 : 0) + (((hg || hm) && hc) ? 4 : 0);
  int y = max(0, (ALTO - total) / 2);
  if (lg) { lineaCentrada(textoGrande, tg, y); y += hg + 4; }
  if (lm) { lineaCentrada(textoMedio, tm, y); y += hm + 4; }
  if (lc) { lineaCentrada(textoChico, 1, y); }
  pantalla.display();
}

// ---------- Cara en vivo (llega por Wi-Fi desde el Taller) ----------

int limitar(JsonVariantConst v, int minimo, int maximo, int porDefecto) {
  if (!v.is<int>()) return porDefecto;
  return constrain(v.as<int>(), minimo, maximo);
}

bool aplicarCaraViva(JsonObjectConst o) {
  Cara c;
  c.ancho = limitar(o["ancho"], 8, 44, 30);
  c.alto = limitar(o["alto"], 2, 40, 30);
  c.redondez = limitar(o["redondez"], 0, 20, 8);
  c.separacion = limitar(o["separacion"], 2, 40, 14);
  c.altura = limitar(o["altura"], -14, 14, -4);
  c.cejas = limitar(o["cejas"], -14, 14, 0);
  c.risa = limitar(o["risa"], 0, 24, 0);
  c.miraX = limitar(o["miraX"], -10, 10, 0);
  c.miraY = limitar(o["miraY"], -8, 8, 0);
  c.boca = limitar(o["boca"], 0, 4, 0);
  c.extra = limitar(o["extra"], 0, 7, 0);
  c.anim = limitar(o["anim"], 0, 5, 0);
  c.velocidad = limitar(o["velocidad"], 1, 10, 5);
  c.efecto = 0;

  JsonArrayConst partes = o["efecto"]["partes"];
  if (!partes.isNull()) {
    efectoVivo.nombre = "vivo";
    uint8_t n = 0;
    for (JsonVariantConst v : partes) {
      if (n >= 8) break;
      Parte& p = efectoVivo.p[n++];
      p.forma = limitar(v["forma"], 0, 8, 0);
      p.ancla = limitar(v["ancla"], 0, 4, 0);
      p.anim = limitar(v["anim"], 0, 11, 0);
      p.vel = limitar(v["vel"], 1, 10, 5);
      p.color = limitar(v["color"], 0, 1, 1);
      p.dx = limitar(v["dx"], -64, 63, 0);
      p.dy = limitar(v["dy"], -32, 31, 0);
      p.tam = limitar(v["tam"], -64, 63, 3);
      p.tam2 = limitar(v["tam2"], -64, 63, 0);
    }
    efectoVivo.n = n;
    if (n > 0) c.efecto = EFECTO_VIVO;
  }

  modoDemo = false;
  desde = actual;
  hacia = c;
  inicioTransicion = millis();
  enTransicion = true;
  strncpy(nombreActual, o["nombre"] | "en vivo", sizeof(nombreActual) - 1);
  Serial.printf("Rostro en vivo: %s\n", nombreActual);
  return true;
}

void procesarLinea(char* txt) {
  while (*txt == ' ') txt++;
  if (!*txt) return;

  if (txt[0] == '{') {
    JsonDocument doc;
    if (deserializeJson(doc, txt)) { Serial.println("No entendí ese JSON"); return; }
    const char* rostro = doc["rostro"] | "";
    if (*rostro) {
      int i = buscarEmocion(rostro);
      if (i >= 0) { modoDemo = false; ponerEmocion(i); }
      else Serial.printf("No conozco la emoción '%s'\n", rostro);
    }
    if (doc["cara"].is<JsonObject>()) aplicarCaraViva(doc["cara"].as<JsonObjectConst>());
    if (doc["pantalla"].is<JsonObject>()) mostrarTexto(doc["pantalla"].as<JsonObjectConst>());
    if (doc["cabeza"].is<int>()) moverCabeza(doc["cabeza"].as<int>());
    return;
  }

  if (strncasecmp(txt, "cabeza", 6) == 0) { moverCabeza(atoi(txt + 6)); return; }
  if (strcasecmp(txt, "demo") == 0) { modoDemo = !modoDemo; proximoDemo = 0; Serial.println(modoDemo ? "Demo encendida" : "Demo apagada"); return; }
  if (strcasecmp(txt, "wifi") == 0) { mostrarWifi(); return; }
  if (strcasecmp(txt, "buscar") == 0) { actPidioBuscar = true; Serial.println("Actualizar: busco ahora en el servidor..."); return; }
  if (strcasecmp(txt, "agenda") == 0) { agendaForzar = true; Serial.println("Agenda: consulto ahora..."); return; }
  if (strcasecmp(txt, "anuncio") == 0) { anuncioOta(); return; }
  if (strcasecmp(txt, "version") == 0) { Serial.printf("Firmware v%s\n", FIRMWARE_VERSION); return; }
  if (strncasecmp(txt, "vol ", 4) == 0) { vozFijarVolumen(atoi(txt + 4)); return; }
  if (strcasecmp(txt, "repetir") == 0) { vozPidioRepetir = true; return; }
  if (strcasecmp(txt, "lista") == 0 || strcasecmp(txt, "ayuda") == 0) { mostrarLista(); return; }
  if (strcasecmp(txt, "conv") == 0) {
    vozConversacion = !vozConversacion;
    Serial.printf("Conversación: %s (espera %d ms tras responder)\n", vozConversacion ? "sí" : "no", VOZ_MS_ESPERA);
    return;
  }

  int i = buscarEmocion(txt);
  if (i >= 0) { modoDemo = false; ponerEmocion(i); }
  else { Serial.printf("No conozco '%s'. ", txt); mostrarLista(); }
}

// ---------- Wi-Fi ----------

void mostrarWifi() {
  if (!redesHay()) { Serial.println("Wi-Fi: no hay redes guardadas. Usa 'wifi agregar NOMBRE|CLAVE' por cable."); return; }
  if (WiFi.status() == WL_CONNECTED)
    Serial.printf("Wi-Fi: conectado a '%s'  IP %s  señal %d dBm  http://%s.local/\n", WiFi.SSID().c_str(), WiFi.localIP().toString().c_str(), WiFi.RSSI(), NOMBRE_ROBOT);
  else
    Serial.printf("Wi-Fi: conectando a '%s'...\n", redesNombreActual());
}

bool tokenValido() {
  if (!cfgToken[0]) return false;                       // sin token configurado el servidor local queda cerrado
  return servidor.header("x-token") == cfgToken;
}

void rutaComando() {
  if (!tokenValido()) { servidor.send(401, "application/json", "{\"ok\":false,\"error\":\"token\"}"); return; }
  String cuerpo = servidor.arg("plain");
  if (cuerpo.length() == 0 || cuerpo.length() > 3000) { servidor.send(400, "application/json", "{\"ok\":false,\"error\":\"cuerpo\"}"); return; }
  static char buf[3001];
  cuerpo.toCharArray(buf, sizeof(buf));
  procesarLinea(buf);
  servidor.send(200, "application/json", "{\"ok\":true}");
}

void rutaEstado() {
  if (!tokenValido()) { servidor.send(401, "application/json", "{\"ok\":false,\"error\":\"token\"}"); return; }
  JsonDocument doc;
  doc["ok"] = true;
  doc["rostro"] = nombreActual;
  doc["cabeza"] = anguloActual;
  doc["rssi"] = WiFi.RSSI();
  doc["version"] = FIRMWARE_VERSION;
  doc["segundos"] = millis() / 1000;
  doc["reinicio"] = estMotivoReinicio();
  doc["heap"] = ESP.getFreeHeap();
  doc["psram"] = ESP.getFreePsram();
  doc["ota"] = otaIniciado;
  agendaAgregarEstado(doc);
  vozAgregarEstado(doc);
  if (mic.lista) {       // captura del micrófono: leer reinicia la ventana. mic_hz debe ser ~16000 y mic_huecos 0
    float hz; uint32_t huecos, huecoMs, desbordes;
    micEstadisticas(hz, huecos, huecoMs, desbordes);
    doc["mic_hz"] = hz; doc["mic_huecos"] = huecos; doc["mic_hueco_ms"] = huecoMs; doc["mic_desbordes"] = desbordes;
  }
  String salida;
  serializeJson(doc, salida);
  servidor.send(200, "application/json", salida);
}


#if MIC_AUDIO_HTTP
// GET /mic/audio (con token): los últimos ~8 s que oyó el micrófono, como WAV de 16 kHz y ganancia x4. Solo existe en RAM.
void rutaMicAudio() {
  if (!tokenValido()) { servidor.send(401, "application/json", "{\"ok\":false,\"error\":\"token\"}"); return; }
  int16_t* pcm = nullptr;
  size_t bytes = micCopiarUltimos(&pcm, 16000 * 8, 6);
  if (!bytes) { servidor.send(404, "application/json", "{\"ok\":false,\"error\":\"sin audio\"}"); return; }
  uint8_t cab[44];
  uint32_t riff = 36 + bytes, fmtLargo = 16, tasa = 16000, bytesSeg = 32000, datos = bytes;
  uint16_t formato = 1, canales = 1, alinea = 2, bits = 16;
  memcpy(cab, "RIFF", 4); memcpy(cab + 4, &riff, 4); memcpy(cab + 8, "WAVEfmt ", 8); memcpy(cab + 16, &fmtLargo, 4);
  memcpy(cab + 20, &formato, 2); memcpy(cab + 22, &canales, 2); memcpy(cab + 24, &tasa, 4); memcpy(cab + 28, &bytesSeg, 4);
  memcpy(cab + 32, &alinea, 2); memcpy(cab + 34, &bits, 2); memcpy(cab + 36, "data", 4); memcpy(cab + 40, &datos, 4);
  servidor.setContentLength(44 + bytes);
  servidor.send(200, "audio/wav", "");
  servidor.sendContent((const char*)cab, 44);
  servidor.sendContent((const char*)pcm, bytes);
  free(pcm);
}
#endif

void iniciarWifi() {
  redesCargar();
  if (!redesHay()) { Serial.println("Wi-Fi: no hay redes guardadas. Usa 'wifi agregar NOMBRE|CLAVE' por cable. Funciona solo por Serial."); return; }
  WiFi.persistent(false);        // nuestra lista en NVS es la única fuente: el driver no guarda la suya
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(NOMBRE_ROBOT);
  WiFi.setAutoReconnect(true);
  WiFi.onEvent(estEventoWifi);   // guarda el motivo si no conecta (red no encontrada, clave incorrecta...)
  redesIntentar(0, false);
}

void revisarWifi(uint32_t ahora) {
  if (!redesHay() || servidorIniciado || ahora - ultimoRevisoWifi < 500) return;
  ultimoRevisoWifi = ahora;
  if (WiFi.status() != WL_CONNECTED) return;
  MDNS.begin(NOMBRE_ROBOT);
  const char* cabeceras[] = {"x-token"};
  servidor.collectHeaders(cabeceras, 1);
  servidor.on("/cmd", HTTP_POST, rutaComando);
  servidor.on("/estado", HTTP_GET, rutaEstado);
#if MIC_AUDIO_HTTP
  servidor.on("/mic/audio", HTTP_GET, rutaMicAudio);
#endif
  servidor.begin();
  servidorIniciado = true;
  estIniciarOta();
  mostrarWifi();
}

void leerSerial() {
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r') continue;
    if (ch == '\n') {
      linea[largoLinea] = 0;
      // Los comandos "wifi ..." (claves de red) solo valen por cable: no pasan por procesarLinea, que también atiende /cmd.
      if (strncasecmp(linea, "wifi ", 5) == 0) redesComando(linea + 5);
      else if (strncasecmp(linea, "servidor", 8) == 0 && (linea[8] == 0 || linea[8] == ' ' || linea[8] == '\r')) cfgComando(false, linea + 8);
      else if (strncasecmp(linea, "token ", 6) == 0) cfgComando(true, linea + 6);
      else procesarLinea(linea);
      largoLinea = 0;
    }
    else if (largoLinea < sizeof(linea) - 1) linea[largoLinea++] = ch;
  }
}

// ---------- Voz por toque (la tarea está en voz.h; solo loop() toca la pantalla y el servo) ----------

const char* CARA_PENSANDO = "pensando";   // mientras el PC procesa
const char* CARA_HABLANDO = "feliz";      // si la respuesta es "neutral", sonríe mientras habla
const char* CARA_REPOSO = "neutral";      // al terminar

void atenderVoz() {
  static uint8_t anterior = VOZ_REPOSO;
  uint8_t ahora = vozEstado;
  if (ahora == anterior) return;
  uint8_t antes = anterior;
  anterior = ahora;

  if (ahora == VOZ_ESCUCHANDO) {
    modoDemo = false;
  } else if (ahora == VOZ_PENSANDO) {
    modoDemo = false;
    ponerEmocion(buscarEmocion(CARA_PENSANDO));
  } else if (ahora == VOZ_HABLANDO) {
    modoDemo = false;
    const char* nombre = (strcasecmp(vozEmocion, "neutral") == 0) ? CARA_HABLANDO : vozEmocion;
    int i = buscarEmocion(nombre);
    ponerEmocion(i >= 0 ? i : buscarEmocion(CARA_HABLANDO));
    int cuello = vozCuello;
    if (cuello >= 0) moverCabeza(cuello);
  } else if (ahora == VOZ_ESPERANDO) {
    modoDemo = false;
    ponerEmocion(buscarEmocion("sorprendido"));   // "te escucho" unos segundos
  } else if (antes == VOZ_PENSANDO || antes == VOZ_HABLANDO || antes == VOZ_ESPERANDO) {
    ponerEmocion(buscarEmocion(CARA_REPOSO));
    estAvisoFalloVoz();   // si la conversación falló por la red, lo dice en pantalla
  }
}

// ---------- Arduino ----------

void setup() {
  Serial.begin(115200);
  delay(300);
  randomSeed(esp_random());

  Wire.begin(PIN_SDA, PIN_SCL);
  if (!pantalla.begin(SSD1306_SWITCHCAPVCC, 0x3C) && !pantalla.begin(SSD1306_SWITCHCAPVCC, 0x3D)) {
    Serial.println("No encuentro la pantalla. Revisa VCC, GND, SDA (8) y SCL (9).");
  }

  pantalla.cp437(true);   // para que el símbolo ° se vea bien
  estSplash();            // nombre, versión y por qué se reinició
  estArranque("Servo", 25);
  cuello.attach(PIN_SERVO);
  if (!cuello.listo) Serial.println("Aviso: no pude iniciar el PWM del servo (GPIO13).");
  cuello.write(anguloActual);

  actual = caraDe(EMOCIONES[0]);
  hacia = actual;
  strncpy(nombreActual, EMOCIONES[0].nombre, sizeof(nombreActual) - 1);   // para que /estado diga "neutral" desde el arranque
  proximoParpadeo = millis() + 2000;

  cfgCargar();                                   // servidor y token (NVS o valores de compilación)
  // ---- Wi-Fi: gesto de arranque, portal cautivo o conexión normal ----
  int gesto = portalGestoArranque();             // mantener el toque 4 s = portal; 10 s = borrar las redes
  if (gesto == 2) redesBorrarTodoNVS();
  bool abrirPortal = gesto > 0 || redesLeerMarcaPortal();
  char motivoPortal[72] = "";
  redesCargar();
  if (!abrirPortal && !redesHay()) abrirPortal = true;   // robot nuevo o sin redes: no hay nada que probar
  estArranque("Wi-Fi", 45);
  if (!abrirPortal) {
    iniciarWifi();
    estEsperarWifi(redes.hayCandidata ? 25000 : 8000);   // muestra "conectando", "no veo la red" o "clave incorrecta"; 8 s (25 s si es una red nueva)
    char falla[REDES_SSID_MAX + 1];
    snprintf(falla, sizeof(falla), "%s", redes.hayCandidata ? redes.candidata.ssid : "");
    const char* porque = estTextoMotivoWifi(wifiMotivo);
    if (redesResolverCandidata(WiFi.status() == WL_CONNECTED) < 0) {   // la candidata no conectó: se descarta y se vuelve al portal
      snprintf(motivoPortal, sizeof(motivoPortal), "No pude conectar a \"%s\": %s. Intenta de nuevo.", falla, porque);
      abrirPortal = true;
    }
  }
  if (abrirPortal) {
    portalAbrir(motivoPortal);                   // solo vuelve si vence el tiempo (guardar una red reinicia la placa)
    if (redesHay()) { iniciarWifi(); estEsperarWifi(8000); }
  }
  revisarWifi(millis());       // si ya hay red, arranca el servidor y la OTA antes de iniciar la voz
  estArranque("Voz y sonido", 80);
  iniciarVoz();
  estArranque("Listo", 100);
  estListo();
  actIniciar();                // consulta periódica de versiones nuevas en el servidor
  agendaIniciar();             // consulta periódica de avisos (agenda.h); en modo prueba no suena
  Serial.println("Robot listo. Escribe el nombre de una emoción, 'cabeza 120', 'demo', 'agenda' o 'lista'.");
  mostrarLista();
}

void loop() {
  uint32_t ahora = millis();
#ifdef PRUEBA_ROLLBACK
  // Solo para probar el rollback: compilar con -DPRUEBA_ROLLBACK. Se cuelga a los 20 s, antes de que el firmware se dé por bueno (45 s).
  static bool avisoRollback = false;
  if (!avisoRollback) { avisoRollback = true; Serial.println("PRUEBA ROLLBACK: este firmware se cuelga a los 20 s a proposito."); }
  if (ahora > 20000) abort();
#endif
  if (otaIniciado) ArduinoOTA.handle();   // si llega una actualización, esta llamada no vuelve hasta terminar
  leerSerial();
  revisarWifi(ahora);
  estRevisarWifi(ahora);
  actAtender(ahora);
  if (servidorIniciado) servidor.handleClient();
  avanzarServo(ahora);
  atenderVoz();
  agendaAtender(ahora);

  if (modoDemo && ahora >= proximoDemo) {
    ponerEmocion((emocionActual + 1) % NUM_EMOCIONES);
    moverCabeza(random(50, 131));
    proximoDemo = ahora + 2500;
  }

  if (ahora - ultimoCuadro >= 33) {  // ~30 cuadros por segundo
    ultimoCuadro = ahora;
    avanzarTransicion(ahora);
    if (actPantallaActiva()) actDibujar(ahora);   // cuenta regresiva o instalación: ocupan toda la pantalla
    else if (hayTexto && (int32_t)(textoHasta - ahora) > 0) dibujarTexto();
    else { hayTexto = false; dibujarCara(actual, ahora, aperturaOjos(ahora)); }
  }
}
