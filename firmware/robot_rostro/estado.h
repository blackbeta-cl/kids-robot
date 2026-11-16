/*
  estado.h — feedback en la pantalla: arranque, Wi-Fi y actualización por Wi-Fi (OTA).
  Se incluye desde robot_rostro.ino DESPUÉS de las variables globales (usa `pantalla`, `textoGrande`...).
  Solo loop() y setup() dibujan; los callbacks de ArduinoOTA corren dentro de ArduinoOTA.handle(), que se llama desde loop().

  Qué muestra:
    - Arranque: nombre, versión y por qué se reinició (encendido, botón RST, error, poca energía, actualización),
      luego pasos con barra, el Wi-Fi (conectando / conectado / "no veo la red" / "clave incorrecta") y "Listo!".
    - En uso normal: un icono pequeño de Wi-Fi tachado arriba a la derecha mientras no haya red;
      al volver la red, el icono sin tachar unos segundos.
    - Si hablas y falla algo (sin Wi-Fi, sin hora, sin servidor): un aviso de 4 s en vez de silencio.
    - OTA: "Actualizando... no me apagues" con barra y %, "Actualización lista" o el motivo del fallo.
*/
#pragma once

#include <ArduinoOTA.h>
#include <Preferences.h>
#include <esp_system.h>

#define FIRMWARE_VERSION "1.1.0"   // súbela a mano con cada cambio: se ve en el arranque y en /estado

#ifndef OTA_CLAVE
#define OTA_CLAVE ""               // se define en wifi_config.h; sin clave, la OTA queda apagada
#endif

volatile uint8_t wifiMotivo = 0;   // último motivo de desconexión (códigos de ESP-IDF), 0 = ninguno
bool wifiOk = false;
uint32_t wifiCaidoDesde = 0, wifiRecienHasta = 0, wifiUltimoReintento = 0;
bool otaIniciado = false;
volatile bool otaEnCurso = false;

// ---------- Utilidades de dibujo ----------

void estInicioTexto() {
  pantalla.clearDisplay();
  pantalla.setTextColor(BLANCO);
  pantalla.setTextWrap(false);
}

void estCentrado(const char* t, int tam, int y) {
  int w = (int)strlen(t) * 6 * tam;
  pantalla.setTextSize(tam);
  pantalla.setCursor(max(0, (ANCHO - w) / 2), y);
  pantalla.print(t);
}

// Icono de Wi-Fi: punto y hasta 3 arcos hacia arriba. `tacha` dibuja una raya diagonal (sin red).
void estIconoWifi(int cx, int cy, int e, int nivel, bool tacha) {
  pantalla.fillCircle(cx, cy, e > 1 ? 2 : 1, BLANCO);
  for (int k = 1; k <= nivel && k <= 3; k++) {
    int r = 3 * k * e;
    pantalla.drawCircleHelper(cx, cy, r, 0x3, BLANCO);
    if (e > 1) pantalla.drawCircleHelper(cx, cy, r + 1, 0x3, BLANCO);
  }
  if (tacha) {
    int a = 9 * e;
    pantalla.drawLine(cx - a + 1, cy - a, cx + a + 1, cy + 2 * e, NEGRO);
    pantalla.drawLine(cx - a - 1, cy - a, cx + a - 1, cy + 2 * e, NEGRO);
    pantalla.drawLine(cx - a, cy - a, cx + a, cy + 2 * e, BLANCO);
  }
}

// ---------- Texto temporal (reusa la pantalla de texto de la hora o la temperatura) ----------

void estAviso(const char* grande, const char* medio, const char* chico, int seg) {
  snprintf(textoGrande, sizeof(textoGrande), "%s", grande);
  snprintf(textoMedio, sizeof(textoMedio), "%s", medio);
  snprintf(textoChico, sizeof(textoChico), "%s", chico);
  hayTexto = true;
  textoHasta = millis() + (uint32_t)seg * 1000;
}

// ---------- Arranque ----------

const char* estMotivoReinicio() {
  switch (esp_reset_reason()) {
    case ESP_RST_POWERON: return "Encendido";
    case ESP_RST_EXT: return "Boton RST";
    case ESP_RST_SW: return "Reinicio";
    case ESP_RST_PANIC: return "Reinicio por error";
    case ESP_RST_INT_WDT: case ESP_RST_TASK_WDT: case ESP_RST_WDT: return "Error: watchdog";
    case ESP_RST_BROWNOUT: return "Poca energia!";
    default: return "Arranque";
  }
}

const char* estTextoMotivoWifi(uint8_t m) {
  switch (m) {
    case 201: return "No veo la red";
    case 202: case 15: case 204: return "Clave incorrecta";
    case 0: return "Sin respuesta";
    default: return "Sin conexion";
  }
}

