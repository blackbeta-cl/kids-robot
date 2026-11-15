/*
  actualizar.h — actualización del firmware desde el servidor (OTA por internet).
  Se incluye desde robot_rostro.ino DESPUÉS de voz.h y estado.h.

  Cómo funciona (el robot siempre inicia la conexión; el servidor no puede "empujar" detrás del router):
    - Una tarea (núcleo 0) pregunta cada ~10 min a GET /firmware/version (con X-Token) si hay una versión MAYOR.
      Solo pregunta con el robot en reposo (>= 2 min sin hablar, sin texto en pantalla).
    - Si hay una nueva: pantalla "Actualizar a vX" con cuenta regresiva de 30 s.
        toque corto = más tarde (vuelve a preguntar en 1 h) · mantener el toque (1 s) = instalar ya · sin respuesta = se instala sola.
      La instalación sin respuesta ocurre como mucho una vez cada 24 h.
    - Descarga GET /firmware/app.bin con TLS verificado, comprueba tamaño y SHA-256 del manifiesto ANTES de dar el firmware por bueno,
      y reinicia. Si algo falla, el firmware anterior sigue intacto.
    - Rollback: el firmware nuevo queda "pendiente" y solo se da por bueno tras ACT_VALIDAR_MS sin reiniciarse; si se cuelga antes,
      el bootloader vuelve al anterior (ver verifyRollbackLater en robot_rostro.ino).
    - Búsqueda a pedido (comando serie "buscar"; luego, la orden de voz): consulta ya y, si hay nueva, usa la misma cuenta regresiva.
*/
#pragma once

#include <HTTPClient.h>
#include <Update.h>
#include <esp_ota_ops.h>
#include <mbedtls/sha256.h>
#include <mbedtls/pk.h>
#include "firma_publica.h"

#define ACT_CONSULTA_MS     (10UL * 60 * 1000)   // cada cuánto pregunta al servidor
#define ACT_REPOSO_MS        (2UL * 60 * 1000)    // reposo mínimo antes de preguntar o avisar
#define ACT_CUENTA_S         30                   // cuenta regresiva
#define ACT_POSPONER_MS      (60UL * 60 * 1000)   // si dices "más tarde"
#define ACT_FALLO_MS         (30UL * 60 * 1000)   // reintento tras un fallo
#define ACT_AUTO_INTERVALO_S (24UL * 3600)        // instalación sin respuesta: máximo una cada 24 h
#define ACT_VALIDAR_MS       45000                // tiempo sano antes de dar por bueno un firmware nuevo
#define ACT_TOQUE_LARGO_MS   1000

enum EstadoAct : uint8_t { ACT_NADA, ACT_PREGUNTA, ACT_INSTALANDO, ACT_LISTO, ACT_FALLO };
enum AvisoAct : uint8_t { ACT_AVISO_NINGUNO, ACT_AVISO_AL_DIA, ACT_AVISO_ERROR, ACT_AVISO_SIN_RED };

volatile uint8_t actEstado = ACT_NADA;
volatile bool actPidioBuscar = false;
volatile uint8_t actPct = 0;
volatile uint8_t actAviso = ACT_AVISO_NINGUNO;   // respuesta a una búsqueda pedida (la muestra loop)
char actVersion[16] = "";                        // versión ofrecida por el servidor
char actSha[65] = "";
uint32_t actBytes = 0;
char actMotivo[32] = "";
uint32_t actUltimaActividad = 0, actProximaConsulta = 0, actInicioCuenta = 0, actHasta = 0;
bool actManual = false;                          // la búsqueda actual la pidió una persona
bool actValidado = false;

// ---------- Versiones ----------

bool actEsMayor(const char* nueva, const char* actual) {
  int a[3] = {0, 0, 0}, b[3] = {0, 0, 0};
  sscanf(nueva, "%d.%d.%d", &a[0], &a[1], &a[2]);
  sscanf(actual, "%d.%d.%d", &b[0], &b[1], &b[2]);
  for (int i = 0; i < 3; i++) if (a[i] != b[i]) return a[i] > b[i];
  return false;
}

bool actAutoPermitido() {
  Preferences p;
  uint32_t ultima = 0;
  if (p.begin("robot", true)) { ultima = p.getUInt("autoact", 0); p.end(); }
  uint32_t ahora = (uint32_t)time(nullptr);
  return ultima == 0 || ahora < ultima || ahora - ultima >= ACT_AUTO_INTERVALO_S;
}

void actAnotarAuto() {
  Preferences p;
  if (p.begin("robot", false)) { p.putUInt("autoact", (uint32_t)time(nullptr)); p.end(); }
}

