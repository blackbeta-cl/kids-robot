/*
  portal.h — portal cautivo para configurar el Wi-Fi del robot (W2).
  Se incluye desde robot_rostro.ino DESPUÉS de estado.h y redes.h (usa `pantalla`, estCentrado, estIconoWifi, redes...).

  Cuándo se abre (lo decide setup()):
    - el robot no tiene ninguna red guardada (nuevo o borrada),
    - la red que acaba de escribir un padre ("candidata") no conectó,
    - gesto al encender (mantener el toque 4 s) o comando por cable `wifi portal`.
  Qué hace: crea la red "Robot-XXXX" (WPA2, clave aleatoria nueva en cada apertura, visible en la OLED), un DNS que
  lo redirige todo a 192.168.4.1 y una página donde se elige la red y se escribe la clave. Al guardar, la red queda como
  "candidata" en NVS y el robot REINICIA para probarla (si falla, vuelve aquí). A los 10 minutos sin guardar se cierra.
  Mientras el portal está abierto no corren la voz, la OTA ni /cmd: setup() está bloqueado aquí.
*/
#pragma once

#include <DNSServer.h>
#include <WebServer.h>
#include "portal_pagina.h"

#ifndef PORTAL_MAX_MS
#define PORTAL_MAX_MS 600000UL        // 10 minutos abierto como máximo
#endif
#ifndef PORTAL_VENTANA_MS
#define PORTAL_VENTANA_MS 1200UL      // tras la pantalla de arranque, ventana en la que un toque inicia el gesto
#endif
#define PORTAL_GESTO_PORTAL_MS 4000UL // mantener 4 s: configurar el Wi-Fi
#define PORTAL_GESTO_BORRAR_MS 10000UL // mantener 10 s: borrar todas las redes
#define PORTAL_CONFIRMAR_MS 5000UL    // tiempo para confirmar el borrado con un toque
#define PORTAL_MAX_REDES 20

struct PortalRed { char ssid[REDES_SSID_MAX + 1]; int8_t rssi; bool abierta; };

// ---------- Gesto de arranque ----------

static bool portalTocando() { return digitalRead(VOZ_PIN_TACTO) != 0; }

static void portalPantallaGesto(uint32_t ms) {
  estInicioTexto();
  if (ms < PORTAL_GESTO_PORTAL_MS) {
    estCentrado("Sigue tocando...", 1, 6);
    estCentrado("para configurar Wi-Fi", 1, 20);
    pantalla.drawRect(8, 44, 112, 8, BLANCO);
    pantalla.fillRect(10, 46, (int)(ms * 108UL / PORTAL_GESTO_PORTAL_MS), 4, BLANCO);
  } else {
    estCentrado("Suelta: configurar Wi-Fi", 1, 6);
    estCentrado("Sigue: borrar redes", 1, 20);
    uint32_t extra = ms - PORTAL_GESTO_PORTAL_MS, total = PORTAL_GESTO_BORRAR_MS - PORTAL_GESTO_PORTAL_MS;
    pantalla.drawRect(8, 44, 112, 8, BLANCO);
    pantalla.fillRect(10, 46, (int)(min(extra, total) * 108UL / total), 4, BLANCO);
  }
  pantalla.display();
}

// Pide confirmar el borrado: un toque en 5 s = sí; sin toque = no (se abre el portal sin borrar).
static bool portalConfirmarBorrado() {
  delay(400);                                   // que el rebote de soltar no cuente como confirmación
  uint32_t t0 = millis(), ultima = 0;
  while (millis() - t0 < PORTAL_CONFIRMAR_MS) {
    if (portalTocando()) {
      while (portalTocando()) delay(20);
      estInicioTexto();
      estCentrado("Redes borradas", 1, 28);
      pantalla.display();
      Serial.println("Gesto: borrado confirmado.");
      delay(800);
      return true;
    }
    if (millis() - ultima > 200) {
      ultima = millis();
      estInicioTexto();
      estCentrado("Borrar las redes?", 1, 6);
      estCentrado("Toca 1 vez = SI", 1, 22);
      estCentrado("No toques = NO", 1, 34);
      char t[8];
      snprintf(t, sizeof(t), "%u", (unsigned)((PORTAL_CONFIRMAR_MS - (millis() - t0)) / 1000 + 1));
      estCentrado(t, 2, 46);
      pantalla.display();
    }
    delay(10);
  }
  Serial.println("Gesto: sin confirmacion, no se borra nada.");
  return false;
}

