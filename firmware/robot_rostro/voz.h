/*
  voz.h — voz por toque para robot_rostro (TTP223 + INMP441 + MAX98357A + Wi-Fi).

  Mientras el TTP223 (GPIO 14) está tocado, graba el micrófono a 16 kHz, mono, 16 bits, en PSRAM
  (máx. 10 s). Al soltar lo envía como WAV por POST al servidor (server/puente.py, ruta /voz/stream)
  y toca por el MAX98357A el WAV que contesta.

  Todo esto corre en una tarea aparte (núcleo 0) para no frenar la animación de la cara en loop().
  La tarea NO toca la pantalla ni el servo: solo deja el estado y lo que mandó el PC en las
  variables vozEstado / vozEmocion / vozCuello, y loop() (atenderVoz) los muestra.

  Grabación: se descartan los primeros 150 ms (golpe del toque) y los últimos 100 ms (golpe de soltar);
  los toques de menos de 400 ms se ignoran.

  Modo conversación (VOZ_CONVERSACION): después de cada respuesta se queda escuchando 5 s (cara sorprendida).
  Si el niño habla sin tocar (4 bloques seguidos sobre 2,5 veces el ruido de fondo), graba solo, con 400 ms de
  audio anterior para no perder la primera sílaba, y cierra la frase tras 700 ms de silencio. Hasta 5 turnos
  seguidos sin tocar; el toque reinicia la cuenta. "conv" por Serial lo enciende y apaga en caliente.

  El TTP223 se dispara solo: el toque no se acepta hasta 3 s después de arrancar y con el sensor en reposo;
  las grabaciones sin voz se descartan. Contadores y estado en /estado (voz_armado, voz_linea, toque_cortos,
  toque_sin_voz, voz_piso...).
  Por Serial/HTTP (procesarLinea):  vol 0..100  |  repetir  |  conv  (alterna el modo conversación)

  Pines: TTP223 IO 14 | INMP441 SCK 4, WS 5, SD 6 | MAX98357A BCLK 15, LRC 16, DIN 17
  Configuración: copia voz_config.example.h a voz_config.h (no se sube a git), o usa los comandos "servidor" y "token" (servidor_cfg.h).
  Token: se manda como cabecera X-Token (mismo valor que ROBOT_TOKEN del servidor).
  HTTPS: con VOZ_HTTPS 1 en voz_config.h el robot habla con https://<servidor>:<puerto> verificando el certificado
  (raíces del core) y la hora por NTP (zona VOZ_ZONA_HORARIA); el servidor puede ser un nombre, p. ej. robot.example.com.
*/
#pragma once

#include <ESP_I2S.h>
#include <HTTPClient.h>
#include <NetworkClientSecure.h>
#include "voz_config.h"
#include "servidor_cfg.h"   // servidor y token (de voz_config.h / wifi_config.h o guardados en NVS)
#include "microfono.h"     // captura del micrófono en su propia tarea (sin perder audio) y filtro pasa-altos
#include "anuncio_ota.h"   // WAV del anuncio de OTA (generar_anuncio_ota.py)

#define VOZ_PIN_TACTO 14
#define VOZ_PIN_SCK 4
#define VOZ_PIN_WS  5
#define VOZ_PIN_SD  6
#define VOZ_PIN_BCLK_SALIDA 15
#define VOZ_PIN_LRC_SALIDA  16
#define VOZ_PIN_DIN_SALIDA  17

#define VOZ_FS 16000                 // (no se llama FS: choca con la clase FS de WebServer)
#define VOZ_MS_ANTIRREBOTE 30
#define VOZ_MS_TOQUE_MIN 400         // toques más cortos se ignoran
#define VOZ_MS_ARMAR 3000            // el toque no se acepta hasta 3 s después de arrancar (y con el sensor en reposo)
#define VOZ_PICO_MIN 600             // grabaciones con pico menor: no hay voz (posible toque falso), no se envían
#define VOZ_CONVERSACION 1           // tras responder queda escuchando unos segundos (0 = solo con el toque)
#define VOZ_MS_ESPERA 5000           // ventana para contestar sin volver a tocar
#define VOZ_VAD_MIN 3500             // pico mínimo (16 bits, ganancia x8) para dar por empezada una voz (los disparos de 2.300 con umbral 2.100 eran ruido; la voz cercana mide 4.800-20.000)
#define VOZ_GUARDA_MS 700            // tras hablar el robot, el micrófono aún oye su propia voz (eco del parlante): ese tiempo se descarta
#define VOZ_VAD_FACTOR 2.0f          // además debe superar 2 veces el ruido de fondo medido
#define VOZ_PISO_ALPHA 0.90f         // el ruido de fondo BAJA rápido (peso de lo anterior)
#define VOZ_PISO_SUBE 0.998f         // ...y SUBE muy lento: la voz no debe contarse como ruido (si no, el umbral la deja afuera)
#define VOZ_PISO_MAX 4000.0f         // tope del ruido de fondo (escala de la grabación): el umbral nunca pasa de ~6000
#define VOZ_UMBRAL_TECHO 8000        // el umbral que se informa en /estado no pasa de aquí
#define VOZ_VAD_BLOQUES 8            // 8 bloques seguidos de 16 ms (~130 ms): una palabra, no un golpe
#define VOZ_FIN_SILENCIO 700         // ms de silencio para cerrar la frase
#define VOZ_PREVIO_MS 400            // audio anterior al disparo que se incluye (no perder la primera sílaba)
#define VOZ_MAX_TURNOS 5             // turnos seguidos sin tocar; después hay que tocar
#define VOZ_MS_DESCARTE_INICIO 150   // golpe del toque
#define VOZ_MS_DESCARTE_FINAL 100    // golpe de soltar
#define VOZ_SEG_MAX 10
#define VOZ_DESPLAZAR 5              // 24 bits -> 16 bits con ganancia x8 (>> 8 sería ganancia 1); las muestras llegan de microfono.h ya filtradas
#define VOZ_VOLUMEN_INICIAL 30       // % del WAV recibido. Se cambia con "vol N"
#define VOZ_RESPUESTA_MAX_BYTES (2 * 1024 * 1024)   // ~43 s a 24 kHz mono 16 bits
#define VOZ_STREAMING 1              // 1 = empieza a sonar con la primera frase (POST /voz/stream); 0 = baja todo y luego suena (POST /voz)
#ifndef VOZ_HTTPS
#define VOZ_HTTPS 0                  // se define en voz_config.h: 1 = HTTPS verificando el certificado (servidor en la nube); 0 = HTTP (PC de la casa)
#endif
#ifndef VOZ_ZONA_HORARIA
#define VOZ_ZONA_HORARIA "UTC0"      // cadena POSIX TZ; se cambia en voz_config.h (ejemplos en voz_config.example.h)
#endif
#define VOZ_PRECARGA_MS 300          // audio por delante antes de empezar a sonar (colchón contra los cortes de la red)
#if VOZ_HTTPS
#define VOZ_ESQUEMA "https://"
#define VOZ_STACK_TAREA 28672        // el apretón de manos TLS necesita más pila que HTTP plano
#else
#define VOZ_ESQUEMA "http://"
#define VOZ_STACK_TAREA 16384
#endif

#define VOZ_MUESTRAS_INICIO ((VOZ_FS / 1000) * VOZ_MS_DESCARTE_INICIO)
#define VOZ_MUESTRAS_FINAL  ((VOZ_FS / 1000) * VOZ_MS_DESCARTE_FINAL)
#define VOZ_MUESTRAS_MAX    (VOZ_FS * VOZ_SEG_MAX)
#define VOZ_LARGO_CABECERA  44

