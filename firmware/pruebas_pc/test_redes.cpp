// Pruebas en el PC de robot_rostro/redes_logica.h (lógica pura: sin Arduino ni placa).
// Compilar y correr:   g++ -std=c++17 -Wall -Wextra -o test_redes test_redes.cpp && ./test_redes
// (o ejecutar_pruebas.bat, que lo hace con el g++ que haya en el PATH)
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "../robot_rostro/redes_logica.h"

static int fallos = 0, total = 0;
#define CHECK(cond) do { total++; if (!(cond)) { fallos++; printf("FALLA l.%d: %s\n", __LINE__, #cond); } } while (0)

static void validacion() {
  CHECK(redesValidar("MiRed", "12345678") == REDES_OK);
  CHECK(redesValidar("MiRed", "") == REDES_OK);                 // red abierta
  CHECK(redesValidar("MiRed", nullptr) == REDES_OK);
  CHECK(redesValidar("", "12345678") == REDES_SSID_VACIO);
  CHECK(redesValidar(nullptr, "12345678") == REDES_SSID_VACIO);
  CHECK(redesValidar("MiRed", "1234567") == REDES_CLAVE_CORTA);
  char largo[80]; memset(largo, 'a', 64); largo[64] = 0;
  CHECK(redesValidar("MiRed", largo) == REDES_CLAVE_LARGA);
  largo[63] = 0;
  CHECK(redesValidar("MiRed", largo) == REDES_OK);              // 63 es el máximo
  char ssid33[40]; memset(ssid33, 'x', 33); ssid33[33] = 0;
  CHECK(redesValidar(ssid33, "12345678") == REDES_SSID_LARGO);
  ssid33[32] = 0;
  CHECK(redesValidar(ssid33, "12345678") == REDES_OK);          // 32 es el máximo
  CHECK(redesValidar("Mi\nRed", "12345678") == REDES_SSID_CON_CONTROL);
  CHECK(redesValidar("Mi red WiFi", "con espacios y ñ") == REDES_OK);
}

static void lista() {
  ListaRedes l; redesLimpiar(l);
  CHECK(redesAgregar(l, "A", "aaaaaaaa") == REDES_OK);
  CHECK(redesAgregar(l, "B", "bbbbbbbb") == REDES_OK);
  CHECK(l.n == 2 && strcmp(l.red[0].ssid, "B") == 0 && strcmp(l.red[1].ssid, "A") == 0);   // la última va primero
  // misma red otra vez: no se duplica, sube y cambia la clave
  CHECK(redesAgregar(l, "A", "nuevaaaa") == REDES_OK);
  CHECK(l.n == 2 && strcmp(l.red[0].ssid, "A") == 0 && strcmp(l.red[0].clave, "nuevaaaa") == 0);
  // llena: la más vieja sale
  redesAgregar(l, "C", "cccccccc"); redesAgregar(l, "D", "dddddddd");
  CHECK(l.n == 4);
  CHECK(redesAgregar(l, "E", "eeeeeeee") == REDES_OK);
  CHECK(l.n == 4 && strcmp(l.red[0].ssid, "E") == 0 && redesBuscar(l, "B") < 0);   // B era la más vieja
  // una inválida no toca nada
  CHECK(redesAgregar(l, "F", "corta") == REDES_CLAVE_CORTA);
  CHECK(l.n == 4 && strcmp(l.red[0].ssid, "E") == 0);
  // olvidar
  CHECK(redesOlvidar(l, "D"));
  CHECK(l.n == 3 && redesBuscar(l, "D") < 0);
  CHECK(!redesOlvidar(l, "D"));
  CHECK(l.red[3].ssid[0] == 0);                                  // el hueco quedó limpio (sin clave residual)
  CHECK(l.red[3].clave[0] == 0);
  redesBorrarTodas(l);
  CHECK(l.n == 0 && !l.hayCandidata);
}

static void candidata() {
  ListaRedes l; redesLimpiar(l);
  redesAgregar(l, "Casa", "casacasa");
  CHECK(redesProponer(l, "Nueva", "nuevanue") == REDES_OK);
  CHECK(l.hayCandidata);
  CHECK(redesCantidadAIntentar(l) == 1);                         // con candidata solo se prueba ella
  CHECK(strcmp(redesAIntentar(l, 0)->ssid, "Nueva") == 0);
  CHECK(redesAIntentar(l, 1) == nullptr);
  CHECK(redesSiguiente(l, 0) == 0);
  // falla: se descarta y Casa sigue
  redesDescartarCandidata(l);
  CHECK(!l.hayCandidata && l.n == 1 && strcmp(l.red[0].ssid, "Casa") == 0);
  CHECK(l.candidata.clave[0] == 0);                              // no quedan restos de la clave
  CHECK(redesCantidadAIntentar(l) == 1 && strcmp(redesAIntentar(l, 0)->ssid, "Casa") == 0);
  // conecta: pasa a primera
  redesProponer(l, "Nueva", "nuevanue");
  CHECK(redesConfirmarCandidata(l));
  CHECK(!l.hayCandidata && l.n == 2 && strcmp(l.red[0].ssid, "Nueva") == 0 && strcmp(l.red[1].ssid, "Casa") == 0);
  CHECK(!redesConfirmarCandidata(l));                            // ya no hay
  // candidata inválida no se acepta y no pisa una buena
  redesProponer(l, "X", "12345678");
  CHECK(redesProponer(l, "Y", "123") == REDES_CLAVE_CORTA);
  CHECK(l.hayCandidata && strcmp(l.candidata.ssid, "X") == 0);
  // una candidata cuyo nombre ya está guardado actualiza la clave en vez de duplicar
  redesDescartarCandidata(l);
  redesProponer(l, "Casa", "otraclave");
  redesConfirmarCandidata(l);
  CHECK(l.n == 2 && strcmp(l.red[0].ssid, "Casa") == 0 && strcmp(l.red[0].clave, "otraclave") == 0);
  // borrar todo borra también la candidata
  redesProponer(l, "Z", "zzzzzzzz");
  redesBorrarTodas(l);
  CHECK(!l.hayCandidata && l.n == 0 && redesCantidadAIntentar(l) == 0);
}