// Devuelve 0 = nada, 1 = abrir el portal, 2 = borrar todas las redes (y abrir el portal).
// El TTP223 se recalibra al encender: por eso se mira una ventana corta DESPUÉS de la pantalla de arranque en vez de
// exigir tenerlo tocado desde el primer instante. Soltar antes de 4 s cancela (un falso toque no hace nada).
int portalGestoArranque() {
  pinMode(VOZ_PIN_TACTO, INPUT);
  estArranque("Toca = ajustar Wi-Fi", 10);
  uint32_t t0 = millis();
  while (!portalTocando()) {
    if (millis() - t0 > PORTAL_VENTANA_MS) return 0;
    delay(10);
  }
  uint32_t inicio = millis(), ultimaPantalla = 0;
  while (portalTocando()) {
    uint32_t ms = millis() - inicio;
    if (ms >= PORTAL_GESTO_BORRAR_MS) {
      estInicioTexto();
      estCentrado("Suelta el toque", 1, 28);
      pantalla.display();
      while (portalTocando()) delay(20);
      Serial.println("Gesto: toque de 10 s. Pido confirmacion para borrar las redes.");
      return portalConfirmarBorrado() ? 2 : 1;
    }
    if (millis() - ultimaPantalla > 80) { ultimaPantalla = millis(); portalPantallaGesto(ms); }
    delay(10);
  }
  uint32_t dur = millis() - inicio;
  if (dur >= PORTAL_GESTO_PORTAL_MS) { Serial.printf("Gesto: toque de %u ms. Abro el portal.\n", (unsigned)dur); return 1; }
  Serial.printf("Gesto: toque de %u ms (menos de 4 s): ignorado.\n", (unsigned)dur);
  return 0;
}

// ---------- Estado del portal (solo existe mientras está abierto) ----------

static PortalRed portalLista[PORTAL_MAX_REDES];
static int portalN = 0;
static char portalToken[9];
static char portalMotivo[72];
static bool portalGuardado = false;
static uint32_t portalGuardadoEn = 0;

static uint32_t portalAzar() { return esp_random(); }

static void portalEscanear() {
  portalN = 0;
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true);
  delay(100);
  int n = WiFi.scanNetworks();                      // bloquea unos segundos; se hace ANTES de abrir el AP (con el AP abierto cortaría al móvil)
  for (int i = 0; i < n; i++) {
    String s = WiFi.SSID(i);
    if (!s.length() || s.length() > REDES_SSID_MAX) continue;       // oculta o rara: se escribe a mano
    int k = -1;
    for (int j = 0; j < portalN; j++) if (s == portalLista[j].ssid) { k = j; break; }
    int rssi = WiFi.RSSI(i);
    if (k >= 0) { if (rssi > portalLista[k].rssi) portalLista[k].rssi = rssi; continue; }   // misma red en varios puntos de acceso: la más fuerte
    if (portalN >= PORTAL_MAX_REDES) continue;
    snprintf(portalLista[portalN].ssid, sizeof(portalLista[portalN].ssid), "%s", s.c_str());
    portalLista[portalN].rssi = (int8_t)rssi;
    portalLista[portalN].abierta = WiFi.encryptionType(i) == WIFI_AUTH_OPEN;
    portalN++;
  }
  WiFi.scanDelete();
  for (int a = 1; a < portalN; a++) {                // ordenar por señal, de mayor a menor
    PortalRed x = portalLista[a];
    int b = a - 1;
    while (b >= 0 && portalLista[b].rssi < x.rssi) { portalLista[b + 1] = portalLista[b]; b--; }
    portalLista[b + 1] = x;
  }
  Serial.printf("Portal: %d redes visibles (2,4 GHz).\n", portalN);
}