// ---------- Estado que ve loop() ----------

enum EstadoVoz : uint8_t { VOZ_REPOSO, VOZ_ESCUCHANDO, VOZ_PENSANDO, VOZ_HABLANDO, VOZ_ESPERANDO };
volatile uint8_t vozEstado = VOZ_REPOSO;
char vozEmocion[24] = "neutral";          // emoción que pide el PC (X-Emocion); se escribe antes de pasar a HABLANDO
volatile int vozCuello = -1;              // grados que pide el PC (X-Cuello), o -1
volatile int vozVolumenPct = VOZ_VOLUMEN_INICIAL;
volatile bool vozPidioRepetir = false;
bool vozActiva = false;
volatile bool vozPausada = false;         // true durante una actualización OTA: la tarea no graba ni envía
volatile bool vozAccionBuscar = false;    // el PC pidió (X-Accion: buscar_actualizacion) que el robot busque una versión nueva
volatile bool vozModoRespuesta = false;  // true mientras robot_rostro pregunta algo con cuenta regresiva: el toque no graba, solo responde
enum ToqueVoz : uint8_t { TOQUE_NADA, TOQUE_CORTO, TOQUE_LARGO };
volatile uint8_t vozToqueEvento = TOQUE_NADA;   // respuesta al tocar en ese modo: toque corto o mantenido (>= 1 s)
enum FalloVoz : uint8_t { VOZ_FALLO_NINGUNO, VOZ_FALLO_WIFI, VOZ_FALLO_HORA, VOZ_FALLO_SERVIDOR };
volatile uint8_t vozFallo = VOZ_FALLO_NINGUNO;   // por qué falló la última conversación (lo muestra estado.h)

void vozFijarVolumen(int pct) {
  vozVolumenPct = constrain(pct, 0, 100);
  Serial.printf("Volumen: %d%%\n", (int)vozVolumenPct);
}

// ---------- Memoria y objetos (solo los usa la tarea de voz) ----------

// Datos de un WAV ya analizado (va antes de las funciones: el preprocesador de Arduino genera los prototipos arriba).
struct InfoWav { uint32_t tasa; uint16_t canales, bits; const uint8_t* datos; uint32_t largo; };

I2SClass vozMicrofono;                    // RX
I2SClass vozParlante;                     // TX: otra instancia, otro controlador I2S
uint8_t* vozWav = nullptr;                // cabecera (44 bytes) + audio grabado, en PSRAM
int16_t* vozAudio = nullptr;              // apunta a vozWav + 44
uint8_t* vozRespuesta = nullptr;          // WAV que contesta el PC
size_t vozRespuestaBytes = 0;

bool vozLeido = false, vozEstable = false;
uint32_t vozCambioCrudo = 0;
bool vozGrabando = false;
uint32_t vozInicioToque = 0;
uint32_t vozEscritas = 0;                 // muestras guardadas (ya sin las del inicio)
uint32_t vozVistas = 0;                   // muestras leídas desde que empezó el toque
bool vozLlenoAvisado = false;

// Diagnóstico del TTP223 (se dispara solo): se ven en /estado sin abrir el serie.
volatile bool vozArmado = false;             // false hasta 3 s después de arrancar y con el sensor en reposo
volatile uint32_t vozToquesCortos = 0;       // pulsos < 400 ms ignorados
volatile uint32_t vozToquesSinVoz = 0;       // grabaciones descartadas por nivel (posible toque falso)
volatile uint32_t vozUltimoToqueMs = 0;      // duración del último toque aceptado

// Modo conversación: después de responder queda escuchando unos segundos, sin tocar.
bool vozConversacion = VOZ_CONVERSACION;
volatile bool vozEsperando = false;
bool vozAutoGrabando = false;                // la grabación la abrió la ventana conversacional, no el toque
volatile uint8_t vozTurnos = 0;              // turnos automáticos seguidos (se reinicia al tocar)
float vozPiso = 1000.0f;                     // ruido de fondo (media del pico por bloque, escala de la grabación)
uint32_t vozVentanaDesde = 0;
uint32_t vozUltimaVoz = 0;
uint8_t vozVozBloques = 0;
volatile uint32_t vozVentanas = 0, vozAutos = 0;   // ventanas abiertas y veces que el micrófono disparó solo
volatile int32_t vozMaxPico = 0, vozMaxUmbral = 0; // lo más fuerte que se oyó y el umbral de esa ventana (diagnóstico)
volatile uint32_t vozWinIt = 0;                    // veces que se evaluó la ventana (si queda en pocas, algo la interrumpe)
volatile uint32_t vozDisparoMs = 0, vozDisparoPico = 0;   // a los cuántos ms de acabar la guarda se oyó voz, y con qué pico
volatile uint8_t vozWinFin = 0;                    // 0 abierta/interrumpida, 1 se acabó el tiempo, 2 se oyó voz

// Abre (o cierra) la ventana de conversación. Solo se llama después de una respuesta hablada.
void vozAbrirVentana() {
  vozVozBloques = 0;
  if (!vozConversacion || vozTurnos >= VOZ_MAX_TURNOS) { vozEsperando = false; vozEstado = VOZ_REPOSO; return; }
  vozEsperando = true;
  vozVentanaDesde = millis() + VOZ_GUARDA_MS;          // la espera de VOZ_MS_ESPERA cuenta desde que acaba la guarda
  vozEstado = VOZ_ESPERANDO;
  vozVentanas++;
  vozMaxPico = 0; vozMaxUmbral = 0; vozWinIt = 0; vozWinFin = 0;
  Serial.printf("Voz: te escucho %d ms (sin tocar, turno %d de %d)\n", VOZ_MS_ESPERA, vozTurnos + 1, VOZ_MAX_TURNOS);
}

// ---------- WAV ----------

void vozEscribirCabecera(uint32_t muestras) {
  uint32_t datos = muestras * 2;
  uint32_t riff = 36 + datos;
  uint32_t fmtLargo = 16, tasa = VOZ_FS, bytesSeg = VOZ_FS * 2;
  uint16_t formato = 1, canales = 1, alinea = 2, bits = 16;
  memcpy(vozWav + 0, "RIFF", 4);  memcpy(vozWav + 4, &riff, 4);
  memcpy(vozWav + 8, "WAVE", 4);  memcpy(vozWav + 12, "fmt ", 4);
  memcpy(vozWav + 16, &fmtLargo, 4); memcpy(vozWav + 20, &formato, 2); memcpy(vozWav + 22, &canales, 2);
  memcpy(vozWav + 24, &tasa, 4);  memcpy(vozWav + 28, &bytesSeg, 4);
  memcpy(vozWav + 32, &alinea, 2); memcpy(vozWav + 34, &bits, 2);
  memcpy(vozWav + 36, "data", 4); memcpy(vozWav + 40, &datos, 4);
}