static void rotacion() {
  ListaRedes l; redesLimpiar(l);
  CHECK(redesSiguiente(l, 0) == 0);                              // vacía: no falla
  redesAgregar(l, "A", "aaaaaaaa"); redesAgregar(l, "B", "bbbbbbbb"); redesAgregar(l, "C", "cccccccc");
  int i = 0; const char* orden[] = {"C", "B", "A", "C"};
  for (int k = 0; k < 4; k++) { CHECK(strcmp(redesAIntentar(l, i)->ssid, orden[k]) == 0); i = redesSiguiente(l, i); }
  CHECK(redesAIntentar(l, -1) == nullptr && redesAIntentar(l, 3) == nullptr);
}

static void ayudasPortal() {
  char b[32];
  redesNombreAp(b, sizeof(b), 0xA3, 0x0F);
  CHECK(strcmp(b, "Robot-A30F") == 0);
  char c[8];
  redesNombreAp(c, sizeof(c), 0xA3, 0x0F);                       // buffer chico: no desborda
  CHECK(strlen(c) == 7);
}

static uint32_t semilla = 12345;
static uint32_t azar() { semilla = semilla * 1664525u + 1013904223u; return semilla; }
static uint32_t cero() { return 0; }
static uint32_t maximo() { static int k = 0; return (k++ % 2) ? 0u : 0xFFFFFFFFu; }   // 0xFFFFFFFF debe rechazarse por sesgo

static void claveAleatoria() {
  char k[9];
  redesGenerarClave(k, sizeof(k), azar);
  CHECK(strlen(k) == 8);
  bool limpia = true;
  for (size_t i = 0; k[i]; i++) if (strchr("01OIl", k[i]) || !strchr("23456789ABCDEFGHJKMNPQRSTUVWXYZ", k[i])) limpia = false;
  CHECK(limpia);
  // sirve como clave WPA2 y no se repite entre aperturas
  CHECK(redesValidar("Robot-XXXX", k) == REDES_OK);
  char k2[9]; redesGenerarClave(k2, sizeof(k2), azar);
  CHECK(strcmp(k, k2) != 0);
  // todos los símbolos aparecen con el tiempo y ninguno domina (control grueso de sesgo)
  int cuenta[256] = {0};
  for (int n = 0; n < 3100; n++) { char t[2]; redesGenerarClave(t, sizeof(t), azar); cuenta[(unsigned char)t[0]]++; }
  int vistos = 0, maxc = 0;
  for (int i = 0; i < 256; i++) if (cuenta[i]) { vistos++; if (cuenta[i] > maxc) maxc = cuenta[i]; }
  CHECK(vistos == 31 && maxc < 200);                             // esperado ~100 cada uno
  // con rnd = 0 produce siempre el primer símbolo y termina (no se cuelga)
  char z[5]; redesGenerarClave(z, sizeof(z), cero);
  CHECK(strcmp(z, "2222") == 0);
  char m[5]; redesGenerarClave(m, sizeof(m), maximo);            // rechaza 0xFFFFFFFF y reintenta
  CHECK(strlen(m) == 4);
}

static void escapeQr() {
  char o[64];
  CHECK(redesEscapeQr("Casa", o, sizeof(o)) && strcmp(o, "Casa") == 0);
  CHECK(redesEscapeQr("a;b,c:d\"e\\f", o, sizeof(o)) && strcmp(o, "a\\;b\\,c\\:d\\\"e\\\\f") == 0);
  CHECK(redesEscapeQr("", o, sizeof(o)) && o[0] == 0);
  char chico[4];
  CHECK(!redesEscapeQr("abcd", chico, sizeof(chico)));           // no cabe: falla y deja cadena vacía
  CHECK(chico[0] == 0);
  CHECK(redesEscapeQr("abc", chico, sizeof(chico)) && strcmp(chico, "abc") == 0);   // justo
  CHECK(!redesEscapeQr("ab;", chico, sizeof(chico)));            // el escape lo hace pasar del límite
}

int main() {
  validacion(); lista(); candidata(); rotacion(); ayudasPortal(); claveAleatoria(); escapeQr();
  printf("%d comprobaciones, %d fallos\n", total, fallos);
  return fallos ? 1 : 0;
}