// ---------- Pantallas ----------

static void portalPantallaAbierto(const char* nombre, const char* clave, uint32_t restanteMs, uint32_t inicioMs) {
  estInicioTexto();
  estCentrado("CONFIGURA MI WI-FI", 1, 0);
  pantalla.setTextSize(1);
  pantalla.setCursor(0, 12);  pantalla.printf("Red:   %s", nombre);
  pantalla.setCursor(0, 22);  pantalla.printf("Clave: %s", clave);
  if (WiFi.softAPgetStationNum() > 0) {
    // Samsung/Android a veces no abre la página solo: alternar la pista cada 4 s
    if (((millis() - inicioMs) / 4000) % 2 == 0) {
      estCentrado("Abre 192.168.4.1", 1, 36);
      estCentrado("si no se abre sola", 1, 46);
    } else {
      estCentrado("Sin internet? Toca", 1, 36);
      estCentrado("Administrar router", 1, 46);
    }
  } else {
    estCentrado("Conectate a esa red", 1, 36);
    estCentrado("desde tu celular", 1, 46);
  }
  char t[24];
  uint32_t s = restanteMs / 1000;
  snprintf(t, sizeof(t), "cierra en %u:%02u", (unsigned)(s / 60), (unsigned)(s % 60));
  estCentrado(t, 1, 56);
  pantalla.display();
}

static void portalPantallaMensaje(const char* a, const char* b, const char* c, int ms) {
  estInicioTexto();
  estIconoWifi(64, 18, 2, 3, true);
  estCentrado(a, 1, 30);
  if (b && b[0]) estCentrado(b, 1, 42);
  if (c && c[0]) estCentrado(c, 1, 54);
  pantalla.display();
  delay(ms);
}

// ---------- Páginas ----------

static void portalNoCache(WebServer& w) {
  w.sendHeader("Cache-Control", "no-store");
  w.sendHeader("X-Content-Type-Options", "nosniff");
}

static void portalJson(WebServer& w, int codigo, bool ok, const char* error) {
  JsonDocument d;
  d["ok"] = ok;
  if (error) d["error"] = error;
  String s;
  serializeJson(d, s);
  portalNoCache(w);
  w.send(codigo, "application/json", s);
}

static bool portalTokenOk(WebServer& w) {
  String t = w.arg("t");
  return t.length() == strlen(portalToken) && t == portalToken;
}

static void portalRutaPagina(WebServer& w) {
  String h = FPSTR(PORTAL_HTML);
  h.replace("__TOKEN__", portalToken);
  portalNoCache(w);
  w.send(200, "text/html; charset=utf-8", h);
}

static void portalRutaRedes(WebServer& w) {
  if (!portalTokenOk(w)) { portalJson(w, 403, false, "Token invalido"); return; }
  JsonDocument d;
  JsonArray rs = d["redes"].to<JsonArray>();
  for (int i = 0; i < portalN; i++) {
    JsonObject o = rs.add<JsonObject>();
    o["s"] = portalLista[i].ssid;
    o["r"] = portalLista[i].rssi;
    o["a"] = portalLista[i].abierta;
  }
  JsonArray gs = d["guardadas"].to<JsonArray>();
  for (int i = 0; i < redes.n && !redesRespaldoActivo; i++) gs.add(redes.red[i].ssid);   // solo nombres, nunca claves
  if (portalMotivo[0]) d["motivo"] = portalMotivo;
  String s;
  serializeJson(d, s);
  portalNoCache(w);
  w.send(200, "application/json", s);
}

