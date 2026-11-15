/*
  Prueba del micrófono INMP441 (ESP32-S3, core 3.x, ESP_I2S).
  Imprime el volumen por Serial a 115200: una barra y el valor.
  Conexiones:
    INMP441  VDD -> 3V3 (NUNCA 5V)   GND -> GND   L/R -> GND
             SCK -> GPIO4   WS -> GPIO5   SD -> GPIO6
  Prueba: silencio = valor bajo y estable; aplaude o habla = la barra sube.
*/
#include <ESP_I2S.h>

#define PIN_SCK 4
#define PIN_WS  5
#define PIN_SD  6
#define FS 16000

I2SClass i2s;

void setup() {
  Serial.begin(115200);
  delay(300);
  i2s.setPins(PIN_SCK, PIN_WS, -1, PIN_SD);   // bclk, ws, dout (sin usar), din
  if (!i2s.begin(I2S_MODE_STD, FS, I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_MONO, I2S_STD_SLOT_LEFT)) {
    Serial.println("ERROR: no pude iniciar I2S.");
    while (true) delay(1000);
  }
  Serial.println("Microfono listo. Habla o aplaude.");
}

void loop() {
  static int32_t buf[512];
  size_t n = i2s.readBytes((char*)buf, sizeof(buf)) / sizeof(int32_t);
  if (n == 0) { Serial.println("Sin datos del microfono (revisa SCK/WS/SD)."); delay(500); return; }

  // El INMP441 entrega 24 bits en la parte alta de 32. Quitamos el offset y medimos el RMS.
  double suma = 0, media = 0;
  for (size_t i = 0; i < n; i++) media += (buf[i] >> 8);
  media /= n;
  for (size_t i = 0; i < n; i++) { double v = (buf[i] >> 8) - media; suma += v * v; }
  double rms = sqrt(suma / n);

  static uint32_t ultimo = 0;
  if (millis() - ultimo >= 100) {
    ultimo = millis();
    int barra = constrain((int)(log10(rms + 1) * 8), 0, 50);
    char linea[64];
    memset(linea, '#', barra); linea[barra] = 0;
    Serial.printf("%8.0f  %s\n", rms, linea);
  }
}
