/*
  agenda.h — avisos programados del robot (recordatorios, alarmas, rutinas, cumpleaños, temporizadores).

  El robot inicia siempre la conexión: cada 20-30 s pregunta GET /pendientes (con X-Token). Si no hay nada,
  el servidor responde 204. Si hay un aviso, llega un WAV con las cabeceras X-Id, X-Tipo, X-Emocion,
  X-Cuello, X-Texto y X-Segundos; se reproduce con el mismo parlante que la voz y después se confirma con
  POST /pendientes/<id>/hecho. Si la confirmación se pierde, el servidor vuelve a ofrecer el mismo id
  dentro de la ventana de 5 min y el robot NO lo repite (lista corta de ids en RAM): solo reconfirma.

  Se incluye desde robot_rostro.ino después de voz.h, estado.h y actualizar.h. La tarea corre en el
  núcleo 0 y solo actúa cuando el robot está en reposo (>= 2 s sin hablar, sin grabación, sin OTA y sin
  texto en pantalla), para no competir con la voz por toque ni con el TLS de la actualización.

  Modos (se pueden fijar en voz_config.h, que no se sube a git):
    AGENDA_ACTIVA 0        apaga todo (ni consulta ni reproduce).
    AGENDA_MODO_PRUEBA 1   consulta, muestra en pantalla y registra en el log, SIN sonido y confirma
                           "omitido" con motivo "modo prueba". Es el primer paso de A3.
    AGENDA_MODO_PRUEBA 0   reproduce y confirma "dicho".

  /estado añade agenda_activa, agenda_estado, agenda_id, agenda_fallos, agenda_intervalo, agenda_ultimo,
  agenda_modo y agenda_consultas. Comando serie: "agenda" fuerza una consulta ya.
*/
#pragma once

#ifndef AGENDA_ACTIVA
#define AGENDA_ACTIVA 1
#endif
#ifndef AGENDA_MODO_PRUEBA
#define AGENDA_MODO_PRUEBA 0          // 0 = reproduce y confirma "dicho"; 1 = solo muestra en pantalla (pruebas)
#endif

#define AGENDA_INTERVALO_MS   (20UL * 1000)   // sondeo normal (20-30 s, como el plan)
#define AGENDA_FALLO_1_MS     (60UL * 1000)    // tras 3 fallos seguidos
#define AGENDA_FALLO_2_MS     (5UL * 60 * 1000) // tras 10 fallos seguidos
#define AGENDA_REPOSO_MS      2000             // reposo mínimo antes de consultar o sonar
#define AGENDA_ESPERA_MS      (2UL * 60 * 1000) // si el niño habla justo después de bajar el aviso, se espera esto
#define AGENDA_MAX_BYTES      (3UL * 1024 * 1024)   // tope del WAV (el servidor corta el texto; sobra)
#define AGENDA_IDS            8                // ids recordados para no repetir si se pierde la confirmación

enum EstadoAgenda : uint8_t { AGENDA_REPOSO, AGENDA_CONSULTANDO, AGENDA_ESPERANDO, AGENDA_HABLANDO, AGENDA_ERROR };

volatile uint8_t agendaEstado = AGENDA_REPOSO;
volatile uint32_t agendaUltimoOk = 0;        // millis() de la última respuesta buena (204 o 200 confirmado)
volatile uint32_t agendaUltimaOcupado = 0;   // última vez que el robot no estaba en reposo
volatile uint32_t agendaIntervalo = AGENDA_INTERVALO_MS;
volatile uint32_t agendaConsultas = 0;
volatile uint16_t agendaFallos = 0;
volatile int agendaUltimoId = -1;
volatile bool agendaForzar = false;
volatile bool agendaTareaCreada = false;
volatile uint32_t agendaProximaMs = 0;

uint8_t* agendaWav = nullptr;
size_t agendaWavBytes = 0;
int agendaIds[AGENDA_IDS];
uint8_t agendaIdsPos = 0;

// Pantalla del modo prueba (la pinta loop() llamando a estAviso; la tarea no toca la pantalla).
volatile bool agendaAvisoEnPantalla = false;
char agendaPantallaTipo[24] = "";
char agendaPantallaTexto[32] = "";

bool agendaVisto(int id) {
  for (uint8_t i = 0; i < AGENDA_IDS; i++) if (agendaIds[i] == id) return true;
  return false;
}