static void portalRutaGuardar(WebServer& w) {
  if (!portalTokenOk(w)) { portalJson(w, 403, false, "Token invalido"); return; }
  String ssid = w.arg("ssid"), clave = w.arg("clave");
  RedesError e = redesGuardarCandidata(ssid.c_str(), clave.c_str());
  if (e != REDES_OK) { portalJson(w, 200, false, redesTextoError(e)); return; }
  Serial.printf("Portal: red '%s' guardada como candidata. Reinicio para probarla.\n", ssid.c_str());   // sin clave
  portalJson(w, 200, true, nullptr);
  portalGuardado = true;
  portalGuardadoEn = millis();
}

static void portalRutaOlvidar(WebServer& w) {
  if (!portalTokenOk(w)) { portalJson(w, 403, false, "Token invalido"); return; }
  String ssid = w.arg("ssid");
  if (!redesOlvidarGuardada(ssid.c_str())) { portalJson(w, 200, false, "No tengo esa red"); return; }
  Serial.printf("Portal: red '%s' olvidada.\n", ssid.c_str());
  portalJson(w, 200, true, nullptr);
}

// Abre el portal y se queda aquí. Reinicia la placa al guardar una red; si vence el tiempo, cierra y devuelve false
// (setup() sigue con las redes que haya). `motivo` (puede ser "") se muestra arriba en la página.
bool portalAbrir(const char* motivo) {
  snprintf(portalMotivo, sizeof(portalMotivo), "%s", motivo ? motivo : "");
  portalGuardado = false;
  snprintf(portalToken, sizeof(portalToken), "%08x", (unsigned)esp_random());

  portalPantallaMensaje("Buscando redes...", "", "", 50);
  portalEscanear();

  char nombre[24], clave[9];
  uint8_t mac[6];
  WiFi.macAddress(mac);
  redesNombreAp(nombre, sizeof(nombre), mac[4], mac[5]);
  redesGenerarClave(clave, sizeof(clave), portalAzar);

  WiFi.mode(WIFI_AP);
  WiFi.softAPsetHostname(NOMBRE_ROBOT);
  if (!WiFi.softAP(nombre, clave, 1, 0, 2)) {
    Serial.println("Portal: no pude crear la red del robot.");
    portalPantallaMensaje("No pude abrir", "el portal", "", 3000);
    return false;
  }
  IPAddress ip = WiFi.softAPIP();
  Serial.printf("Portal: abierto. Red '%s' (la clave está en la pantalla), página en http://%s/\n", nombre, ip.toString().c_str());

  DNSServer dns;
  dns.setErrorReplyCode(DNSReplyCode::NoError);
  dns.start(53, "*", ip);

  WebServer web(80);
  web.on("/", HTTP_GET, [&web]() { portalRutaPagina(web); });
  web.on("/redes", HTTP_GET, [&web]() { portalRutaRedes(web); });
  web.on("/guardar", HTTP_POST, [&web]() { portalRutaGuardar(web); });
  web.on("/olvidar", HTTP_POST, [&web]() { portalRutaOlvidar(web); });
  String destino = String("http://") + ip.toString() + "/";
  web.onNotFound([&web, destino]() {                 // /generate_204, /hotspot-detect.html, /connecttest.txt...: manda al portal
    web.sendHeader("Location", destino, true);
    portalNoCache(web);
    web.send(302, "text/plain", "");
  });
  web.begin();

  uint32_t t0 = millis(), ultima = 0;
  while (true) {
    uint32_t ahora = millis();
    dns.processNextRequest();
    web.handleClient();
    if (portalGuardado && ahora - portalGuardadoEn > 1500) {
      portalPantallaMensaje("Red guardada", "Reiniciando...", "", 800);
      ESP.restart();
    }
    if (ahora - t0 > PORTAL_MAX_MS) break;
    if (ahora - ultima > 500) { ultima = ahora; portalPantallaAbierto(nombre, clave, PORTAL_MAX_MS - (ahora - t0), t0); }
    delay(2);
  }
  web.stop();
  dns.stop();
  WiFi.softAPdisconnect(true);
  WiFi.mode(WIFI_OFF);
  Serial.println("Portal: tiempo cumplido, cerrado.");
  portalPantallaMensaje("Portal cerrado", "Toca al encender", "para configurar", 2500);
  return false;
}