// ---------- Firma ----------
// El firmware lo firma quien lo publica con una clave privada que NO está en el servidor (publicar.ps1 / publicar.sh, ECDSA P-256).
// Se firma el texto "kids-robot-fw:<version>:<sha256>": así la firma ata la versión y el contenido (no se puede
// servir un firmware viejo firmado haciéndolo pasar por una versión nueva). Sin firma válida, el robot ni lo ofrece.
bool actVerificarFirma(const char* version, const char* sha, const char* firmaHex) {
  size_t n = strlen(firmaHex);
  if (n < 16 || n > 160 || (n & 1)) return false;
  uint8_t firma[80];
  for (size_t i = 0; i < n / 2; i++) {
    char par[3] = {firmaHex[2 * i], firmaHex[2 * i + 1], 0};
    char* fin = nullptr;
    long v = strtol(par, &fin, 16);
    if (*fin) return false;
    firma[i] = (uint8_t)v;
  }
  char mensaje[128];
  int largo = snprintf(mensaje, sizeof(mensaje), "kids-robot-fw:%s:%s", version, sha);
  if (largo <= 0 || largo >= (int)sizeof(mensaje)) return false;
  uint8_t hash[32];
  mbedtls_sha256((const uint8_t*)mensaje, largo, hash, 0);

  mbedtls_pk_context pk;
  mbedtls_pk_init(&pk);
  bool ok = mbedtls_pk_parse_public_key(&pk, (const uint8_t*)FIRMA_CLAVE_PUBLICA, sizeof(FIRMA_CLAVE_PUBLICA)) == 0 &&
            mbedtls_pk_verify(&pk, MBEDTLS_MD_SHA256, hash, sizeof(hash), firma, n / 2) == 0;
  mbedtls_pk_free(&pk);
  return ok;
}

// ---------- Red (en la tarea) ----------

// 0 = al día (o nada publicado), 1 = hay una versión mayor (rellena actVersion/actSha/actBytes), -1 = no pude consultar.
int actConsultar() {
  VozCliente cliente;
  vozPrepararCliente(cliente);
  HTTPClient http;
  http.setConnectTimeout(15000);
  http.setTimeout(15000);
  String url = String(VOZ_ESQUEMA) + cfgHost + ":" + cfgPuerto + "/firmware/version";
  if (!http.begin(cliente, url)) return -1;
  if (cfgToken[0]) http.addHeader("X-Token", cfgToken);
  int codigo = http.GET();
  if (codigo == 404) { http.end(); Serial.println("Actualizar: el servidor no tiene firmware publicado."); return 0; }
  if (codigo != 200) {
    Serial.printf("Actualizar: consulta falló (%d %s)\n", codigo, codigo < 0 ? http.errorToString(codigo).c_str() : "");
    vozDetalleTls(cliente);
    http.end();
    return -1;
  }
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, http.getString());
  http.end();
  const char* version = doc["version"] | "";
  const char* sha = doc["sha256"] | "";
  uint32_t bytes = doc["bytes"] | 0;
  const char* firma = doc["firma"] | "";
  if (err || !version[0] || strlen(sha) != 64 || bytes < 100000) { Serial.println("Actualizar: respuesta del servidor inválida."); return -1; }
  if (!actEsMayor(version, FIRMWARE_VERSION)) {
    Serial.printf("Actualizar: ya tengo la última (servidor v%s, yo v%s).\n", version, FIRMWARE_VERSION);
    return 0;
  }
  if (!actVerificarFirma(version, sha, firma)) {
    Serial.printf("Actualizar: FIRMA INVÁLIDA o ausente para v%s: no se ofrece ni se instala.\n", version);
    return -1;
  }
  snprintf(actVersion, sizeof(actVersion), "%s", version);
  snprintf(actSha, sizeof(actSha), "%s", sha);
  actBytes = bytes;
  Serial.printf("Actualizar: hay una versión nueva: v%s (%u bytes, firma ok); yo tengo v%s.\n", version, (unsigned)bytes, FIRMWARE_VERSION);
  return 1;
}

bool actFallar(const char* motivo) {
  snprintf(actMotivo, sizeof(actMotivo), "%s", motivo);
  Serial.printf("Actualizar: falló (%s). Sigo con el firmware de antes.\n", motivo);
  return false;
}

