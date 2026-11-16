// reposo.h — vida en reposo: cuando nadie le habla, el robot se aburre y hace cosas.
//
// Mira a los lados, se queda curioso, sigue una mosca, juega con una pelota, bosteza y, si pasa mucho
// rato solo, cabecea y se queda dormido. Todo es SOLO cara y cuello (nada de red, nada de modelo):
//   - no cambia la emoción de fondo: trabaja sobre una copia de la cara que se dibuja en cada cuadro
//   - se corta al instante con cualquier actividad (toque, voz, aviso de agenda, texto, OTA, otra emoción)
//   - si estaba dormido, despierta con la cara "sorprendido" 1,5 s y vuelve a "neutral"
// Se incluye desde robot_rostro.ino (usa sus variables). No toca emociones.h.
// Consola serie: "reposo" (estado), "reposo off|on", "reposo mirar|curioso|mosca|pelota|ojos|bostezo|dormir".
#pragma once

#define REPOSO_CUELLO       0          // 1 si el servo del cuello esta conectado; 0 = solo cara (caja actual, sin cuello)
#define REPOSO_PRIMERA_MS   12000UL    // quieto antes de la primera conducta tras la última actividad
#define REPOSO_ENTRE_MIN    4000UL     // pausa entre conductas (al azar entre MIN y MAX)
#define REPOSO_ENTRE_MAX    10000UL
#define REPOSO_JUEGA_MS     40000UL    // desde aquí, además de mirar, juega (mosca, pelota, ojos)
#define REPOSO_SUENO_MS     150000UL   // desde aquí se duerme (una vez; despierta con la actividad)

enum Conducta : uint8_t { C_NADA, C_MIRAR, C_CURIOSO, C_MOSCA, C_PELOTA, C_OJOS, C_BOSTEZO, C_SUENO };
static const char* const CONDUCTA_NOMBRE[] = {"nada", "mirar", "curioso", "mosca", "pelota", "ojos", "bostezo", "dormir"};
enum ObjetoReposo : uint8_t { OBJ_NADA, OBJ_MOSCA, OBJ_PELOTA };

struct Reposo {
  bool activo = true;
  uint32_t ultimaActividad = 0;       // se actualiza mientras el robot hace otra cosa
  uint32_t proxima = 0;               // cuándo toca la siguiente conducta
  Conducta c = C_NADA, anterior = C_NADA;
  uint32_t inicio = 0;                // cuándo empezó la conducta actual
  uint32_t ultimoCuadro = 0;
  uint8_t paso = 0, pasos = 0;        // sub-pasos de la conducta
  uint32_t pasoDesde = 0, pasoHasta = 0;
  int8_t lado = 1;
  float fase = 0;
  // mirada suavizada y objetivo
  float mx = 0, my = 0, tx = 0, ty = 0;
  // retoques sobre la cara de fondo (se recalculan en cada cuadro)
  float abre = 1, dAlto = 0, dAncho = 0, cejas = 0, risa = 0, boca = -1;
  bool bostezo = false, caraSueno = false;
  // objeto que se dibuja encima (mosca, pelota)
  uint8_t objeto = OBJ_NADA;
  int ox = 0, oy = 0;
  // cuello: se mueve a una velocidad limitada para que cabecear sea lento y despertar sea rápido
  bool cuelloMovido = false;
  float cuelloF = 90, cuelloDeseado = 90, cuelloVel = 40;   // grados y grados/seg
  int base = 90;                      // dónde estaba el cuello al empezar
  uint32_t ultCuello = 0;
  int escrito = 90;                   // último ángulo que puso reposo: si cambió, otro módulo tomó el cuello
  bool atenuada = false;              // pantalla en brillo bajo mientras duerme
  bool dormido = false;
  bool despertando = false;
  uint32_t despertarHasta = 0;
} rp;

// ---------- utilidades ----------

