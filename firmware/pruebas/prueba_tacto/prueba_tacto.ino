/*
  Prueba del sensor táctil TTP223 (ESP32-S3).
  Lee GPIO 14 con antirrebote e imprime 1 (tocado) / 0 (suelto) por Serial a 115200.
  Al soltar, dice cuánto duró el toque y si valdría como "hablar" (>= 400 ms).
  Sirve para medir la sensibilidad con el cartón real encima.
  Conexiones:
    TTP223  VCC -> 3V3   GND -> GND   IO -> GPIO 14   (salida alta mientras se toca)
  Sin pull-up ni pull-down internos: el módulo ya empuja la línea.
*/
#define PIN_TACTO 14
#define MS_ANTIRREBOTE 30
#define MS_TOQUE_MIN 400     // toques más cortos se ignorarán en el sketch de voz

bool estable = false;        // estado ya filtrado
bool leido = false;          // última lectura cruda
uint32_t cambioCrudo = 0;    // cuándo cambió la lectura cruda
uint32_t inicioToque = 0;

void setup() {
  Serial.begin(115200);
  delay(300);
  pinMode(PIN_TACTO, INPUT);
  leido = estable = digitalRead(PIN_TACTO);
  Serial.printf("Tacto listo en GPIO %d. Estado inicial: %d\n", PIN_TACTO, estable);
}

void loop() {
  uint32_t ahora = millis();
  bool crudo = digitalRead(PIN_TACTO);
  if (crudo != leido) { leido = crudo; cambioCrudo = ahora; }

  if (leido != estable && ahora - cambioCrudo >= MS_ANTIRREBOTE) {
    estable = leido;
    if (estable) {
      inicioToque = cambioCrudo;
      Serial.println("1  tocado");
    } else {
      uint32_t dur = cambioCrudo - inicioToque;
      Serial.printf("0  suelto (duro %lu ms) %s\n", (unsigned long)dur, dur >= MS_TOQUE_MIN ? "-> valido" : "-> muy corto, se ignora");
    }
  }
}