// Baja el firmware, lo escribe en la otra ranura y comprueba tamaño y SHA-256. Solo si todo coincide lo da por bueno.
bool actDescargar() {
  anuncioOta();                            // beeps + "Actualizando en tres, dos, uno" antes de escribir la flash
  VozCliente cliente;
  vozPrepararCliente(cliente);
  HTTPClient http;
  http.setConnectTimeout(15000);
  http.setTimeout(20000);
  String url = String(VOZ_ESQUEMA) + cfgHost + ":" + cfgPuerto + "/firmware/app.bin";
  if (!http.begin(cliente, url)) return actFallar("Sin conexion");
  if (cfgToken[0]) http.addHeader("X-Token", cfgToken);
  int codigo = http.GET();
  if (codigo != 200) { vozDetalleTls(cliente); http.end(); return actFallar(codigo < 0 ? "Sin conexion" : "Servidor dijo no"); }
  int tam = http.getSize();
  if (tam <= 0 || (uint32_t)tam != actBytes) { http.end(); return actFallar("Tamano distinto"); }
  if (!Update.begin(tam)) { http.end(); return actFallar("Sin espacio"); }

  mbedtls_sha256_context ctx;
  mbedtls_sha256_init(&ctx);
  mbedtls_sha256_starts(&ctx, 0);
  static uint8_t buf[2048];
  WiFiClient* flujo = http.getStreamPtr();
  size_t total = 0;
  uint32_t ultimo = millis();
  uint32_t t0 = millis();
  while (total < (size_t)tam) {
    int disp = flujo->available();
    if (disp <= 0) {
      if (!flujo->connected() && flujo->available() <= 0) break;
      if (millis() - ultimo > 20000) break;
      vTaskDelay(pdMS_TO_TICKS(5));
      continue;
    }
    size_t quiero = min((size_t)disp, min(sizeof(buf), (size_t)tam - total));
    int n = flujo->readBytes(buf, quiero);
    if (n <= 0) continue;
    if (Update.write(buf, n) != (size_t)n) { Update.abort(); mbedtls_sha256_free(&ctx); http.end(); return actFallar("No pude escribir"); }
    mbedtls_sha256_update(&ctx, buf, n);
    total += n;
    ultimo = millis();
    actPct = (uint8_t)((uint64_t)total * 100 / tam);
  }
  http.end();
  if (total != (size_t)tam) { Update.abort(); mbedtls_sha256_free(&ctx); return actFallar("Se corto la bajada"); }

  uint8_t hash[32];
  mbedtls_sha256_finish(&ctx, hash);
  mbedtls_sha256_free(&ctx);
  char hex[65];
  for (int i = 0; i < 32; i++) snprintf(hex + 2 * i, 3, "%02x", hash[i]);
  if (strcasecmp(hex, actSha) != 0) { Update.abort(); return actFallar("Archivo corrupto"); }
  if (!Update.end(true)) { return actFallar("Imagen invalida"); }

  Preferences p;
  if (p.begin("robot", false)) { p.putString("prev", FIRMWARE_VERSION); p.end(); }   // el arranque siguiente dirá "Actualizado a vX"
  Serial.printf("Actualizar: v%s instalada en %lu ms, SHA-256 ok. Reinicio para usarla.\n", actVersion, (unsigned long)(millis() - t0));
  return true;
}

void tareaActualizar(void*) {
  for (;;) {
    vTaskDelay(pdMS_TO_TICKS(500));
    if (actEstado == ACT_INSTALANDO) {
      actEstado = actDescargar() ? ACT_LISTO : ACT_FALLO;
      continue;
    }
    if (actEstado != ACT_NADA) continue;

    uint32_t ahora = millis();
    bool manual = actPidioBuscar;
    if (!manual) {
      if ((int32_t)(ahora - actProximaConsulta) < 0) continue;
      if (vozEstado != VOZ_REPOSO || ahora - actUltimaActividad < ACT_REPOSO_MS || otaEnCurso || hayTexto) continue;
    } else {
      // Pedida por voz: el robot todavía está diciendo "voy a ver..."; se espera a que termine (menos memoria en uso a la vez y la respuesta sale en orden).
      for (int i = 0; i < 200 && vozEstado != VOZ_REPOSO; i++) vTaskDelay(pdMS_TO_TICKS(100));
      ahora = millis();
    }
    if (WiFi.status() != WL_CONNECTED || time(nullptr) < 1700000000) {    // sin red o sin hora no se puede verificar el certificado
      if (manual) { actPidioBuscar = false; actAviso = ACT_AVISO_SIN_RED; }
      else actProximaConsulta = ahora + 60000;
      continue;
    }
    actPidioBuscar = false;
    actProximaConsulta = ahora + ACT_CONSULTA_MS;
    int r = actConsultar();
    if (r < 0) { if (manual) actAviso = ACT_AVISO_ERROR; continue; }
    if (r == 0) { if (manual) actAviso = ACT_AVISO_AL_DIA; continue; }
    if (!manual && !actAutoPermitido()) { Serial.println("Actualizar: hay versión nueva, pero ya se instaló una sola hace menos de 24 h."); continue; }

    actManual = manual;
    vozToqueEvento = TOQUE_NADA;
    vozModoRespuesta = true;                 // desde aquí el toque responde la pregunta y no graba
    actInicioCuenta = millis();
    actEstado = ACT_PREGUNTA;
  }
}