static float rpSuave(float a, float b, float x) {          // smoothstep entre a y b
  if (x <= a) return 0;
  if (x >= b) return 1;
  float p = (x - a) / (b - a);
  return p * p * (3 - 2 * p);
}
static float rpMezcla(float a, float b, float p) { return a + (b - a) * p; }
static float rpLimite(float v, float lo, float hi) { return v < lo ? lo : (v > hi ? hi : v); }

static bool reposoOcupado() {
  int sorp = buscarEmocion("sorprendido");
  bool emocionPropia = rp.despertando && emocionActual == sorp;
  // El TTP223 se dispara solo con pulsos cortos (cientos por minuto): solo cuenta como actividad un toque de verdad.
  bool toqueReal = vozGrabando && (millis() - vozInicioToque > VOZ_MS_TOQUE_MIN);
  return vozEstado != VOZ_REPOSO || toqueReal || vozEsperando || modoDemo || hayTexto || actPantallaActiva() ||
         agendaEstado == AGENDA_ESPERANDO || agendaEstado == AGENDA_HABLANDO || agendaAvisoEnPantalla ||
         (emocionActual != 0 && !emocionPropia);
}

static void reposoCuello(float grados, float velocidad) {
#if !REPOSO_CUELLO
  (void)grados; (void)velocidad; return;                      // sin cuello: no se mueve el servo
#endif  // pide un ángulo; reposoMoverCuello lo recorre poco a poco
  rp.cuelloDeseado = rpLimite(grados, 55, 125);
  rp.cuelloVel = velocidad;
  if (!rp.cuelloMovido) { rp.cuelloMovido = true; rp.cuelloF = anguloActual; rp.escrito = anguloObjetivo; rp.ultCuello = millis(); }
}

static void reposoMoverCuello(uint32_t ahora) {
  if (!rp.cuelloMovido) return;
  if (anguloObjetivo != rp.escrito) { rp.cuelloMovido = false; return; }   // la voz u otro módulo movió el cuello: no pelear
  float dt = (ahora - rp.ultCuello) / 1000.0f;
  rp.ultCuello = ahora;
  if (dt <= 0 || dt > 0.5f) return;
  float paso = rp.cuelloVel * dt, dif = rp.cuelloDeseado - rp.cuelloF;
  rp.cuelloF = fabsf(dif) <= paso ? rp.cuelloDeseado : rp.cuelloF + (dif > 0 ? paso : -paso);
  anguloObjetivo = rp.escrito = constrain((int)lroundf(rp.cuelloF), 10, 170);   // sin Serial.printf de moverCabeza: no inundar el monitor
  if (rp.cuelloF == rp.cuelloDeseado && anguloObjetivo == rp.base) rp.cuelloMovido = false;
}

static void reposoLimpiarRetoques() {
  rp.abre = 1; rp.dAlto = 0; rp.dAncho = 0; rp.cejas = 0; rp.risa = 0; rp.boca = -1;
  rp.bostezo = false; rp.caraSueno = false;
}

// Termina lo que esté haciendo y deja todo como estaba (con un solo gesto: volver al centro).
static void reposoCortar(uint32_t ahora, bool despertar) {
  bool estabaDormido = rp.dormido;
  rp.c = C_NADA; rp.dormido = false; rp.objeto = OBJ_NADA;
  rp.tx = rp.ty = rp.mx = rp.my = 0;
  reposoLimpiarRetoques();
  if (rp.atenuada) { pantalla.dim(false); rp.atenuada = false; }
  if (rp.cuelloMovido) reposoCuello(rp.base, 120);
  rp.proxima = ahora + REPOSO_PRIMERA_MS;
  if (estabaDormido && despertar) {
    int sorp = buscarEmocion("sorprendido");
    if (sorp >= 0) { ponerEmocion(sorp); rp.despertando = true; rp.despertarHasta = ahora + 1500; }
  }
}

// ---------- conductas ----------

static const int8_t RP_MIRADAS[][2] = {{-10, 0}, {10, 0}, {-9, -5}, {9, 4}, {0, -7}, {0, 5}, {-8, 4}, {8, -4}};