// Recorre los trozos del WAV (no supone que la cabecera mida 44 bytes).
bool vozAnalizarWav(const uint8_t* b, size_t n, InfoWav& w) {
  if (n < 44 || memcmp(b, "RIFF", 4) || memcmp(b + 8, "WAVE", 4)) return false;
  size_t pos = 12;
  bool hayFmt = false;
  while (pos + 8 <= n) {
    uint32_t tam; memcpy(&tam, b + pos + 4, 4);
    if (!memcmp(b + pos, "fmt ", 4) && pos + 8 + 16 <= n) {
      uint16_t formato; memcpy(&formato, b + pos + 8, 2);
      memcpy(&w.canales, b + pos + 10, 2); memcpy(&w.tasa, b + pos + 12, 4); memcpy(&w.bits, b + pos + 22, 2);
      if (formato != 1) return false;                    // solo PCM
      hayFmt = true;
    } else if (!memcmp(b + pos, "data", 4)) {
      if (!hayFmt) return false;
      w.datos = b + pos + 8;
      w.largo = min((size_t)tam, n - pos - 8);
      return true;
    }
    pos += 8 + (size_t)tam + (tam & 1);
  }
  return false;
}

// ---------- Parlante ----------

void vozReproducir(const uint8_t* bytes, size_t n) {
  InfoWav w;
  if (!vozAnalizarWav(bytes, n, w)) { Serial.println("La respuesta no es un WAV valido."); return; }
  if (w.bits != 16 || w.canales < 1 || w.canales > 2) {
    Serial.printf("WAV no soportado (%u bits, %u canales).\n", w.bits, w.canales); return;
  }
  vozParlante.setPins(VOZ_PIN_BCLK_SALIDA, VOZ_PIN_LRC_SALIDA, VOZ_PIN_DIN_SALIDA);
  if (!vozParlante.begin(I2S_MODE_STD, w.tasa, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO)) {
    Serial.println("ERROR: no pude iniciar el I2S del parlante."); return;
  }
  const int16_t* m = (const int16_t*)w.datos;
  const size_t cuadros = w.largo / (2 * w.canales);
  Serial.printf("Reproduciendo %.1f s (%lu Hz, %u canal, volumen %d%%)\n", (float)cuadros / w.tasa, (unsigned long)w.tasa, w.canales, (int)vozVolumenPct);
  static int16_t buf[256 * 2];                           // 256 cuadros estéreo
  for (size_t i = 0; i < cuadros; i += 256) {
    int pct = vozVolumenPct;                             // se puede cambiar con "vol N" mientras suena
    size_t k = min((size_t)256, cuadros - i);
    for (size_t j = 0; j < k; j++) {
      int32_t izq = m[(i + j) * w.canales];
      int32_t der = (w.canales == 2) ? m[(i + j) * 2 + 1] : izq;
      buf[2 * j]     = (int16_t)(izq * pct / 100);
      buf[2 * j + 1] = (int16_t)(der * pct / 100);
    }
    vozParlante.write((uint8_t*)buf, k * 4);
  }
  memset(buf, 0, sizeof(buf));                           // silencio final: evita el "pop" y que se corte la cola
  for (uint32_t t = 0; t < w.tasa / 5; t += 256) vozParlante.write((uint8_t*)buf, sizeof(buf));
  vozParlante.end();
}

// Anuncio de OTA por el parlante: tres beeps y «Actualizando en tres, dos, uno».
// Lo usan la OTA local (estado.h) y la del servidor (actualizar.h). Espera a que la voz esté libre,
// pausa la tarea mientras suena y deja la pausa como estaba (la OTA ya la mantiene pausada).
void anuncioOta() {
  if (!vozActiva) return;
  uint32_t t = millis();
  while ((vozEstado != VOZ_REPOSO || vozGrabando) && millis() - t < 10000) delay(100);
  if (vozEstado != VOZ_REPOSO || vozGrabando) {
    Serial.println("OTA: estaba ocupado; sigo sin anuncio.");
    return;
  }
  bool pausaPrevia = vozPausada;
  vozPausada = true;
  Serial.println("OTA: anuncio por el parlante.");
  vozReproducir((const uint8_t*)ANUNCIO_OTA_WAV, ANUNCIO_OTA_WAV_LEN);
  vozPausada = pausaPrevia;
}

// ---------- Red ----------

// ---------- HTTPS y hora ----------
// El certificado del servidor se verifica de verdad (nunca setInsecure): con las raíces que trae el core (Mozilla,
// incluida ISRG Root X1 de Let's Encrypt) y con la fecha, así que sin hora real no hay HTTPS: se sincroniza por NTP.

void vozPrepararCliente(NetworkClientSecure& c) { c.useBuiltinCACertBundle(); }
void vozPrepararCliente(WiFiClient&) {}                  // HTTP plano: nada que preparar

void vozDetalleTls(NetworkClientSecure& c) {
  char detalle[100] = "";
  int codigo = c.lastError(detalle, sizeof(detalle));
  if (codigo != 0) Serial.printf("  (TLS: %s, código %d)\n", detalle, codigo);
}
void vozDetalleTls(WiFiClient&) {}

void vozIniciarHora() {
#if VOZ_HTTPS
  configTzTime(VOZ_ZONA_HORARIA, "pool.ntp.org", "time.google.com", "time.cloudflare.com");
#endif
}

// true si se puede seguir (HTTP plano, o HTTPS con hora válida).
bool vozAsegurarHora() {
#if VOZ_HTTPS
  uint32_t t = millis();
  while (time(nullptr) < 1700000000 && millis() - t < 20000) delay(200);    // 1700000000 = nov-2023: cualquier hora real es posterior
  if (time(nullptr) < 1700000000) { Serial.println("Voz: sin hora de internet (NTP): no se puede verificar el certificado HTTPS."); vozFallo = VOZ_FALLO_HORA; return false; }
#endif
  return true;
}

String vozDecodificarUrl(const String& s) {              // %xx -> bytes (UTF-8), para imprimir legible
  String r; r.reserve(s.length());
  for (size_t i = 0; i < s.length(); i++) {
    if (s[i] == '%' && i + 2 < s.length() && isxdigit(s[i + 1]) && isxdigit(s[i + 2])) {
      r += (char)strtol(s.substring(i + 1, i + 3).c_str(), nullptr, 16); i += 2;
    } else if (s[i] == '+') r += ' ';
    else r += s[i];
  }
  return r;
}

// Envía el audio grabado a /voz y, cuando el PC termina, baja toda la respuesta y la toca.
// Devuelve cuando termina de sonar o falla. (Camino de respaldo si el servidor no tiene /voz/stream.)
void vozEnviarCompleto(uint32_t muestras) {
  uint32_t espera = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - espera < 5000) delay(100);   // el Wi-Fi se reconecta solo
  if (WiFi.status() != WL_CONNECTED) { Serial.println("Voz: no envío, sin Wi-Fi."); vozFallo = VOZ_FALLO_WIFI; return; }
  if (!vozAsegurarHora()) return;

  vozEscribirCabecera(muestras);
#if VOZ_HTTPS
  NetworkClientSecure cliente;
#else
  WiFiClient cliente;
