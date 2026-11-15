/*
  microfono.h — captura del micrófono (INMP441) sin perder audio.

  Antes, la misma tarea de voz (prioridad 1, núcleo 0) leía el I2S y además grababa, corría el detector y enviaba por la red.
  El controlador I2S solo guarda 90 ms (6 x 240 muestras): cualquier pausa mayor (TLS de otra tarea, Wi-Fi, un modelo) perdía audio.
  Medido el 14-nov: entre el 10 % y el 90 % de las muestras se perdían según lo que hiciera la placa.

  Ahora una tarea propia, de prioridad alta y que no hace nada más, lee el I2S y deja las muestras en un anillo en PSRAM (~8 s).
  La tarea de voz consume de ahí con micLeer(). Mientras lee, se quita lo que está por debajo de ~100 Hz (filtro pasa-altos):
  el micrófono trae una deriva lenta (0,5-3 Hz) varias veces más grande que la voz, que obligaba a bajar la ganancia.

  Las muestras del anillo están en escala de 24 bits (lo que entrega el INMP441), ya filtradas. Quien las usa elige la ganancia
  con un desplazamiento: >> 8 es ganancia 1 a 16 bits, >> 5 es x8.

  Para comprobar que no se pierde nada (GET /estado, con token), desde la lectura anterior de /estado:
    mic_hz           muestras por segundo recibidas (debe ser ~16000)
    mic_huecos       veces que entre dos lecturas del I2S pasaron más de 80 ms (cada una es audio perdido)
    mic_hueco_ms     la pausa más larga entre dos lecturas
    mic_desbordes    veces que la tarea de voz se atrasó más que el anillo entero (no debería pasar)
  GET /mic/audio (con token): los últimos ~8 s como WAV de 16 kHz. Solo existe en RAM; no se envía a ningún sitio por sí solo.
  Para quitar esa ruta: MIC_AUDIO_HTTP 0.
*/
#pragma once

#include <ESP_I2S.h>
#include <esp_timer.h>

#define MIC_FS 16000
#define MIC_ANILLO_MUESTRAS 131072u        // potencia de 2 (8,19 s; 512 KB de PSRAM): el índice es total & (N - 1)
#define MIC_BLOQUE 256                     // muestras por lectura del I2S (16 ms)
#define MIC_PRIORIDAD 10                   // por encima de voz, agenda y actualización (1-2); por debajo del Wi-Fi (>= 18)
#define MIC_NUCLEO 1                       // lejos del Wi-Fi y del TLS, que viven en el núcleo 0
#define MIC_CORTE_HZ 100.0f                // pasa-altos: quita la deriva lenta y el zumbido de red
#define MIC_HUECO_MS 80                    // pausa entre lecturas que ya implica pérdida (el I2S guarda 90 ms)
#ifndef MIC_AUDIO_HTTP
#define MIC_AUDIO_HTTP 0           // 1 = expone GET /mic/audio (con token): audio del micrófono por la red; solo para depurar
#endif

struct MicEstado {
  I2SClass* i2s = nullptr;
  int32_t* anillo = nullptr;
  volatile uint32_t total = 0;             // muestras escritas desde el arranque (da la vuelta sin problema: N es potencia de 2)
  uint32_t leido = 0;                      // hasta dónde consumió la tarea de voz (solo ella lo toca)
  SemaphoreHandle_t aviso = nullptr;       // se da cada vez que llegan muestras: despierta a quien espera en micLeer()
  bool lista = false;
  // estadísticas (las escribe la tarea de captura; /estado las lee y reinicia)
  volatile uint32_t muestrasVentana = 0;
  volatile int64_t inicioVentanaUs = 0;
  volatile uint32_t huecos = 0, huecoMaxMs = 0, desbordes = 0;
} mic;

void tareaMicrofono(void*) {
  static int32_t bloque[MIC_BLOQUE];
  // Butterworth de 2.º orden, pasa-altos. Estado en float: la FPU de la S3 es de precisión simple.
  const float w = 2.0f * PI * MIC_CORTE_HZ / MIC_FS, c = cosf(w), al = sinf(w) / (2.0f * 0.70710678f), a0 = 1.0f + al;
  const float b0 = (1.0f + c) / 2.0f / a0, b1 = -(1.0f + c) / a0, b2 = b0, a1 = -2.0f * c / a0, a2 = (1.0f - al) / a0;
  float x1 = 0, x2 = 0, y1 = 0, y2 = 0;
  int64_t anterior = esp_timer_get_time();
  mic.inicioVentanaUs = anterior;
  for (;;) {
    size_t n = mic.i2s->readBytes((char*)bloque, sizeof(bloque)) / sizeof(int32_t);
    int64_t ahora = esp_timer_get_time();
    uint32_t pausaMs = (uint32_t)((ahora - anterior) / 1000);
    anterior = ahora;
    if (pausaMs > MIC_HUECO_MS) { mic.huecos = mic.huecos + 1; }
    if (pausaMs > mic.huecoMaxMs) mic.huecoMaxMs = pausaMs;
    if (!n) { vTaskDelay(1); continue; }
    uint32_t t = mic.total;
    for (size_t i = 0; i < n; i++) {
      float x = (float)(bloque[i] >> 8);                               // 32 bits -> 24 bits
      float y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
      x2 = x1; x1 = x; y2 = y1; y1 = y;
      mic.anillo[(t + i) & (MIC_ANILLO_MUESTRAS - 1)] = (int32_t)y;
    }
    __sync_synchronize();
    mic.total = t + n;                                                 // se publica después de escribir las muestras
    mic.muestrasVentana = mic.muestrasVentana + n;
    xSemaphoreGive(mic.aviso);
  }
}