static void reposoEmpezar(Conducta c, uint32_t ahora) {
  rp.c = c; rp.inicio = ahora; rp.paso = 0; rp.pasoDesde = ahora; rp.pasoHasta = ahora;
  rp.base = anguloObjetivo; rp.lado = random(2) ? 1 : -1; rp.fase = random(0, 628) / 100.0f;
  reposoLimpiarRetoques();
  Serial.printf("Reposo: %s\n", CONDUCTA_NOMBRE[c]);
  if (c == C_MIRAR) rp.pasos = random(2, 5);
  if (c == C_SUENO) rp.dormido = false;
}

static void reposoTerminar(uint32_t ahora) {
  rp.anterior = rp.c;
  rp.c = C_NADA; rp.objeto = OBJ_NADA; rp.tx = rp.ty = 0;
  reposoLimpiarRetoques();
  if (rp.cuelloMovido) reposoCuello(rp.base, 60);
  rp.proxima = ahora + random(REPOSO_ENTRE_MIN, REPOSO_ENTRE_MAX);
}

static Conducta reposoElegir(uint32_t inactivo) {
  struct P { Conducta c; uint8_t peso; };
  static const P calma[] = {{C_MIRAR, 40}, {C_CURIOSO, 25}, {C_MOSCA, 15}, {C_BOSTEZO, 10}, {C_OJOS, 10}};
  static const P aburrida[] = {{C_MIRAR, 18}, {C_CURIOSO, 10}, {C_MOSCA, 24}, {C_PELOTA, 24}, {C_OJOS, 10}, {C_BOSTEZO, 14}};
  const P* tabla = inactivo >= REPOSO_JUEGA_MS ? aburrida : calma;
  uint8_t n = inactivo >= REPOSO_JUEGA_MS ? sizeof(aburrida) / sizeof(P) : sizeof(calma) / sizeof(P);
  for (int intento = 0; intento < 4; intento++) {          // evita repetir la misma dos veces seguidas
    int suma = 0;
    for (uint8_t i = 0; i < n; i++) suma += tabla[i].peso;
    int r = random(suma);
    for (uint8_t i = 0; i < n; i++) { if (r < tabla[i].peso) { if (tabla[i].c != rp.anterior || intento == 3) return tabla[i].c; break; } r -= tabla[i].peso; }
  }
  return C_MIRAR;
}

// Un bostezo cabe en 1,8 s de un ciclo de 4 s (lo dibuja dibujarCara con anim 5): se espera al comienzo del ciclo.
static bool reposoBostezar(uint32_t ahora, uint32_t* t0) {
  if (rp.paso == 0) {
    if (ahora % 4000 < 50) { rp.paso = 1; rp.pasoDesde = ahora; }
    else return false;                                       // esperando el inicio del ciclo
  }
  rp.bostezo = true;
  *t0 = rp.pasoDesde;
  float u = (ahora - rp.pasoDesde) / 1800.0f;
  reposoCuello(rp.base + 7 * sinf(rpLimite(u, 0, 1) * PI), 40);   // echa un poco la cabeza atrás
  if (ahora - rp.pasoDesde >= 2100) { rp.bostezo = false; return true; }
  return false;
}

static void reposoSeguir(float x, float y, uint32_t ahora) {   // ojos y cabeza siguen un punto de la pantalla
  rp.tx = rpLimite((x - 64) * 0.18f, -10, 10);
  rp.ty = rpLimite((y - 32) * 0.22f, -7, 7);
  reposoCuello(rp.base + rpLimite((x - 64) * 0.28f, -16, 16), 70);
}