#endif
  vozPrepararCliente(cliente);
  HTTPClient http;
  String url = String(VOZ_ESQUEMA) + cfgHost + ":" + cfgPuerto + "/voz";
  static const char* claves[] = {"X-Emocion", "X-Cuello", "X-Texto", "X-Respuesta", "X-Segundos", "X-Accion"};
  http.collectHeaders(claves, 6);
  http.setConnectTimeout(15000);                         // con HTTPS incluye el apretón de manos TLS
  http.setTimeout(60000);                                // el PC corre Whisper + modelo + voz: puede tardar
  http.begin(cliente, url);
  http.addHeader("Content-Type", "audio/wav");
  if (cfgToken[0]) http.addHeader("X-Token", cfgToken);   // el puente exige el mismo token a los equipos de la red
  uint32_t t = millis();
  int codigo = http.POST(vozWav, VOZ_LARGO_CABECERA + muestras * 2);
  if (codigo <= 0) { Serial.printf("Voz: POST %s falló: %s\n", url.c_str(), http.errorToString(codigo).c_str()); vozDetalleTls(cliente); vozFallo = VOZ_FALLO_SERVIDOR; http.end(); return; }

  int tam = http.getSize();
  Serial.printf("Voz: POST -> %d, respuesta %d bytes, %lu ms\n", codigo, tam, (unsigned long)(millis() - t));
  if (codigo != 200) { Serial.println(http.getString().substring(0, 200)); vozFallo = VOZ_FALLO_SERVIDOR; http.end(); return; }
  if (tam <= 0 || tam > VOZ_RESPUESTA_MAX_BYTES) {
    Serial.printf("Voz: respuesta con tamaño inválido o muy grande (%d bytes, máx %d): no se reproduce.\n", tam, VOZ_RESPUESTA_MAX_BYTES);
    http.end(); return;
  }

  String emocion = http.header("X-Emocion");
  String cuello = http.header("X-Cuello");
  if (http.header("X-Accion") == "buscar_actualizacion") vozAccionBuscar = true;
  Serial.printf("  emocion=%s cuello=%s servidor=%s s\n", emocion.c_str(), cuello.length() ? cuello.c_str() : "-", http.header("X-Segundos").c_str());
  Serial.printf("  te entendí: %s\n", vozDecodificarUrl(http.header("X-Texto")).c_str());
  Serial.printf("  respondo:   %s\n", vozDecodificarUrl(http.header("X-Respuesta")).c_str());

  WiFiClient* flujo = http.getStreamPtr();
  size_t leidos = 0;
  uint32_t ultimo = millis();
  while (http.connected() && leidos < (size_t)tam && millis() - ultimo < 15000) {
    size_t disp = flujo->available();
    if (disp) {
      leidos += flujo->readBytes(vozRespuesta + leidos, min(disp, (size_t)tam - leidos));
      ultimo = millis();
    } else delay(2);
  }
  http.end();
  if (leidos < (size_t)tam) { Serial.printf("Voz: se cortó la descarga: %u de %d bytes.\n", (unsigned)leidos, tam); vozRespuestaBytes = 0; return; }
  vozRespuestaBytes = leidos;
  Serial.printf("  descargado en %lu ms en total\n", (unsigned long)(millis() - t));

  // Primero la emoción y el cuello, y solo después el estado: loop() los lee al ver HABLANDO.
  strncpy(vozEmocion, emocion.length() ? emocion.c_str() : "neutral", sizeof(vozEmocion) - 1);
  vozEmocion[sizeof(vozEmocion) - 1] = 0;
  vozCuello = cuello.length() ? cuello.toInt() : -1;
  __sync_synchronize();
  vozEstado = VOZ_HABLANDO;
  vozReproducir(vozRespuesta, vozRespuestaBytes);
}

// ---------- Respuesta en streaming ----------
// POST /voz/stream: el PC contesta con un WAV "sin fin" que se va llenando frase por frase. Se pide en HTTP/1.0
// para que el cuerpo llegue sin "chunked" (termina cuando el servidor cierra). Aquí se toca lo que va llegando.

// Lee exactamente n bytes del flujo; false si se corta la conexión o pasa demasiado tiempo sin datos.
bool vozLeerN(WiFiClient* flujo, uint8_t* destino, size_t n, uint32_t esperaMs) {
  size_t leidos = 0;
  uint32_t ultimo = millis();
  while (leidos < n) {
    int disp = flujo->available();
    if (disp >= 1) {
      int r = flujo->read(destino + leidos, min((size_t)disp, n - leidos));
      if (r > 0) { leidos += (size_t)r; ultimo = millis(); }
    } else {
      if (!flujo->connected() || millis() - ultimo > esperaMs) return false;
      delay(2);
    }
  }
  return true;
}

// Lee la línea de estado y las cabeceras de la respuesta HTTP, byte a byte, para que el cuerpo empiece justo después
// de la línea en blanco (así no se pierde nada del audio que ya venga pegado). Guarda las que importan.
bool vozLeerCabeceras(WiFiClient* c, int& codigo, String& emocion, String& cuello, String& texto, uint32_t esperaMs) {
  String linea;
  linea.reserve(256);
  bool primera = true;
  codigo = 0;
  uint32_t ultimo = millis();
  for (;;) {
    if (c->available() >= 1) {
      int ch = c->read();
      if (ch < 0) continue;
      ultimo = millis();
      if (ch == '\n') {
        linea.trim();                                        // quita el \r
        if (primera) {                                       // "HTTP/1.0 200 OK"
          int sp = linea.indexOf(' ');
          codigo = (sp > 0) ? linea.substring(sp + 1, sp + 4).toInt() : 0;
          primera = false;
        } else if (linea.length() == 0) {
          return codigo > 0;                                 // fin de las cabeceras
        } else {
          int dp = linea.indexOf(':');
          if (dp > 0) {
            String k = linea.substring(0, dp); k.toLowerCase();
            String v = linea.substring(dp + 1); v.trim();
            if (k == "x-emocion") emocion = v;
            else if (k == "x-cuello") cuello = v;
            else if (k == "x-texto") texto = v;
            else if (k == "x-accion" && v == "buscar_actualizacion") vozAccionBuscar = true;
          }
        }
        linea = "";
      } else if (linea.length() < 1500) {                    // X-Texto codificado con %xx puede ser largo
        linea += (char)ch;
      }
    } else {
      if (!c->connected() || millis() - ultimo > esperaMs) return false;
      delay(2);
    }
  }
}

// ---------- Conexión anticipada ----------
// El apretón de manos TLS cuesta ~2 s en el ESP32 (verificar la cadena de certificados). En vez de pagarlo después de soltar
// el sensor, se hace MIENTRAS el niño habla: pasados 350 ms de toque (para ignorar roces) una tarea abre la conexión y la deja
// lista. Al soltar, el audio sale por esa conexión. (HTTPClient cierra la conexión ya abierta al hacer begin() con un objeto
// nuevo y negocia otra vez: por eso la petición se escribe a mano.)
#if VOZ_HTTPS
typedef NetworkClientSecure VozCliente;
#else
typedef WiFiClient VozCliente;
#endif

VozCliente* vozConexion = nullptr;
volatile uint8_t vozConexionEstado = 0;          // 0 nada, 1 conectando, 2 lista, 3 falló
volatile bool vozConexionDescartar = false;      // se soltó el sensor antes de tiempo: cerrar al terminar de conectar
uint32_t vozConexionHora = 0;                    // cuándo quedó lista (millis)
bool vozPreconIntentada = false;                 // una sola vez por toque

void vozTareaPreconectar(void*) {
  VozCliente* c = new VozCliente();
  vozPrepararCliente(*c);
  uint32_t t = millis();
  bool ok = c->connect(cfgHost, (uint16_t)atoi(cfgPuerto));
  uint32_t ms = millis() - t;
  if (ok && !vozConexionDescartar) {
    vozConexion = c;
    vozConexionHora = millis();
    __sync_synchronize();
    vozConexionEstado = 2;
    Serial.printf("Voz: conexión %s lista en %lu ms (mientras se habla)\n", VOZ_HTTPS ? "TLS" : "TCP", (unsigned long)ms);
  } else {
    if (!ok) { Serial.printf("Voz: la conexión anticipada falló tras %lu ms\n", (unsigned long)ms); vozDetalleTls(*c); }
    c->stop();
    delete c;
    vozConexionDescartar = false;
    vozConexionEstado = ok ? 0 : 3;
  }
  vTaskDelete(nullptr);
}

