/*
  redes.h — redes Wi-Fi guardadas en NVS (namespace "wifi"), sin depender de la pantalla.
  La lógica (lista, candidata, validación) está en redes_logica.h y se prueba en el PC.

  Orden de uso:
    1. Si hay una candidata (la que acaba de escribir un padre), solo se prueba esa en el arranque.
    2. Si no, las confirmadas, la usada más recientemente primero; si una no conecta se rota a la siguiente.
    3. Respaldo de desarrollo: si NVS no tiene NINGUNA red, se usa la de wifi_config.h (solo en memoria, no se guarda).
  Las claves nunca se imprimen.
*/
#pragma once

#include <Preferences.h>
#include <WiFi.h>
#include "redes_logica.h"

ListaRedes redes;
int redesIdx = 0;                    // red que se está probando ahora (índice entre las "a intentar")
bool redesRespaldoActivo = false;    // true si la lista contiene solo la de wifi_config.h (no está en NVS)

// ---------- NVS ----------

static void redesClaves(char* ks, char* kp, int i) {
  snprintf(ks, 4, "s%d", i);
  snprintf(kp, 4, "p%d", i);
}

void redesGuardar() {
  if (redesRespaldoActivo) return;   // el respaldo de wifi_config.h nunca se escribe en NVS
  Preferences p;
  if (!p.begin("wifi", false)) { Serial.println("Wi-Fi: no pude abrir la NVS para guardar."); return; }
  p.putUChar("n", redes.n);
  for (int i = 0; i < REDES_MAX; i++) {
    char ks[4], kp[4];
    redesClaves(ks, kp, i);
    if (i < redes.n) { p.putString(ks, redes.red[i].ssid); p.putString(kp, redes.red[i].clave); }
    else { p.remove(ks); p.remove(kp); }
  }
  if (redes.hayCandidata) { p.putString("cs", redes.candidata.ssid); p.putString("cp", redes.candidata.clave); }
  else { p.remove("cs"); p.remove("cp"); }
  p.end();
}

void redesCargar() {
  redesLimpiar(redes);
  redesRespaldoActivo = false;
  Preferences p;
  if (p.begin("wifi", true)) {
    uint8_t n = p.getUChar("n", 0);
    if (n > REDES_MAX) n = REDES_MAX;
    for (int i = 0; i < n; i++) {
      char ks[4], kp[4];
      redesClaves(ks, kp, i);
      String s = p.getString(ks, "");
      String c = p.getString(kp, "");
      if (redesValidar(s.c_str(), c.c_str()) == REDES_OK) redesCopiar(redes.red[redes.n++], s.c_str(), c.c_str());
    }
    String cs = p.getString("cs", "");
    if (cs.length()) {
      String cp = p.getString("cp", "");
      if (redesValidar(cs.c_str(), cp.c_str()) == REDES_OK) { redesCopiar(redes.candidata, cs.c_str(), cp.c_str()); redes.hayCandidata = true; }
    }
    p.end();
  }
  if (redes.n == 0 && !redes.hayCandidata && WIFI_SSID[0] && redesValidar(WIFI_SSID, WIFI_CLAVE) == REDES_OK) {
    redesCopiar(redes.red[0], WIFI_SSID, WIFI_CLAVE);
    redes.n = 1;
    redesRespaldoActivo = true;
  }
}

// Hay alguna red que probar (guardada, candidata o el respaldo de wifi_config.h).
bool redesHay() { return redes.n > 0 || redes.hayCandidata; }
// Hay redes realmente guardadas en NVS (sin contar el respaldo). W2 usa esto para decidir si abre el portal.
bool redesHayGuardadas() { return !redesRespaldoActivo && redesHay(); }

// Antes de cambiar la lista: si solo estaba el respaldo, se quita para que no se mezcle con las guardadas de verdad.
static void redesSoltarRespaldo() {
  if (redesRespaldoActivo) { redesLimpiar(redes); redesRespaldoActivo = false; }
}

// ---------- Conexión ----------

const RedGuardada* redesActual() { return redesAIntentar(redes, redesIdx); }

const char* redesNombreActual() {
  const RedGuardada* r = redesActual();
  return r ? r->ssid : "";
}

// Empieza a conectar con la red número `i` (de las que hay que intentar). No bloquea.
void redesIntentar(int i, bool cortarAntes) {
  const RedGuardada* r = redesAIntentar(redes, i);
  if (!r) return;
  redesIdx = i;
  if (cortarAntes) WiFi.disconnect();
  WiFi.begin(r->ssid, r->clave[0] ? r->clave : nullptr);
  Serial.printf("Wi-Fi: probando '%s' (%d/%d)%s...\n", r->ssid, i + 1, redesCantidadAIntentar(redes),
                redes.hayCandidata ? " [candidata]" : (redesRespaldoActivo ? " [respaldo de wifi_config.h]" : ""));
}

// Para reintentar con la siguiente red cuando la actual no conecta (con una sola red, repite la misma).
void redesRotar() {
  redesIntentar(redesSiguiente(redes, redesIdx), true);
}

