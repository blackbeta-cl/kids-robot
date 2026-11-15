// emociones.h — generado por el Taller de Emociones
// Para cambiar las caras, diseña en el Taller y pega aquí el código nuevo.
#pragma once
#include <stdint.h>

// Una pieza de un efecto propio (círculo, estrella, línea...)
struct Parte {
  uint8_t forma;  // 0 círculo, 1 aro, 2 rect, 3 línea, 4 triángulo, 5 corazón, 6 estrella, 7 gota, 8 zeta
  uint8_t ancla;  // 0 pantalla, 1 ojo izq, 2 ojo der, 3 boca, 4 cara
  uint8_t anim;   // 0 fija, 1 parpadea, 2 flota, 3 cae, 4 sube, 5 late, 6 órbita, 7 gira, 8 tiembla, 9-11 aparece en el paso 1, 2 o 3
  uint8_t vel;    // 1 lento ... 10 rápido
  uint8_t color;  // 1 blanco, 0 negro (borra)
  int8_t dx, dy, tam, tam2;
};
struct Efecto {
  const char* nombre;
  uint8_t n;      // cuántas piezas usa
  Parte p[8];
};

struct Emocion {
  const char* nombre;
  int8_t ancho, alto, redondez, separacion, altura, cejas, risa, miraX, miraY;
  uint8_t boca;   // 0 nada, 1 sonrisa, 2 sorpresa, 3 recta, 4 triste
  uint8_t extra;  // 0 nada, 1 corazones, 2 lágrima, 3 mejillas, 4 zzz, 5 ojos brillantes, 6 estrellas, 7 estrellas que giran
  uint8_t anim;   // 0 quieto, 1 temblar, 2 saltar, 3 mirar a los lados, 4 gelatina, 5 bostezo
  uint8_t velocidad;  // 1 lento ... 5 normal ... 10 rápido
  uint8_t efecto;     // 0 ninguno, o la posición en EFECTOS
};

//  nombre, piezas, { forma, ancla, anim, vel, color, dx, dy, tam, tam2 }
const Efecto EFECTOS[] = {
  {"ninguno", 0, {}},
  {"sudor", 2, {
    {  7,  4,  3,  4,  1, 44,-20,  2,  0},
    {  7,  4,  3,  3,  1,-44,-12,  2,  0},
  }},
  {"bateria", 6, {
    {  2,  0,  0,  5,  1, 44,-20, 26, 14},
    {  2,  0,  0,  5,  0, 44,-20, 22, 10},
    {  2,  0,  0,  5,  1, 58,-20,  3,  6},
    {  2,  0,  9,  5,  1, 37,-20,  5,  6},
    {  2,  0, 10,  5,  1, 44,-20,  5,  6},
    {  2,  0, 11,  5,  1, 51,-20,  5,  6},
  }},
};
const uint8_t NUM_EFECTOS = sizeof(EFECTOS) / sizeof(EFECTOS[0]);

//  nombre         ancho alto red sep alt cej ris mX  mY boca ext anim vel efc
const Emocion EMOCIONES[] = {
  {"neutral",       30, 30,  8, 14, -4,  0,  0,  0,  0,  0,  0,  0,  5,  0},
  {"feliz",         30, 30,  8, 14, -4,  0, 14,  0,  0,  1,  0,  0,  5,  0},
  {"triste",        30, 24,  8, 16, -2, -8,  0,  0,  4,  4,  2,  0,  5,  0},
  {"enojado",       32, 26,  6, 10, -2, 10,  0,  0,  0,  3,  0,  1,  5,  0},
  {"sorprendido",   26, 36, 13, 16, -6,  0,  0,  0, -2,  2,  0,  0,  5,  0},
  {"sueno",         32,  6,  3, 14,  0,  0,  0,  0,  4,  0,  4,  5,  4,  0},
  {"enamorado",     30, 30,  8, 14, -4,  0,  0,  0,  0,  1,  1,  2,  5,  0},
  {"pensando",      28, 28,  8, 14, -6, -3,  0,  4, -8,  3,  0,  3,  8,  0},
  {"verguenza",     30, 26,  8, 14, -2,  0, 10, -6,  4,  1,  3,  0,  5,  0},
  {"suplicando",    32, 32, 16, 10, -4, -6,  0,  0,  2,  4,  5,  1,  3,  0},
  {"emocionado",    32, 32,  8, 14, -4,  0,  0,  0,  0,  1,  7,  2,  6,  0},
  {"nervioso",      30, 30,  8, 14, -4, -5,  0,  0,  0,  3,  0,  1,  6,  1},
  {"cargando",      32,  6,  3, 14,  0,  0,  0,  0,  0,  1,  0,  0,  5,  2},
};
const uint8_t NUM_EMOCIONES = sizeof(EMOCIONES) / sizeof(EMOCIONES[0]);