// ---------- Pantalla y decisiones (en loop) ----------

bool actPantallaActiva() { return actEstado != ACT_NADA && actEstado != ACT_FALLO; }

void actDibujar(uint32_t ahora) {
  if (actEstado == ACT_PREGUNTA) {
    int resta = max(0, (int)ACT_CUENTA_S - (int)((ahora - actInicioCuenta) / 1000));
    estInicioTexto();
    char t[32], n[8];
    snprintf(t, sizeof(t), "Actualizar a v%s", actVersion);
    snprintf(n, sizeof(n), "%d", resta);
    estCentrado(t, 1, 2);
    estCentrado(n, 3, 14);
    estCentrado("Toca: mas tarde", 1, 42);
    estCentrado("Manten: ya", 1, 54);
    pantalla.display();
  } else if (actEstado == ACT_INSTALANDO) {
    estPantallaOta("Actualizando...", actPct, "No me apagues");
  } else if (actEstado == ACT_LISTO) {
    estPantallaOta("Actualizacion lista", -1, "Reiniciando...");
  }
}

void actAtender(uint32_t ahora) {
  if (vozEstado != VOZ_REPOSO) actUltimaActividad = ahora;

  if (vozAccionBuscar) {                      // "busca actualizaciones para ti": la orden de voz llegó con la respuesta
    vozAccionBuscar = false;
    actPidioBuscar = true;
    Serial.println("Actualizar: me lo pidieron por voz, busco ahora.");
  }

  uint8_t aviso = actAviso;
  if (aviso && vozEstado == VOZ_REPOSO) {     // el mensaje espera a que el robot termine de hablar
    actAviso = ACT_AVISO_NINGUNO;
    if (aviso == ACT_AVISO_AL_DIA) estAviso("Al dia", "", "Ya tengo la ultima", 3);
    else if (aviso == ACT_AVISO_SIN_RED) estAviso("Sin red", "", "No puedo buscar ahora", 3);
    else estAviso("No pude buscar", "", "Pruebo mas tarde", 3);
  }

  if (actEstado == ACT_PREGUNTA) {
    uint8_t ev = vozToqueEvento;
    vozToqueEvento = TOQUE_NADA;
    bool venció = ahora - actInicioCuenta >= ACT_CUENTA_S * 1000UL;
    if (ev == TOQUE_CORTO) {
      vozModoRespuesta = false;
      actEstado = ACT_NADA;
      actProximaConsulta = ahora + ACT_POSPONER_MS;
      Serial.println("Actualizar: pospuesta una hora.");
      estAviso("Mas tarde", "", "Te vuelvo a preguntar", 3);
    } else if (ev == TOQUE_LARGO || venció) {
      if (ev != TOQUE_LARGO && !actManual) actAnotarAuto();   // instalación sin respuesta: cuenta para el límite de 24 h
      vozModoRespuesta = false;
      vozPausada = true;                                      // la voz no compite por CPU ni memoria
      modoDemo = false;
      hayTexto = false;
      actPct = 0;
      Serial.printf("Actualizar: instalo v%s (%s).\n", actVersion, ev == TOQUE_LARGO ? "pedido con el toque" : "sin respuesta");
      actEstado = ACT_INSTALANDO;
    }
  } else if (actEstado == ACT_LISTO) {
    if (actHasta == 0) actHasta = ahora + 1500;
    else if ((int32_t)(ahora - actHasta) >= 0) ESP.restart();
  } else if (actEstado == ACT_FALLO) {
    vozPausada = false;
    estAviso("Fallo OTA", "", actMotivo, 5);
    actProximaConsulta = ahora + ACT_FALLO_MS;
    actEstado = ACT_NADA;
  }

  // Un firmware recién instalado queda "pendiente": si se cuelga antes de esto, el bootloader vuelve al anterior.
  if (!actValidado && ahora >= ACT_VALIDAR_MS) {
    actValidado = true;
    esp_err_t e = esp_ota_mark_app_valid_cancel_rollback();
    Serial.printf("Firmware v%s: %s.\n", FIRMWARE_VERSION, e == ESP_OK ? "validado tras el arranque (rollback cancelado)" : "ya estaba validado");
  }
}

void actIniciar() {
  actUltimaActividad = millis();
  actProximaConsulta = millis() + 60000;          // primera consulta ~1 min tras arrancar (y con >= 2 min de reposo)
  if (!redesHay()) return;
  xTaskCreatePinnedToCore(tareaActualizar, "act", VOZ_STACK_TAREA, nullptr, 1, nullptr, 0);
}