// Llamar tras esperar el Wi-Fi del arranque. Si había candidata: conectó -> queda confirmada; no conectó -> se descarta.
// Devuelve 1 si se confirmó, -1 si se descartó, 0 si no había candidata.
int redesResolverCandidata(bool conecto) {
  if (!redes.hayCandidata) return 0;
  char ssid[REDES_SSID_MAX + 1];
  snprintf(ssid, sizeof(ssid), "%s", redes.candidata.ssid);
  if (conecto) {
    redesConfirmarCandidata(redes);
    redesGuardar();
    Serial.printf("Wi-Fi: '%s' conectó: queda guardada como la primera.\n", ssid);
    return 1;
  }
  redesDescartarCandidata(redes);
  redesGuardar();
  Serial.printf("Wi-Fi: '%s' no conectó: se descarta (las demás redes siguen guardadas).\n", ssid);
  redesIdx = 0;
  return -1;
}

// ---------- Operaciones que usan el portal y los comandos (guardan en NVS) ----------

RedesError redesGuardarCandidata(const char* ssid, const char* clave) {
  redesSoltarRespaldo();
  RedesError e = redesProponer(redes, ssid, clave);
  if (e == REDES_OK) redesGuardar(); else redesCargar();
  return e;
}

bool redesOlvidarGuardada(const char* ssid) {
  redesSoltarRespaldo();
  bool ok = redesOlvidar(redes, ssid);
  if (ok) redesGuardar(); else redesCargar();
  return ok;
}

// Borra todas las redes y la candidata (y la marca de "abrir el portal"). El respaldo de wifi_config.h volverá a verse en el próximo redesCargar().
void redesBorrarTodoNVS() {
  redesBorrarTodas(redes);
  redesRespaldoActivo = false;
  Preferences p;
  if (p.begin("wifi", false)) { p.clear(); p.end(); }
}

// Marca "abrir el portal en el próximo arranque" (comando por cable `wifi portal`). Se lee y se borra en portalPedidoPorMarca().
void redesPedirPortal() {
  Preferences p;
  if (p.begin("wifi", false)) { p.putBool("portal", true); p.end(); }
}

bool redesLeerMarcaPortal() {
  Preferences p;
  bool v = false;
  if (p.begin("wifi", false)) { v = p.getBool("portal", false); if (v) p.remove("portal"); p.end(); }
  return v;
}

// ---------- Comandos por Serial (solo por cable; no pasan por /cmd) ----------
//   wifi lista | wifi agregar NOMBRE|CLAVE | wifi candidata NOMBRE|CLAVE | wifi olvidar NOMBRE | wifi borrar
// NOMBRE y CLAVE se separan en el primer "|" (la clave puede llevar espacios; sin "|" la red es abierta).

static void redesReiniciarEn1s(const char* motivo) {
  Serial.printf("%s Reinicio en 1 s para aplicar.\n", motivo);
  delay(1000);
  ESP.restart();
}

void redesComando(char* args) {
  while (*args == ' ') args++;
  if (strcasecmp(args, "lista") == 0) {
    if (!redesHay()) { Serial.println("Wi-Fi: no hay redes guardadas."); return; }
    for (int i = 0; i < redes.n; i++)
      Serial.printf("  %d. %s%s\n", i + 1, redes.red[i].ssid, redesRespaldoActivo ? "  (respaldo de wifi_config.h, no guardada)" : "");
    if (redes.hayCandidata) Serial.printf("  candidata: %s (se prueba al arrancar)\n", redes.candidata.ssid);
    return;
  }
  if (strcasecmp(args, "borrar") == 0) {
    redesBorrarTodoNVS();
    redesReiniciarEn1s("Wi-Fi: redes borradas.");
    return;
  }
  if (strcasecmp(args, "portal") == 0) {
    redesPedirPortal();
    redesReiniciarEn1s("Wi-Fi: el portal se abre al arrancar.");
    return;
  }
  bool agregar = strncasecmp(args, "agregar ", 8) == 0;
  bool candidata = strncasecmp(args, "candidata ", 10) == 0;
  if (agregar || candidata) {
    char* ssid = args + (agregar ? 8 : 10);
    while (*ssid == ' ') ssid++;
    char* barra = strchr(ssid, '|');
    const char* clave = "";
    if (barra) { *barra = 0; clave = barra + 1; }
    RedesError e;
    if (agregar) {
      redesSoltarRespaldo();
      e = redesAgregar(redes, ssid, clave);
      if (e == REDES_OK) redesGuardar(); else redesCargar();
    } else {
      e = redesGuardarCandidata(ssid, clave);
    }
    if (e != REDES_OK) { Serial.printf("Wi-Fi: no guardé la red: %s.\n", redesTextoError(e)); return; }
    redesReiniciarEn1s(agregar ? "Wi-Fi: red guardada." : "Wi-Fi: candidata guardada (se prueba al arrancar).");
    return;
  }
  if (strncasecmp(args, "olvidar ", 8) == 0) {
    char* ssid = args + 8;
    while (*ssid == ' ') ssid++;
    if (!redesOlvidarGuardada(ssid)) { Serial.println("Wi-Fi: no tengo esa red."); return; }
    redesReiniciarEn1s("Wi-Fi: red olvidada.");
    return;
  }
  Serial.println("Wi-Fi: uso: wifi lista | wifi agregar NOMBRE|CLAVE | wifi candidata NOMBRE|CLAVE | wifi olvidar NOMBRE | wifi borrar | wifi portal");
}