// Arranca la captura. El I2S ya debe estar iniciado (32 bits, mono, 16 kHz). false = sin memoria: no hay micrófono.
bool micIniciar(I2SClass* i2s) {
  mic.anillo = (int32_t*)ps_malloc(MIC_ANILLO_MUESTRAS * sizeof(int32_t));
  if (!mic.anillo) return false;
  memset(mic.anillo, 0, MIC_ANILLO_MUESTRAS * sizeof(int32_t));
  mic.aviso = xSemaphoreCreateBinary();
  if (!mic.aviso) return false;
  mic.i2s = i2s;
  mic.lista = true;
  xTaskCreatePinnedToCore(tareaMicrofono, "mic", 4096, nullptr, MIC_PRIORIDAD, nullptr, MIC_NUCLEO);
  return true;
}

// Salta al presente: se llama al volver de algo largo (enviar, hablar, pausa) para no procesar audio viejo.
void micAlPresente() { mic.leido = mic.total; }

// Entrega hasta "max" muestras (24 bits, filtradas), esperando como mucho "esperaMs" a que haya alguna. Devuelve cuántas.
size_t micLeer(int32_t* destino, size_t max, uint32_t esperaMs) {
  if (!mic.lista) { vTaskDelay(pdMS_TO_TICKS(esperaMs ? esperaMs : 1)); return 0; }
  uint32_t disponibles = mic.total - mic.leido;
  if (!disponibles && esperaMs) {
    xSemaphoreTake(mic.aviso, pdMS_TO_TICKS(esperaMs));
    disponibles = mic.total - mic.leido;
  }
  if (disponibles > MIC_ANILLO_MUESTRAS - MIC_BLOQUE) {                // el consumidor se atrasó más que el anillo: se perdió audio
    mic.desbordes = mic.desbordes + 1;
    mic.leido = mic.total - MIC_BLOQUE; disponibles = MIC_BLOQUE;
  }
  size_t n = min((size_t)disponibles, max);
  for (size_t i = 0; i < n; i++) destino[i] = mic.anillo[(mic.leido + i) & (MIC_ANILLO_MUESTRAS - 1)];
  mic.leido += n;
  return n;
}

// Copia "muestras" del anillo que terminan en "hasta" (índice total) a un destino ya reservado. Devuelve cuántas copió.
// La ventana conversacional la usa para incluir el audio anterior al disparo (no perder la primera sílaba).
uint32_t micCopiarHasta(int16_t* destino, uint32_t hasta, uint32_t muestras, int desplazar) {
  if (!mic.lista || !destino) return 0;
  uint32_t total = mic.total;
  if (hasta > total) hasta = total;
  uint32_t minimo = total > (uint32_t)(MIC_ANILLO_MUESTRAS - 2 * MIC_BLOQUE) ? total - (MIC_ANILLO_MUESTRAS - 2 * MIC_BLOQUE) : 0;
  if (hasta < minimo) hasta = minimo;
  uint32_t ini = hasta > muestras ? hasta - muestras : 0;
  if (ini < minimo) ini = minimo;
  uint32_t n = hasta - ini;
  for (uint32_t i = 0; i < n; i++) destino[i] = (int16_t)constrain(mic.anillo[(ini + i) & (MIC_ANILLO_MUESTRAS - 1)] >> desplazar, -32768, 32767);
  return n;
}

// Para /estado: tasa real y huecos desde la lectura anterior (leer reinicia la ventana).
void micEstadisticas(float& hz, uint32_t& huecos, uint32_t& huecoMaxMs, uint32_t& desbordes) {
  int64_t ahora = esp_timer_get_time();
  int64_t dt = ahora - mic.inicioVentanaUs;
  hz = dt > 0 ? (float)((double)mic.muestrasVentana * 1e6 / (double)dt) : 0;
  huecos = mic.huecos; huecoMaxMs = mic.huecoMaxMs; desbordes = mic.desbordes;
  mic.muestrasVentana = 0; mic.inicioVentanaUs = ahora; mic.huecos = 0; mic.huecoMaxMs = 0; mic.desbordes = 0;
}

// Copia los últimos "muestras" del anillo como PCM de 16 bits (>> desplazar). El llamador libera con free(). Devuelve bytes.
size_t micCopiarUltimos(int16_t** salida, uint32_t muestras, int desplazar) {
  if (!mic.lista) return 0;
  uint32_t total = mic.total;
  muestras = min(muestras, min(total, (uint32_t)(MIC_ANILLO_MUESTRAS - 2 * MIC_BLOQUE)));   // margen: la captura sigue escribiendo
  if (!muestras) return 0;
  int16_t* b = (int16_t*)ps_malloc(muestras * 2);
  if (!b) return 0;
  uint32_t ini = total - muestras;
  for (uint32_t i = 0; i < muestras; i++) b[i] = (int16_t)constrain(mic.anillo[(ini + i) & (MIC_ANILLO_MUESTRAS - 1)] >> desplazar, -32768, 32767);
  *salida = b;
  return (size_t)muestras * 2;
}