void vozPreconectar() {
  if (vozConexionEstado == 2 && millis() - vozConexionHora > 20000) {            // quedó vieja: se cierra y se hace otra
    delete vozConexion; vozConexion = nullptr; vozConexionEstado = 0;
  }
  if (vozConexionEstado != 0 && vozConexionEstado != 3) return;                  // ya hay una en curso o lista
  if (WiFi.status() != WL_CONNECTED) return;
#if VOZ_HTTPS
  if (time(nullptr) < 1700000000) return;                                        // sin hora no se puede verificar el certificado
#endif
  vozConexionEstado = 1;
  vozConexionDescartar = false;
  xTaskCreatePinnedToCore(vozTareaPreconectar, "vozconn", 16384, nullptr, 1, nullptr, 0);
}

// La grabación no se va a enviar (toque corto, sin audio útil): se cierra la conexión anticipada.
void vozSoltarConexion() {
  if (vozConexionEstado == 2) { delete vozConexion; vozConexion = nullptr; vozConexionEstado = 0; }
  else if (vozConexionEstado == 1) vozConexionDescartar = true;
  else if (vozConexionEstado == 3) vozConexionEstado = 0;
}

// Descarga de la respuesta en streaming, en una tarea aparte. Leer solo lo que se reproduce (~48 KB/s exactos) dejaba la
// ventana TCP casi cerrada y SIN colchón: con el Wi-Fi y TLS por internet, cualquier retraso era un corte. Esta tarea
// vacía el socket lo más rápido posible hacia el búfer de PSRAM y el reproductor consume desde ahí, así el audio va por
// delante de lo que suena. Con TLS available() cuenta solo lo que queda del registro cifrado actual (puede ser 1 byte),
// por eso se lee con >= 1 y no se exige un número par: la alineación de muestras la cuida el reproductor.
struct VozDescarga {
  WiFiClient* flujo;
  uint8_t* destino;
  size_t capacidad;
  volatile size_t escritos;      // bytes de PCM ya en el búfer (lo escribe la tarea, lo lee el reproductor)
  volatile bool terminado;
  volatile bool fallo;
};

void vozTareaDescarga(void* arg) {
  VozDescarga* d = (VozDescarga*)arg;
  uint32_t sinDatos = millis();
  for (;;) {
    int disp = d->flujo->available();
    if (disp >= 1) {
      size_t libre = d->capacidad - d->escritos;
      if (libre == 0) break;                                     // búfer lleno (>40 s de audio): se corta aquí
      int r = d->flujo->read(d->destino + d->escritos, min((size_t)disp, libre));
      if (r > 0) { __sync_synchronize(); d->escritos = d->escritos + (size_t)r; sinDatos = millis(); }
    } else if (d->flujo->connected() || d->flujo->available()) {
      if (millis() - sinDatos > 20000) { d->fallo = true; break; }
      vTaskDelay(1);
    } else break;                                                // el servidor cerró: terminó la respuesta
  }
  __sync_synchronize();
  d->terminado = true;                                           // lo último que toca: después el reproductor puede liberar "d"
  vTaskDelete(nullptr);
}