void estEventoWifi(arduino_event_id_t ev, arduino_event_info_t info) {
  if (ev == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) wifiMotivo = info.wifi_sta_disconnected.reason;
  else if (ev == ARDUINO_EVENT_WIFI_STA_GOT_IP) wifiMotivo = 0;
}

void estArranque(const char* paso, int pct) {
  estInicioTexto();
  estCentrado("KIDS ROBOT", 2, 4);
  char v[16];
  snprintf(v, sizeof(v), "v%s", FIRMWARE_VERSION);
  estCentrado(v, 1, 24);
  estCentrado(paso, 1, 38);
  pantalla.drawRect(14, 51, 100, 7, BLANCO);
  pantalla.fillRect(16, 53, constrain(pct, 0, 100) * 96 / 100, 3, BLANCO);
  pantalla.display();
}

// Pantalla inicial: nombre, versión y motivo del reinicio. Si venimos de una OTA, lo dice.
void estSplash() {
  char linea[32];
  snprintf(linea, sizeof(linea), "%s", estMotivoReinicio());
  Preferences p;
  if (p.begin("robot", false)) {
    String previa = p.getString("prev", "");
    if (previa.length()) {
      p.remove("prev");
      if (previa != FIRMWARE_VERSION) snprintf(linea, sizeof(linea), "Actualizado a v%s", FIRMWARE_VERSION);
    }
    p.end();
  }
  Serial.printf("Arranque: %s (firmware v%s)\n", linea, FIRMWARE_VERSION);
  estArranque(linea, 8);
  delay(1500);
}

// Espera el Wi-Fi mostrando una animación; al final dice cómo quedó. No bloquea más de maxMs.
void estEsperarWifi(uint32_t maxMs) {
  if (!redesHay()) return;
  char red[22];
  snprintf(red, sizeof(red), "%s", redesNombreActual());
  uint32_t t0 = millis(), tRed = t0;
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < maxMs) {
    if (redesCantidadAIntentar(redes) > 1 && millis() - tRed > 4000) {   // con varias redes, prueba la siguiente cada 4 s
      redesRotar();
      tRed = millis();
      snprintf(red, sizeof(red), "%s", redesNombreActual());
    }
    estInicioTexto();
    estIconoWifi(64, 26, 2, (int)(((millis() - t0) / 250) % 4), false);
    estCentrado("Conectando Wi-Fi", 1, 38);
    estCentrado(wifiMotivo ? estTextoMotivoWifi(wifiMotivo) : red, 1, 52);
    pantalla.display();
    delay(60);
  }
  estInicioTexto();
  if (WiFi.status() == WL_CONNECTED) {
    estIconoWifi(64, 26, 2, 3, false);
    estCentrado("Wi-Fi conectado", 1, 38);
    estCentrado(red, 1, 52);
    pantalla.display();
    delay(700);
  } else {
    estIconoWifi(64, 26, 2, 3, true);
    estCentrado("Sin Wi-Fi", 1, 38);
    estCentrado(estTextoMotivoWifi(wifiMotivo), 1, 52);
    pantalla.display();
    Serial.printf("Wi-Fi: sin conexión tras %lu ms (%s, código %u). Sigo intentando en segundo plano.\n",
                  (unsigned long)(millis() - t0), estTextoMotivoWifi(wifiMotivo), (unsigned)wifiMotivo);
    delay(2000);
  }
}

void estListo() {
  wifiOk = WiFi.status() == WL_CONNECTED;     // desde aquí, loop() vigila los cambios
  wifiCaidoDesde = millis();
  wifiRecienHasta = 0;
  estInicioTexto();
  estCentrado("Listo!", 2, 4);
  char ip[24];
  if (wifiOk) snprintf(ip, sizeof(ip), "%s", WiFi.localIP().toString().c_str());
  else snprintf(ip, sizeof(ip), "Sin Wi-Fi");
  estCentrado(ip, 1, 28);
  const char* ota = otaIniciado ? "OTA lista" : (!OTA_CLAVE[0] ? "OTA sin clave" : "OTA: esperando Wi-Fi");
  estCentrado(ota, 1, 40);
  char v[16];
  snprintf(v, sizeof(v), "v%s", FIRMWARE_VERSION);
  estCentrado(v, 1, 52);
  pantalla.display();
  delay(1800);
}

// ---------- Wi-Fi en uso normal ----------

// Se llama en cada vuelta de loop(): detecta caídas y vueltas, y reintenta a mano si la red no vuelve.
void estRevisarWifi(uint32_t ahora) {
  if (!redesHay()) return;
  bool ok = WiFi.status() == WL_CONNECTED;
  if (ok && !wifiOk) {
    wifiOk = true;
    wifiRecienHasta = ahora + 2500;
    Serial.printf("Wi-Fi: de vuelta (IP %s)\n", WiFi.localIP().toString().c_str());
  } else if (!ok && wifiOk) {
    wifiOk = false;
    wifiCaidoDesde = ahora;
    Serial.printf("Wi-Fi: se cayó (%s, código %u)\n", estTextoMotivoWifi(wifiMotivo), (unsigned)wifiMotivo);
  }
  if (!ok && ahora - wifiCaidoDesde > 15000 && ahora - wifiUltimoReintento > 20000) {
    wifiUltimoReintento = ahora;
    Serial.println("Wi-Fi: reintento a mano.");
    redesRotar();   // con varias redes guardadas prueba la siguiente; con una sola repite la misma
  }
}