void agendaRecordar(int id) {
  agendaIds[agendaIdsPos] = id;
  agendaIdsPos = (uint8_t)((agendaIdsPos + 1) % AGENDA_IDS);
}

bool agendaLibre() {
  if (otaEnCurso || vozPausada || hayTexto) return false;
  if (vozEstado == VOZ_PENSANDO || vozEstado == VOZ_HABLANDO || vozEstado == VOZ_ESPERANDO) return false;
  // El TTP223 a veces se dispara solo con pulsos cortos (ruido o un roce). Eso no debe bloquear
  // el sondeo; una grabación real (más de VOZ_MS_TOQUE_MIN) sí.
  if (vozGrabando && millis() - vozInicioToque > VOZ_MS_TOQUE_MIN) return false;
  return true;
}

void agendaExito() {
  agendaFallos = 0;
  agendaIntervalo = AGENDA_INTERVALO_MS;
  agendaUltimoOk = millis();
  agendaEstado = AGENDA_REPOSO;
}

void agendaFallo() {
  if (agendaFallos < 65535) agendaFallos++;
  agendaIntervalo = agendaFallos >= 10 ? AGENDA_FALLO_2_MS
                    : agendaFallos >= 3 ? AGENDA_FALLO_1_MS
                                        : AGENDA_INTERVALO_MS;
  agendaEstado = AGENDA_ERROR;
}

bool agendaEsperarLibre(uint32_t maxMs) {
  uint32_t t = millis();
  while (millis() - t < maxMs) {
    if (agendaLibre() && millis() - agendaUltimaOcupado >= AGENDA_REPOSO_MS) return true;
    vTaskDelay(pdMS_TO_TICKS(250));
  }
  return false;
}

bool agendaConfirmar(int id, const char* resultado, const char* motivo) {
  if (id <= 0) return false;
  VozCliente cliente;
  vozPrepararCliente(cliente);
  HTTPClient http;
  http.setConnectTimeout(15000);
  http.setTimeout(15000);
  String url = String(VOZ_ESQUEMA) + cfgHost + ":" + cfgPuerto + "/pendientes/" + String(id) + "/hecho";
  if (!http.begin(cliente, url)) return false;
  http.addHeader("Content-Type", "application/json");
  if (cfgToken[0]) http.addHeader("X-Token", cfgToken);
  String cuerpo = String("{\"resultado\":\"") + resultado + "\",\"motivo\":\"" + motivo + "\"}";
  int codigo = http.POST(cuerpo);
  http.end();
  if (codigo == 200 || codigo == 404) return true;   // 404: ya no existe o es de otra familia; no se reintenta
  Serial.printf("Agenda: no pude confirmar el aviso %d (%d)\n", id, codigo);
  return false;
}

void agendaMostrarEnPantalla(const String& tipo, const String& texto) {
  snprintf(agendaPantallaTipo, sizeof(agendaPantallaTipo), "%s", tipo.length() ? tipo.c_str() : "aviso");
  const char* t = texto.length() ? texto.c_str() : "aviso";
  snprintf(agendaPantallaTexto, sizeof(agendaPantallaTexto), "%s", t);
  __sync_synchronize();
  agendaAvisoEnPantalla = true;
}

// Reproduce un aviso ya bajado. Pausa la tarea de voz mientras dura (nadie graba ni habla encima).
void agendaReproducir(const String& emocion, int cuello) {
  InfoWav w;
  if (!vozAnalizarWav(agendaWav, agendaWavBytes, w)) {
    Serial.println("Agenda: el WAV del aviso no es valido; lo omito.");
    return;
  }
  vozPausada = true;                       // la tarea de voz no graba ni toca el parlante
  snprintf(vozEmocion, sizeof(vozEmocion), "%s", emocion.length() ? emocion.c_str() : "neutral");
  vozCuello = cuello;
  __sync_synchronize();
  vozEstado = VOZ_HABLANDO;
  Serial.printf("Agenda: suena el aviso (%u bytes, %.1f s)\n", (unsigned)agendaWavBytes,
                (float)(w.largo / (2 * w.canales)) / w.tasa);
  vozReproducir(agendaWav, agendaWavBytes);
  vozEstado = VOZ_REPOSO;
  vozLeido = vozEstable = digitalRead(VOZ_PIN_TACTO);   // si tocó durante el aviso, no arrancar una grabación fantasma
  vozCambioCrudo = millis();
  vozPausada = false;
}