static void reposoConducta(uint32_t ahora) {
  uint32_t t = ahora - rp.inicio;
  switch (rp.c) {
    case C_MIRAR: {
      if (ahora >= rp.pasoHasta) {
        if (rp.paso >= rp.pasos) { rp.tx = rp.ty = 0; if (ahora >= rp.pasoHasta + 400) reposoTerminar(ahora); break; }
        const int8_t* m = RP_MIRADAS[random(8)];
        rp.tx = m[0]; rp.ty = m[1];
        rp.paso++;
        rp.pasoHasta = ahora + (rp.paso > rp.pasos ? 400 : random(800, 1600));
        if (rp.paso <= rp.pasos && random(2)) reposoCuello(rp.base + m[0] * 1.6f, 45);   // a veces gira la cabeza
        if (rp.paso > rp.pasos) { rp.tx = rp.ty = 0; reposoCuello(rp.base, 45); }
      }
      break;
    }
    case C_CURIOSO: {
      if (t < 300) { rp.tx = rp.lado * 6; rp.ty = -8; reposoCuello(rp.base + rp.lado * 12, 50); }
      rp.dAlto = rpSuave(0, 300, t) * 4; rp.dAncho = -rpSuave(0, 300, t) * 2;
      if (t > 2300) { rp.dAlto = rp.dAncho = 0; rp.tx = rp.ty = 0; reposoCuello(rp.base, 50); }
      if (t > 3000) reposoTerminar(ahora);
      break;
    }
    case C_OJOS: {                                           // juega con los ojos: los gira en círculo
      const uint32_t dur = 3200;
      float a = 6.2832f * t / 1600.0f;
      rp.tx = 9 * cosf(a); rp.ty = 6 * sinf(a);
      reposoCuello(rp.base + 9 * cosf(a), 60);
      if (t > dur - 500) { rp.tx = rp.ty = 0; rp.risa = 8; }
      if (t > dur) reposoTerminar(ahora);
      break;
    }
    case C_BOSTEZO: {
      uint32_t t0;
      if (reposoBostezar(ahora, &t0)) reposoTerminar(ahora);
      break;
    }
    case C_MOSCA: {
      const float dur = 7500;
      float u = t / dur;
      float x = 64 + 58 * sinf(6.2832f * 1.3f * u + rp.fase);
      float y = 26 + 16 * sinf(6.2832f * 2.1f * u + 1.0f);
      float w = rpSuave(0.40f, 0.48f, u) * (1 - rpSuave(0.64f, 0.72f, u));      // se posa cerca de la boca
      x = rpMezcla(x, 70, w); y = rpMezcla(y, 47, w);
      x = rpMezcla(x, 64 + rp.lado * 84, 1 - rpSuave(0, 0.12f, u));             // entra por un borde
      x = rpMezcla(x, 64 - rp.lado * 84, rpSuave(0.88f, 1.0f, u));              // sale por el otro
      rp.objeto = OBJ_MOSCA; rp.ox = (int)lroundf(x); rp.oy = (int)lroundf(y);
      reposoSeguir(x, y, ahora);
      rp.cejas = w * 5;                                                         // se molesta un poco mientras está posada
      if (u > 0.9f) rp.risa = 6;
      if (t >= dur) { rp.objeto = OBJ_NADA; reposoTerminar(ahora); }
      break;
    }
    case C_PELOTA: {
      const float dur = 8000;
      float u = t / dur;
      float x = 64 + 56 * sinf(6.2832f * 0.9f * u);
      float y = 58 - 44 * fabsf(sinf(PI * 7 * u));
      y += (1 - rpSuave(0, 0.08f, u)) * 14 + rpSuave(0.92f, 1.0f, u) * 14;      // sube desde abajo y se va hacia abajo
      rp.objeto = OBJ_PELOTA; rp.ox = (int)lroundf(x); rp.oy = (int)lroundf(y);
      reposoSeguir(x, y, ahora);
      if (u > 0.85f) { rp.risa = 10; rp.boca = 1; }
      if (t >= dur) { rp.objeto = OBJ_NADA; reposoTerminar(ahora); }
      break;
    }
    case C_SUENO: {
      // pasos: 0 bostezo, 1 ojos pesados, 2 cabeceo, 3 ojos pesados, 4 cabeceo, 5 dormido
      static const uint16_t DURACION[] = {0, 8000, 3600, 4000, 3600, 0};
      if (rp.paso == 0) {
        uint32_t t0;
        if (reposoBostezar(ahora, &t0)) { rp.paso = 1; rp.pasoDesde = ahora; }
        break;
      }
      uint32_t tp = ahora - rp.pasoDesde;
      if (rp.paso == 1 || rp.paso == 3) {
        float u = rpLimite(tp / (float)DURACION[rp.paso], 0, 1);
        float objetivo = rp.paso == 1 ? rpMezcla(1.0f, 0.5f, u) : rpMezcla(0.5f, 0.35f, u);
        rp.abre = objetivo;
        if ((tp % 2600) > 2100) rp.abre = 0.12f;                                // parpadeo lento
        reposoCuello(rp.base - (rp.paso == 1 ? 6 : 10), 4);
      } else if (rp.paso == 2 || rp.paso == 4) {
        if (tp < 2200) { rp.abre = 0.1f; reposoCuello(rp.base - 24, 11); }      // la cabeza se le cae despacio
        else if (tp < 2500) {                                                    // ¡sobresalto!
          rp.abre = 1; rp.dAlto = 6; rp.dAncho = -3; reposoCuello(rp.base, 400);
        } else { rp.abre = 1; rp.dAlto = 0; rp.dAncho = 0; }
      } else if (rp.paso == 5) {
        rp.caraSueno = true;
        reposoCuello(rp.base - 12, 8);
        if (!rp.dormido) { rp.dormido = true; Serial.println("Reposo: se quedo dormido"); }
        if (!rp.atenuada && tp > 3000) {                            // brillo bajo, pero visible (dim(true) deja el contraste en 0: no se ve nada)
          pantalla.ssd1306_command(SSD1306_SETCONTRAST); pantalla.ssd1306_command(0x30); rp.atenuada = true;
        }
        break;
      }
      if (rp.paso < 5 && tp >= DURACION[rp.paso]) { rp.paso++; rp.pasoDesde = ahora; }
      break;
    }
    default: break;
  }
}