// true = el servidor atendió el pedido (aunque haya fallado después); false = no tiene /voz/stream (se usa /voz).
bool vozEnviarStream(uint32_t muestras) {
  uint32_t espera = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - espera < 5000) delay(100);
  if (WiFi.status() != WL_CONNECTED) { Serial.println("Voz: no envío, sin Wi-Fi."); vozFallo = VOZ_FALLO_WIFI; return true; }
  if (!vozAsegurarHora()) return true;

  vozEscribirCabecera(muestras);

  // Conexión: la anticipada (abierta mientras se hablaba) o, si no está, se abre ahora.
  uint32_t tConexion = millis();
  while (vozConexionEstado == 1 && millis() - tConexion < 20000) delay(10);      // aún conectando: se espera
  VozCliente* cliente = nullptr;
  if (vozConexionEstado == 2 && vozConexion && vozConexion->connected()) {
    cliente = vozConexion; vozConexion = nullptr; vozConexionEstado = 0;
    Serial.printf("  conexión anticipada lista (esperé %lu ms)\n", (unsigned long)(millis() - tConexion));
  } else {
    if (vozConexionEstado == 2) { delete vozConexion; vozConexion = nullptr; }   // se cayó mientras esperaba
    vozConexionEstado = 0;
    cliente = new VozCliente();
    vozPrepararCliente(*cliente);
    bool ok = cliente->connect(cfgHost, (uint16_t)atoi(cfgPuerto));
    Serial.printf("  %s con %s en %lu ms (%s)\n", VOZ_HTTPS ? "TLS" : "TCP", cfgHost, (unsigned long)(millis() - tConexion), ok ? "ok" : "FALLÓ");
    if (!ok) { vozDetalleTls(*cliente); vozFallo = VOZ_FALLO_SERVIDOR; delete cliente; return true; }
  }

  // Petición HTTP/1.0 escrita a mano sobre esa conexión (sin "chunked": el cuerpo termina cuando el servidor cierra).
  uint32_t t = millis();
  String peticion = String("POST /voz/stream HTTP/1.0\r\nHost: ") + cfgHost + "\r\nContent-Type: audio/wav\r\nContent-Length: " +
                    String((unsigned long)(VOZ_LARGO_CABECERA + muestras * 2)) + "\r\n";
  if (cfgToken[0]) peticion += String("X-Token: ") + cfgToken + "\r\n";
  peticion += "\r\n";
  cliente->write((const uint8_t*)peticion.c_str(), peticion.length());
  const uint8_t* p = vozWav;
  size_t restante = VOZ_LARGO_CABECERA + muestras * 2;
  uint32_t ultimoEnvio = millis();
  while (restante > 0) {
    size_t n = min(restante, (size_t)4096);
    size_t w = cliente->write(p, n);
    if (w == 0) {
      if (!cliente->connected() || millis() - ultimoEnvio > 15000) { Serial.println("Voz: falló el envío del audio."); vozFallo = VOZ_FALLO_SERVIDOR; cliente->stop(); delete cliente; return true; }
      delay(5); continue;
    }
    p += w; restante -= w; ultimoEnvio = millis();
  }
  Serial.printf("  audio enviado en %lu ms\n", (unsigned long)(millis() - t));

  int codigo = 0;
  String emocion, cuello, textoUrl;
  if (!vozLeerCabeceras(cliente, codigo, emocion, cuello, textoUrl, 60000)) {      // Whisper + modelo antes de las cabeceras
    Serial.println("Voz: no llegaron las cabeceras de la respuesta."); vozDetalleTls(*cliente); vozFallo = VOZ_FALLO_SERVIDOR; cliente->stop(); delete cliente; return true;
  }
  if (codigo == 404) { cliente->stop(); delete cliente; return false; }            // servidor sin streaming
  Serial.printf("Voz: POST /voz/stream -> %d, cabeceras a los %lu ms\n", codigo, (unsigned long)(millis() - t));
  if (codigo != 200) { vozFallo = VOZ_FALLO_SERVIDOR; cliente->stop(); delete cliente; return true; }
  Serial.printf("  emocion=%s cuello=%s\n", emocion.c_str(), cuello.length() ? cuello.c_str() : "-");
  Serial.printf("  te entendí: %s\n", vozDecodificarUrl(textoUrl).c_str());

  WiFiClient* flujo = cliente;
  uint8_t cab[VOZ_LARGO_CABECERA];
  if (!vozLeerN(flujo, cab, VOZ_LARGO_CABECERA, 25000)) {
    Serial.println("Voz: el PC no mandó audio a tiempo."); vozFallo = VOZ_FALLO_SERVIDOR; cliente->stop(); delete cliente; return true;
  }
  uint32_t tasa; uint16_t formato, canales, bits;
  memcpy(&formato, cab + 20, 2); memcpy(&canales, cab + 22, 2); memcpy(&tasa, cab + 24, 4); memcpy(&bits, cab + 34, 2);
  if (memcmp(cab, "RIFF", 4) || memcmp(cab + 8, "WAVE", 4) || memcmp(cab + 36, "data", 4) || formato != 1 || canales != 1 || bits != 16) {
    Serial.println("Voz: la respuesta en streaming no es un WAV PCM 16 bits mono."); cliente->stop(); delete cliente; return true;
  }

  vozParlante.setPins(VOZ_PIN_BCLK_SALIDA, VOZ_PIN_LRC_SALIDA, VOZ_PIN_DIN_SALIDA);
  if (!vozParlante.begin(I2S_MODE_STD, tasa, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO)) {
    Serial.println("ERROR: no pude iniciar el I2S del parlante."); cliente->stop(); delete cliente; return true;
  }
  // Primero la emoción y el cuello (loop() los lee al ver HABLANDO, que se pone cuando empieza a sonar de verdad).
  strncpy(vozEmocion, emocion.length() ? emocion.c_str() : "neutral", sizeof(vozEmocion) - 1);
  vozEmocion[sizeof(vozEmocion) - 1] = 0;
  vozCuello = cuello.length() ? cuello.toInt() : -1;

  // La descarga va a vozRespuesta (cabecera WAV + PCM), que además queda para "repetir".
  memcpy(vozRespuesta, cab, VOZ_LARGO_CABECERA);
  VozDescarga d;
  d.flujo = flujo;
  d.destino = vozRespuesta + VOZ_LARGO_CABECERA;
  d.capacidad = VOZ_RESPUESTA_MAX_BYTES - VOZ_LARGO_CABECERA;
  d.escritos = 0; d.terminado = false; d.fallo = false;
  xTaskCreatePinnedToCore(vozTareaDescarga, "vozdesc", 12288, &d, 2, nullptr, 0);

  // Colchón: no se empieza a sonar hasta tener un poco de audio por delante (o hasta que termine la respuesta, si es corta).
  const size_t precarga = (size_t)tasa * 2 * VOZ_PRECARGA_MS / 1000;
  uint32_t tPrecarga = millis();
  while (!d.terminado && d.escritos < precarga && millis() - tPrecarga < 15000) delay(5);

  __sync_synchronize();
  vozEstado = VOZ_HABLANDO;
  Serial.printf("  suena el primer audio a los %lu ms (%lu Hz; colchón de %u bytes llenado en %lu ms)\n",
                (unsigned long)(millis() - t), (unsigned long)tasa, (unsigned)d.escritos, (unsigned long)(millis() - tPrecarga));

  static int16_t estereo[1024 * 2];
  static int16_t silencio[2 * 240];                      // 240 cuadros: ~10 ms a 24 kHz
  memset(silencio, 0, sizeof(silencio));
  size_t pos = 0;                                        // bytes de PCM ya reproducidos
  uint32_t huecos = 0;
  for (;;) {
    bool fin = d.terminado;                              // se lee ANTES de contar: si es true, "escritos" ya es el definitivo
    size_t hay = (d.escritos - pos) & ~(size_t)1;        // solo muestras completas (2 bytes)
    if (hay >= 2048 || (fin && hay >= 2)) {
      size_t n = min(hay, (size_t)2048);
      const int16_t* m = (const int16_t*)(d.destino + pos);
      int pct = vozVolumenPct;                           // se puede cambiar con "vol N" mientras suena
      size_t muestrasN = n / 2;
      for (size_t i = 0; i < muestrasN; i++) {
        int16_t v = (int16_t)((int32_t)m[i] * pct / 100);
        estereo[2 * i] = v; estereo[2 * i + 1] = v;
      }
      vozParlante.write((uint8_t*)estereo, muestrasN * 4);
      pos += n;
    } else if (fin) {
      break;                                             // todo descargado y reproducido
    } else {
      vozParlante.write((uint8_t*)silencio, sizeof(silencio));   // el audio aún no llega: silencio, no repetir lo último
      huecos++;
    }
  }
  if (d.fallo) Serial.println("Voz: el PC dejó de mandar audio.");
  for (int k = 0; k < 20; k++) vozParlante.write((uint8_t*)silencio, sizeof(silencio));   // cola de silencio: evita el "pop"
  vozParlante.end();
  cliente->stop();
  delete cliente;

  // Cabecera con los tamaños reales, para que "repetir" use el camino de siempre.
  uint32_t datos = (uint32_t)d.escritos & ~1u, riff = 36 + datos;
  memcpy(vozRespuesta + 4, &riff, 4); memcpy(vozRespuesta + 40, &datos, 4);
  vozRespuestaBytes = VOZ_LARGO_CABECERA + datos;
  Serial.printf("  reproducido: %.1f s de audio, %lu pausas de 10 ms esperando al PC, total %lu ms\n",
                (float)pos / (tasa * 2), (unsigned long)huecos, (unsigned long)(millis() - t));
  return true;
}

// Punto de entrada: streaming si está activado y el servidor lo tiene; si no, el camino de siempre.
void vozEnviar(uint32_t muestras) {
#if VOZ_STREAMING
  if (vozEnviarStream(muestras)) return;
  Serial.println("Voz: el servidor no tiene /voz/stream; uso /voz.");
#endif
  vozEnviarCompleto(muestras);
}

// ---------- Grabación ----------

void vozEmpezarGrabacion(uint32_t t0, bool automatica = false) {
  vozGrabando = true; vozAutoGrabando = automatica; vozInicioToque = t0; vozEscritas = 0; vozVistas = 0; vozLlenoAvisado = false;
  vozPreconIntentada = false;
  vozEstado = VOZ_ESCUCHANDO;
  Serial.println(automatica ? "Voz: te oigo, grabando..." : "Voz: 1  tocado, grabando...");
}