// Se llama al final de dibujarCara(), antes de pantalla.display().
void estSuperposicion(uint32_t ahora) {
  if (!redesHay() || otaEnCurso) return;
  if (!wifiOk) {
    if (ahora - wifiCaidoDesde > 4000 && (ahora / 800) % 4 != 0) estIconoWifi(118, 11, 1, 3, true);   // parpadea despacio
  } else if ((int32_t)(wifiRecienHasta - ahora) > 0) {
    estIconoWifi(118, 11, 1, 3, false);
  }
}

// Aviso cuando una conversación falló por la red (vozFallo lo fija voz.h). Devuelve true si mostró algo.
bool estAvisoFalloVoz() {
  uint8_t f = vozFallo;
  if (!f) return false;
  vozFallo = 0;
  if (f == VOZ_FALLO_WIFI) estAviso("Sin Wi-Fi", "", estTextoMotivoWifi(wifiMotivo), 4);
  else if (f == VOZ_FALLO_HORA) estAviso("Sin hora", "", "No pude fijar la hora", 4);
  else estAviso("Sin servidor", "", "No llego al servidor", 4);
  return true;
}

// ---------- OTA ----------

void estPantallaOta(const char* titulo, int pct, const char* pie) {
  estInicioTexto();
  estCentrado(titulo, 1, 4);
  if (pct >= 0) {
    char n[8];
    snprintf(n, sizeof(n), "%d%%", pct);
    estCentrado(n, 3, 20);
    pantalla.drawRect(8, 50, 112, 8, BLANCO);
    pantalla.fillRect(10, 52, constrain(pct, 0, 100) * 108 / 100, 4, BLANCO);
  }
  if (pie && pie[0]) estCentrado(pie, 1, pct >= 0 ? 42 : 30);
  pantalla.display();
}

void estIniciarOta() {
  if (otaIniciado || WiFi.status() != WL_CONNECTED) return;
  if (!OTA_CLAVE[0]) { Serial.println("OTA: apagada (falta OTA_CLAVE en wifi_config.h)."); return; }

  ArduinoOTA.setHostname(NOMBRE_ROBOT);
  ArduinoOTA.setPassword(OTA_CLAVE);
  ArduinoOTA.setMdnsEnabled(false);          // revisarWifi() ya inicia mDNS; la subida va por IP
  ArduinoOTA.onStart([]() {
    otaEnCurso = true;
    vozPausada = true;                       // la voz no compite por CPU ni memoria mientras se actualiza
    modoDemo = false;
    hayTexto = false;
    Serial.println("OTA: empieza la actualización.");
    anuncioOta();                            // beeps + "Actualizando en tres, dos, uno"
    estPantallaOta("Actualizando...", 0, "No me apagues");
  });
  ArduinoOTA.onProgress([](unsigned int hecho, unsigned int total) {
    static int ultimo = -1;
    int pct = total ? (int)((uint64_t)hecho * 100 / total) : 0;
    if (pct == ultimo) return;               // un cuadro por cada %: no satura el I2C
    ultimo = pct;
    estPantallaOta("Actualizando...", pct, "No me apagues");
  });
  ArduinoOTA.onEnd([]() {
    Preferences p;
    if (p.begin("robot", false)) { p.putString("prev", FIRMWARE_VERSION); p.end(); }   // el arranque siguiente dirá "Actualizado a vX"
    Serial.println("OTA: lista, reiniciando.");
    estPantallaOta("Actualizacion lista", -1, "Reiniciando...");
    delay(1500);
  });
  ArduinoOTA.onError([](ota_error_t e) {
    const char* motivo = e == OTA_AUTH_ERROR ? "Clave incorrecta" : e == OTA_BEGIN_ERROR ? "No pude empezar" :
                         e == OTA_CONNECT_ERROR ? "Fallo la conexion" : e == OTA_RECEIVE_ERROR ? "Se corto la subida" :
                         e == OTA_END_ERROR ? "Archivo invalido" : "Error";
    Serial.printf("OTA: falló (%s, código %u). Sigo con el firmware de antes.\n", motivo, (unsigned)e);
    otaEnCurso = false;
    vozPausada = false;
    estAviso("Fallo OTA", "", motivo, 5);
  });
  ArduinoOTA.begin();
  otaIniciado = true;
  Serial.printf("OTA: lista en %s (puerto 3232, con clave).\n", WiFi.localIP().toString().c_str());
}