// ---------- API para robot_rostro.ino ----------

void reposoAtender(uint32_t ahora) {
  // Cuello: se mueve siempre que haya un movimiento pedido (también al volver al centro tras una interrupción)
  if (ahora - rp.ultimoCuadro < 16) return;
  rp.ultimoCuadro = ahora;

  if (rp.despertando) {                                      // cara de sorpresa al despertar, luego neutral
    int sorp = buscarEmocion("sorprendido");
    bool sigue = emocionActual == sorp;
    if (!sigue || ahora >= rp.despertarHasta) {
      if (sigue && (vozEstado == VOZ_REPOSO || vozEstado == VOZ_ESCUCHANDO)) ponerEmocion(buscarEmocion("neutral"));
      rp.despertando = false;
    }
    rp.ultimaActividad = ahora;
    reposoMoverCuello(ahora);
    return;
  }

  if (!rp.activo || reposoOcupado()) {
    if (rp.c != C_NADA || rp.dormido || rp.objeto != OBJ_NADA) reposoCortar(ahora, rp.activo);
    rp.ultimaActividad = ahora;
    reposoMoverCuello(ahora);
    return;
  }

  uint32_t inactivo = ahora - rp.ultimaActividad;
  if (rp.c == C_NADA) {
    if (inactivo >= REPOSO_PRIMERA_MS && ahora >= rp.proxima) {
      if (inactivo >= REPOSO_SUENO_MS) reposoEmpezar(C_SUENO, ahora);
      else reposoEmpezar(reposoElegir(inactivo), ahora);
    }
  }
  if (rp.c != C_NADA) {
    reposoLimpiarRetoques();                                  // cada conducta vuelve a poner los suyos en este cuadro
    reposoConducta(ahora);
  }

  // mirada suavizada (se alcanza el objetivo en ~0,25 s)
  float k = 1 - expf(-16 / 90.0f);
  rp.mx += (rp.tx - rp.mx) * k;
  rp.my += (rp.ty - rp.my) * k;
  reposoMoverCuello(ahora);
}