void vozTerminarGrabacion(uint32_t t1) {
  vozGrabando = false;
  bool eraAuto = vozAutoGrabando;
  vozAutoGrabando = false;
  uint32_t dur = t1 - vozInicioToque;
  if (dur < VOZ_MS_TOQUE_MIN) {
    vozToquesCortos++;
    if (eraAuto) vozTurnos = 0;
    Serial.printf("Voz: 0  suelto (duro %lu ms): muy corto, se ignora\n", (unsigned long)dur);
    vozSoltarConexion();
    vozEstado = VOZ_REPOSO; return;
  }
  uint32_t muestras = vozEscritas > VOZ_MUESTRAS_FINAL ? vozEscritas - VOZ_MUESTRAS_FINAL : 0;   // quita el golpe de soltar
  Serial.printf("Voz: 0  %s (duro %lu ms): %lu muestras utiles = %.2f s\n", eraAuto ? "silencio" : "suelto", (unsigned long)dur, (unsigned long)muestras, (float)muestras / VOZ_FS);
  if (muestras < VOZ_FS / 4) { Serial.println("Voz: menos de 0,25 s de audio util: no se envia."); if (eraAuto) vozTurnos = 0; vozSoltarConexion(); vozEstado = VOZ_REPOSO; return; }
  int32_t pico = 0; double suma = 0;
  for (uint32_t i = 0; i < muestras; i++) { int32_t v = abs((int32_t)vozAudio[i]); if (v > pico) pico = v; suma += (double)v * v; }
  Serial.printf("Voz: nivel pico %ld de 32767, RMS %.0f\n", (long)pico, sqrt(suma / muestras));
  int32_t pisoMin = max((int32_t)VOZ_PICO_MIN, (int32_t)(vozPiso * 1.5f));
  if (pico < pisoMin) {                            // un toque falso del TTP223 no manda audio (ni gasta una vuelta al servidor)
    vozToquesSinVoz++;
    if (eraAuto) vozTurnos = 0;
    Serial.println("Voz: no se oye voz (posible toque falso): no se envía.");
    vozSoltarConexion(); vozEstado = VOZ_REPOSO; return;
  }
  vozUltimoToqueMs = dur;

  vozEstado = VOZ_PENSANDO;
  vozEnviar(muestras);
  vozEstado = VOZ_REPOSO;
  // Mientras hablaba el parlante no se miró el toque: se vuelve a leer para no arrancar una grabación fantasma.
  vozLeido = vozEstable = digitalRead(VOZ_PIN_TACTO);
  vozCambioCrudo = millis();
  if (eraAuto && vozTurnos < 255) vozTurnos++;
  vozAbrirVentana();
}

// ---------- Tarea ----------

// Campos del TTP223 y la voz en /estado (los usa rutaEstado en robot_rostro.ino).
void vozAgregarEstado(JsonDocument& doc) {
  doc["voz_armado"] = vozArmado;                       // false = aún no acepta toques (o el sensor está pegado)
  doc["voz_linea"] = digitalRead(VOZ_PIN_TACTO);       // 1 = el sensor dice "tocado" en este momento
  doc["voz_estado"] = vozEstado;                       // 0 reposo, 1 escuchando, 2 pensando, 3 hablando, 4 esperando respuesta
  doc["toque_cortos"] = vozToquesCortos;               // pulsos < 400 ms ignorados (ruido del TTP223)
  doc["toque_sin_voz"] = vozToquesSinVoz;              // grabaciones sin voz descartadas
  doc["toque_ultimo_ms"] = vozUltimoToqueMs;           // duración del último toque aceptado
  doc["voz_conv"] = vozConversacion;                   // espera unos segundos a que contesten sin tocar
  doc["voz_turnos"] = vozTurnos;                       // turnos seguidos sin tocar
  doc["voz_piso"] = (int)vozPiso;                      // ruido de fondo (para calibrar el umbral de voz)
  doc["voz_ventanas"] = vozVentanas;                   // ventanas conversacionales abiertas
  doc["voz_autos"] = vozAutos;                         // veces que el micrófono disparó solo
  doc["voz_max_pico"] = (int)vozMaxPico;               // lo más fuerte de la última ventana
  doc["voz_win_it"] = vozWinIt;                        // veces que se evaluó la última ventana
  doc["voz_disparo_ms"] = vozDisparoMs;                // ms entre el fin de la guarda y el disparo (si es ~0 se oye algo constante)
  doc["voz_disparo_pico"] = vozDisparoPico;
  doc["voz_win_fin"] = vozWinFin;                      // cómo acabó: 0 interrumpida, 1 tiempo, 2 voz
  doc["voz_max_umbral"] = min((int)vozMaxUmbral, (int)VOZ_UMBRAL_TECHO);           // umbral que tenía esa ventana
}