void agendaProcesar() {
  agendaEstado = AGENDA_CONSULTANDO;
  agendaConsultas++;
  VozCliente cliente;
  vozPrepararCliente(cliente);
  HTTPClient http;
  static const char* claves[] = {"X-Id", "X-Tipo", "X-Emocion", "X-Cuello", "X-Texto", "X-Segundos"};
  http.collectHeaders(claves, 6);
  http.setConnectTimeout(15000);           // con HTTPS incluye el apretón de manos TLS
  http.setTimeout(60000);                  // el servidor sintetiza la voz del aviso
  String url = String(VOZ_ESQUEMA) + cfgHost + ":" + cfgPuerto + "/pendientes";
  if (!http.begin(cliente, url)) { Serial.println("Agenda: no pude preparar la consulta."); agendaFallo(); return; }
  if (cfgToken[0]) http.addHeader("X-Token", cfgToken);
  int codigo = http.GET();
  if (codigo == 204) { http.end(); agendaExito(); return; }          // nada que decir
  if (codigo != 200) {
    Serial.printf("Agenda: GET /pendientes -> %d\n", codigo);
    vozDetalleTls(cliente);
    http.end();
    agendaFallo();
    return;
  }

  int id = http.header("X-Id").toInt();
  String tipo = http.header("X-Tipo");
  String emocion = http.header("X-Emocion");
  String cuello = http.header("X-Cuello");
  String texto = vozDecodificarUrl(http.header("X-Texto"));
  String segundos = http.header("X-Segundos");
  Serial.printf("Agenda: aviso %d tipo=%s emocion=%s cuello=%s segundos=%s\n", id, tipo.c_str(),
                emocion.c_str(), cuello.length() ? cuello.c_str() : "-", segundos.c_str());
  Serial.printf("  dice: %s\n", texto.c_str());
  if (id <= 0) { http.end(); Serial.println("Agenda: el aviso llego sin X-Id valido."); agendaFallo(); return; }

  int tam = http.getSize();
  if (tam <= 0 || (uint32_t)tam > AGENDA_MAX_BYTES) {
    http.end();
    Serial.printf("Agenda: tamano de WAV invalido (%d bytes).\n", tam);
    agendaRecordar(id);
    agendaConfirmar(id, "omitido", "tamano");
    agendaExito();
    return;
  }
  size_t leidos = 0;
  uint32_t ultimo = millis();
  WiFiClient* flujo = http.getStreamPtr();
  while (leidos < (size_t)tam) {
    int disp = flujo->available();
    if (disp > 0) {
      int r = flujo->readBytes(agendaWav + leidos, min((size_t)disp, (size_t)tam - leidos));
      if (r > 0) { leidos += (size_t)r; ultimo = millis(); }
    } else {
      if (!flujo->connected() && flujo->available() <= 0) break;
      if (millis() - ultimo > 20000) break;
      vTaskDelay(pdMS_TO_TICKS(5));
    }
  }
  http.end();
  if (leidos != (size_t)tam) {
    Serial.printf("Agenda: descarga cortada (%u de %d bytes); lo omito.\n", (unsigned)leidos, tam);
    agendaRecordar(id);
    agendaConfirmar(id, "omitido", "descarga");
    agendaExito();
    return;
  }
  agendaWavBytes = leidos;
  agendaUltimoId = id;
  bool repetido = agendaVisto(id);
  if (repetido) Serial.println("Agenda: aviso repetido (ya lo dije); no lo vuelvo a sonar.");

#if AGENDA_MODO_PRUEBA
  if (!repetido) {
    Serial.println("Agenda: MODO PRUEBA, no suena.");
    agendaMostrarEnPantalla(tipo, texto);
  }
  agendaRecordar(id);
  agendaConfirmar(id, "omitido", "modo prueba");
  Serial.println("Agenda: aviso mostrado y confirmado en modo prueba.");
  agendaExito();
#else
  if (!repetido) {
    agendaEstado = AGENDA_ESPERANDO;
    if (!agendaEsperarLibre(AGENDA_ESPERA_MS)) {
      Serial.println("Agenda: el robot estuvo ocupado demasiado tiempo; lo omito.");
      agendaRecordar(id);
      agendaConfirmar(id, "omitido", "ocupado");
      agendaExito();
      return;
    }
    agendaReproducir(emocion, cuello.length() ? cuello.toInt() : -1);
    agendaRecordar(id);
  }
  agendaConfirmar(id, "dicho", "");
  agendaExito();
#endif
}