// Retoca la copia de la cara antes de dibujarla: mirada, párpados, bostezo, sueño.
void reposoAplicar(Cara& c, float& abre) {
  if (rp.c == C_NADA && !rp.dormido && fabsf(rp.mx) < 0.3f && fabsf(rp.my) < 0.3f) return;
  if (rp.caraSueno) {
    int s = buscarEmocion("sueno");
    if (s >= 0) c = caraDe(EMOCIONES[s]);
    c.altura += 1.2f * sinf(millis() / 640.0f);               // respira
    return;
  }
  c.miraX += rp.mx; c.miraY += rp.my;
  c.alto += rp.dAlto; c.ancho += rp.dAncho; c.cejas += rp.cejas;
  if (rp.risa > 0) c.risa = rp.risa;
  if (rp.boca >= 0) c.boca = (uint8_t)rp.boca;
  if (rp.bostezo) { c.anim = 5; c.velocidad = 5; }
  c.altura += (1 - rp.abre) * c.alto * 0.35f;                 // párpado caído: los ojos bajan al cerrarse
  abre *= rp.abre;
}

// Dibuja la mosca o la pelota encima de la cara (antes de pantalla.display()).
void reposoDibujar(uint32_t t) {
  if (rp.objeto == OBJ_NADA) return;
  int x = rp.ox, y = rp.oy;
  if (rp.objeto == OBJ_MOSCA) {
    pantalla.fillCircle(x, y, 6, NEGRO);                       // halo negro para que se vea sobre los ojos blancos
    pantalla.fillRoundRect(x - 3, y - 1, 7, 4, 1, BLANCO);     // cuerpo (antes 2x2 px: casi invisible)
    if ((t / 50) % 2) { pantalla.fillRect(x - 5, y - 4, 4, 2, BLANCO); pantalla.fillRect(x + 2, y - 4, 4, 2, BLANCO); }   // alas que aletean
    else              { pantalla.fillRect(x - 5, y - 2, 3, 2, BLANCO); pantalla.fillRect(x + 3, y - 2, 3, 2, BLANCO); }
  } else {
    pantalla.fillCircle(x, y, 8, NEGRO);
    pantalla.fillCircle(x, y, 6, BLANCO);
    pantalla.fillCircle(x - 2, y - 2, 1, NEGRO);               // brillo
  }
}

// Comandos por el serie. Devuelve true si el texto era de reposo.
bool reposoComando(const char* txt) {
  if (strncasecmp(txt, "reposo", 6) != 0) return false;
  const char* a = txt + 6;
  while (*a == ' ') a++;
  uint32_t ahora = millis();
  if (!*a) {
    Serial.printf("Reposo: %s, conducta=%s, inactivo %lu s%s\n", rp.activo ? "activo" : "apagado", CONDUCTA_NOMBRE[rp.c],
                  (unsigned long)((ahora - rp.ultimaActividad) / 1000), rp.dormido ? ", dormido" : "");
    return true;
  }
  if (strcasecmp(a, "off") == 0) { rp.activo = false; Serial.println("Reposo apagado"); return true; }
  if (strcasecmp(a, "on") == 0) { rp.activo = true; rp.ultimaActividad = ahora; Serial.println("Reposo encendido"); return true; }
  for (uint8_t i = 1; i < sizeof(CONDUCTA_NOMBRE) / sizeof(CONDUCTA_NOMBRE[0]); i++) {
    if (strcasecmp(a, CONDUCTA_NOMBRE[i]) == 0) {
      if (reposoOcupado()) { Serial.println("Reposo: el robot esta ocupado ahora (cara distinta de neutral, voz o pantalla)"); return true; }
      rp.activo = true;
      if (rp.c != C_NADA || rp.dormido) reposoCortar(ahora, false);
      reposoEmpezar((Conducta)i, ahora);
      return true;
    }
  }
  Serial.println("Uso: reposo [off|on|mirar|curioso|mosca|pelota|ojos|bostezo|dormir]");
  return true;
}