void tareaVoz(void*) {
  static int32_t crudo[256];
  bool respDentro = false, respPulsado = false, respIgnorar = false;
  uint32_t respDesde = 0;
  for (;;) {
    if (vozPausada) { vozEsperando = false; vozAutoGrabando = false; vozEstado = VOZ_REPOSO; vTaskDelay(pdMS_TO_TICKS(50)); micAlPresente(); continue; }    // actualización OTA en curso

    // Modo respuesta: el toque no graba; se mide si fue corto o mantenido y se avisa con vozToqueEvento.
    if (vozModoRespuesta) {
      bool l = digitalRead(VOZ_PIN_TACTO);
      if (!respDentro) { respDentro = true; respPulsado = false; respIgnorar = l; }   // si ya estaba tocado, se espera a que suelte
      if (respIgnorar) { if (!l) respIgnorar = false; }
      else if (l && !respPulsado) { respPulsado = true; respDesde = millis(); }
      else if (respPulsado && l && millis() - respDesde >= 1000 && vozToqueEvento == TOQUE_NADA) vozToqueEvento = TOQUE_LARGO;
      else if (respPulsado && !l) {
        if (millis() - respDesde >= 80 && vozToqueEvento == TOQUE_NADA) vozToqueEvento = TOQUE_CORTO;   // menos de 80 ms = roce
        respPulsado = false;
      }
      vTaskDelay(pdMS_TO_TICKS(10));
      micAlPresente();
      continue;
    }
    if (respDentro) { respDentro = false; vozLeido = vozEstable = digitalRead(VOZ_PIN_TACTO); vozCambioCrudo = millis(); }   // no confundir el toque de la respuesta con una grabación
    // El micrófono lo lee su propia tarea (microfono.h); aquí se consume del anillo: 24 bits, ya sin la deriva lenta.
    size_t n = micLeer(crudo, 256, 30);
    // Pico de este bloque en la escala de la grabación: para el modo conversación y el suelo de ruido.
    int32_t picoBloque = 0;
    for (size_t i = 0; i < n; i++) { int32_t v = abs(crudo[i] >> VOZ_DESPLAZAR); if (v > picoBloque) picoBloque = v; }
    if (!vozGrabando && n) {
      float p = (float)picoBloque;
      if (p < vozPiso) vozPiso = vozPiso * VOZ_PISO_ALPHA + p * (1.0f - VOZ_PISO_ALPHA);        // baja rápido
      else vozPiso = vozPiso * VOZ_PISO_SUBE + p * (1.0f - VOZ_PISO_SUBE);                      // sube muy lento
      if (vozPiso < 100.0f) vozPiso = 100.0f;
      if (vozPiso > VOZ_PISO_MAX) vozPiso = VOZ_PISO_MAX;
    }

    if (vozPidioRepetir) {
      vozPidioRepetir = false;
      vozEsperando = false;
      if (vozRespuestaBytes) { vozEstado = VOZ_HABLANDO; vozReproducir(vozRespuesta, vozRespuestaBytes); vozEstado = VOZ_REPOSO; }
      else Serial.println("Voz: aún no hay respuesta guardada.");
      micAlPresente();                                   // lo que se oyó mientras hablaba no se procesa
      continue;
    }

    uint32_t ahora = millis();
    bool lectura = digitalRead(VOZ_PIN_TACTO);
    if (lectura != vozLeido) { vozLeido = lectura; vozCambioCrudo = ahora; }
    // El TTP223 puede arrancar disparado (se vio ~20 s en ESCUCHANDO): hasta pasar 3 s y verlo en reposo
    // no se acepta ningún toque, así un falso toque al arrancar no graba ni manda audio.
    if (!vozArmado) {
      if (ahora >= VOZ_MS_ARMAR && !lectura) {
        vozArmado = true; vozEstable = false; vozLeido = false; vozCambioCrudo = ahora;
        Serial.printf("Voz: toque armado a los %.1f s\n", ahora / 1000.0f);
      }
    } else if (vozLeido != vozEstable && ahora - vozCambioCrudo >= VOZ_MS_ANTIRREBOTE) {
      vozEstable = vozLeido;
      if (vozEsperando || vozAutoGrabando) {
        // El TTP223 se dispara solo (~6 pulsos/s): durante la ventana y la grabación automática manda el micrófono.
        // Si no, un pulso de ruido cerraba la ventana (o cortaba la frase) antes de que el niño contestara.
      } else if (vozEstable) {
        vozTurnos = 0;
        vozEmpezarGrabacion(vozCambioCrudo);
      } else if (vozGrabando) { vozTerminarGrabacion(vozCambioCrudo); micAlPresente(); }   // tras enviar y hablar, se salta al presente
    }

    // Ventana conversacional: si el niño habla sin tocar, se graba solo (con 400 ms de audio previo).
    if (vozEsperando && !vozGrabando) {
     if ((int32_t)(millis() - vozVentanaDesde) < 0) {
      micAlPresente(); vozVozBloques = 0;                // guarda: se descarta lo que se oye (eco del propio parlante)
     } else {
      int32_t umbral = max((int32_t)VOZ_VAD_MIN, (int32_t)(vozPiso * VOZ_VAD_FACTOR));
      vozWinIt = vozWinIt + 1;
      if (picoBloque > vozMaxPico) vozMaxPico = picoBloque;
      if (umbral > vozMaxUmbral) vozMaxUmbral = umbral;
      if (n && picoBloque > umbral) { if (vozVozBloques < 10) vozVozBloques++; }
      else if (vozVozBloques < VOZ_VAD_BLOQUES) vozVozBloques = 0;
      if (vozVozBloques >= VOZ_VAD_BLOQUES) {
        vozEsperando = false; vozVozBloques = 0; vozAutos++; vozWinFin = 2;
        vozDisparoMs = millis() - vozVentanaDesde; vozDisparoPico = picoBloque;
        Serial.printf("Voz: te oigo (pico %ld > umbral %ld), grabando sin tocar\n", (long)picoBloque, (long)umbral);
        vozEmpezarGrabacion(millis() - VOZ_PREVIO_MS, true);
        uint32_t hasta = mic.leido > n ? mic.leido - n : 0;            // lo anterior a este bloque
        vozEscritas = micCopiarHasta(vozAudio, hasta, (uint32_t)VOZ_FS * VOZ_PREVIO_MS / 1000, VOZ_DESPLAZAR);
        vozVistas = VOZ_MUESTRAS_INICIO;                               // el pre-roll ya empieza donde toca
        vozUltimaVoz = millis();
      } else if ((int32_t)(millis() - vozVentanaDesde) >= (int32_t)VOZ_MS_ESPERA) {
        // millis() fresco y resta con signo: "ahora" es de al inicio de la vuelta y, si en esta misma vuelta se envió y se habló
        // (unos 12 s), queda ATRÁS de vozVentanaDesde; sin signo daba un número enorme y la ventana se cerraba al instante.
        Serial.printf("Voz: nadie contestó (pico máx %ld, umbral %ld); vuelvo al reposo.\n", (long)vozMaxPico, (long)vozMaxUmbral);
        vozEsperando = false; vozTurnos = 0; vozEstado = VOZ_REPOSO; micAlPresente(); vozWinFin = 1;
      }
     }
    }

    // Pasados 350 ms de toque (no fue un roce) se abre la conexión TLS mientras el niño sigue hablando.
    if (vozGrabando && !vozPreconIntentada && ahora - vozInicioToque > 350) {
      vozPreconIntentada = true;
      vozPreconectar();
    }

    if (vozGrabando) {
      for (size_t i = 0; i < n; i++) {
        if (vozVistas++ < VOZ_MUESTRAS_INICIO) continue;            // descarta el golpe del toque
        if (vozEscritas >= VOZ_MUESTRAS_MAX) {
          if (!vozLlenoAvisado) { vozLlenoAvisado = true; Serial.println("Voz: lleno (10 s), suelta para enviar."); }
          break;
        }
        int32_t v = crudo[i] >> VOZ_DESPLAZAR;                      // 24 bits -> 16 bits con ganancia
        vozAudio[vozEscritas++] = (int16_t)constrain(v, -32768, 32767);
      }
      // Fin automático de una frase abierta por la ventana: silencio o tope de 10 s.
      if (vozAutoGrabando) {
        // El mismo umbral que para empezar: si el ruido lo supera seguido, la frase no se cerraría nunca.
        int32_t finUmbral = max((int32_t)VOZ_VAD_MIN, (int32_t)(vozPiso * VOZ_VAD_FACTOR));
        if (n && picoBloque > finUmbral) vozUltimaVoz = ahora;
        if (vozEscritas >= VOZ_MUESTRAS_MAX || ((int32_t)(ahora - vozUltimaVoz) >= (int32_t)VOZ_FIN_SILENCIO && vozEscritas > VOZ_FS / 2)) {
          vozTerminarGrabacion(ahora);
          micAlPresente();
        }
      }
    }
  }
}

// Se llama una vez desde setup(). Si falta algo (PSRAM, I2S), la voz queda apagada y el resto del robot sigue igual.
void iniciarVoz() {
  if (!redesHay()) { Serial.println("Voz: apagada (no hay redes Wi-Fi guardadas)."); return; }
  if (!psramFound()) { Serial.println("Voz: apagada (no hay PSRAM; la placa necesita PSRAM = OPI PSRAM)."); return; }
  vozWav = (uint8_t*)ps_malloc(VOZ_LARGO_CABECERA + VOZ_MUESTRAS_MAX * 2);
  vozRespuesta = (uint8_t*)ps_malloc(VOZ_RESPUESTA_MAX_BYTES);
  if (!vozWav || !vozRespuesta) { Serial.println("Voz: apagada (no pude reservar la memoria de audio)."); return; }
  vozAudio = (int16_t*)(vozWav + VOZ_LARGO_CABECERA);

  pinMode(VOZ_PIN_TACTO, INPUT);
  vozLeido = vozEstable = digitalRead(VOZ_PIN_TACTO);
  vozMicrofono.setPins(VOZ_PIN_SCK, VOZ_PIN_WS, -1, VOZ_PIN_SD);
  if (!vozMicrofono.begin(I2S_MODE_STD, VOZ_FS, I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_MONO, I2S_STD_SLOT_LEFT)) {
    Serial.println("Voz: apagada (no pude iniciar el I2S del micrófono)."); return;
  }
  if (!micIniciar(&vozMicrofono)) { Serial.println("Voz: apagada (no pude reservar el anillo del micrófono)."); return; }
  vozActiva = true;
  WiFi.setSleep(false);                                 // sin ahorro de energía del Wi-Fi: cada ida y vuelta sumaba 100-300 ms (TLS, subida y descarga)
  vozIniciarHora();                                      // NTP en segundo plano (solo con HTTPS); la tarea lo espera antes del primer envío
  xTaskCreatePinnedToCore(tareaVoz, "voz", VOZ_STACK_TAREA, nullptr, 1, nullptr, 0);
  Serial.printf("Voz: lista. Mantén tocado el sensor para hablar (>= %d ms, máx %d s). Volumen %d%%. Servidor %s%s:%s. PSRAM libre %u KB\n",
                VOZ_MS_TOQUE_MIN, VOZ_SEG_MAX, (int)vozVolumenPct, VOZ_ESQUEMA, cfgHost, cfgPuerto, (unsigned)(ESP.getFreePsram() / 1024));
}