void tareaAgenda(void*) {
  uint32_t proxima = millis() + 5000;      // deja terminar el arranque
  for (;;) {
    vTaskDelay(pdMS_TO_TICKS(500));
    uint32_t ahora = millis();
    agendaProximaMs = (int32_t)(proxima - ahora) > 0 ? proxima : ahora;
    bool forzar = agendaForzar;
    if (forzar) agendaForzar = false;
    if (!forzar && (int32_t)(ahora - proxima) < 0) continue;

    if (WiFi.status() != WL_CONNECTED) { proxima = ahora + 30000; continue; }
#if VOZ_HTTPS
    if (time(nullptr) < 1700000000) { proxima = ahora + 30000; continue; }   // sin hora no se verifica el certificado
#endif
    if (!agendaLibre()) {
      proxima = ahora + 1000;              // está hablando, grabando de verdad o mostrando texto
      continue;
    }
    agendaProcesar();
    proxima = millis() + agendaIntervalo;
  }
}

// La tarea no toca la pantalla: deja el pedido y loop() lo pinta (como voz.h con sus estados).
void agendaAtender(uint32_t ahora) {
  if (!agendaLibre()) agendaUltimaOcupado = ahora;
  if (agendaAvisoEnPantalla) {
    agendaAvisoEnPantalla = false;
    estAviso("Aviso", agendaPantallaTipo, agendaPantallaTexto, 8);
  }
}

void agendaAgregarEstado(JsonDocument& doc) {
#if AGENDA_ACTIVA
  doc["agenda_activa"] = true;
  doc["agenda_estado"] = agendaEstado;
  doc["agenda_id"] = agendaUltimoId;
  doc["agenda_fallos"] = agendaFallos;
  doc["agenda_intervalo"] = agendaIntervalo / 1000;
  doc["agenda_ultimo"] = agendaUltimoOk ? (long)((millis() - agendaUltimoOk) / 1000) : -1;
  doc["agenda_consultas"] = agendaConsultas;
  doc["agenda_modo"] = AGENDA_MODO_PRUEBA ? "prueba" : "sonido";
  doc["agenda_tarea"] = agendaTareaCreada;
  doc["agenda_libre"] = agendaLibre();
  doc["agenda_hora"] = (long)time(nullptr);
  doc["agenda_ocupado"] = (millis() - agendaUltimaOcupado) / 1000;
  doc["agenda_proxima"] = (int32_t)(agendaProximaMs - millis()) / 1000;
  doc["agenda_voz"] = vozEstado;
  doc["agenda_pausa"] = vozPausada;
  doc["agenda_texto"] = hayTexto;
  doc["heap_max"] = ESP.getMaxAllocHeap();
#else
  doc["agenda_activa"] = false;
#endif
}

void agendaIniciar() {
#if !AGENDA_ACTIVA
  Serial.println("Agenda: apagada (AGENDA_ACTIVA 0).");
#else
  if (!redesHay()) { Serial.println("Agenda: apagada (no hay redes Wi-Fi guardadas)."); return; }
  if (!psramFound()) { Serial.println("Agenda: apagada (no hay PSRAM)."); return; }
  agendaWav = (uint8_t*)ps_malloc(AGENDA_MAX_BYTES);
  if (!agendaWav) { Serial.println("Agenda: apagada (no pude reservar el buffer del WAV)."); return; }
  for (uint8_t i = 0; i < AGENDA_IDS; i++) agendaIds[i] = -1;
  agendaUltimaOcupado = millis();
  BaseType_t creada = xTaskCreatePinnedToCore(tareaAgenda, "agenda", VOZ_STACK_TAREA, nullptr, 1, nullptr, 0);
  agendaTareaCreada = (creada == pdPASS);
  if (!agendaTareaCreada) {
    Serial.printf("Agenda: ERROR, no pude crear la tarea (heap %u, max bloque %u).\n",
                  (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMaxAllocHeap());
    return;
  }
  Serial.printf("Agenda: lista en modo %s, cada %lus. PSRAM libre %u KB, heap %u (max %u)\n",
                AGENDA_MODO_PRUEBA ? "PRUEBA (sin sonido)" : "sonido",
                (unsigned long)(AGENDA_INTERVALO_MS / 1000), (unsigned)(ESP.getFreePsram() / 1024),
                (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMaxAllocHeap());
#endif
}
