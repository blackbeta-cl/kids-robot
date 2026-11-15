/*
  Prueba del amplificador MAX98357A (ESP32-S3, core 3.x, ESP_I2S).
  Toca un tono de 440 Hz a volumen BAJO: 0,4 s de tono y 1,6 s de silencio, en bucle.
  Conexiones:
    MAX98357A  VIN -> 5V   GND -> GND
               BCLK -> GPIO15   LRC -> GPIO16   DIN -> GPIO17
               SD y GAIN libres por ahora
    Condensador 470 uF: + (pata larga) a VIN y - a GND del MAX98357A
    Parlante en los bornes + y - del MAX98357A.
  Para subir el volumen cambia VOLUMEN (0 a 32767). Empieza bajo.
*/
#include <ESP_I2S.h>

#define PIN_BCLK 15
#define PIN_LRC  16
#define PIN_DIN  17
#define FS 16000
#define VOLUMEN 1500     // ~4.5 % del máximo: bajo a propósito

I2SClass i2s;

void setup() {
  Serial.begin(115200);
  delay(300);
  i2s.setPins(PIN_BCLK, PIN_LRC, PIN_DIN);   // bclk, ws, dout
  if (!i2s.begin(I2S_MODE_STD, FS, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO)) {
    Serial.println("ERROR: no pude iniciar I2S.");
    while (true) delay(1000);
  }
  Serial.println("Amplificador listo: tono de 440 Hz, volumen bajo.");
}

void tocar(float hz, uint32_t ms) {
  static int16_t buf[256 * 2];            // 256 cuadros estéreo
  static float fase = 0;
  const float paso = 2.0f * PI * hz / FS;
  uint32_t total = (uint32_t)FS * ms / 1000;
  for (uint32_t hecho = 0; hecho < total; hecho += 256) {
    for (int i = 0; i < 256; i++) {
      int16_t m = (int16_t)(sinf(fase) * VOLUMEN);
      fase += paso; if (fase > 2.0f * PI) fase -= 2.0f * PI;
      buf[2 * i] = m; buf[2 * i + 1] = m;
    }
    i2s.write((uint8_t*)buf, sizeof(buf));
  }
}

void silencio(uint32_t ms) {
  static int16_t cero[256 * 2] = {0};
  uint32_t total = (uint32_t)FS * ms / 1000;
  for (uint32_t hecho = 0; hecho < total; hecho += 256) i2s.write((uint8_t*)cero, sizeof(cero));
}

void loop() {
  Serial.println("tono");
  tocar(440, 400);
  silencio(1600);
}
