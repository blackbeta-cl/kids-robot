/*
  redes_logica.h — lógica pura de las redes Wi-Fi guardadas (sin Arduino, sin NVS, sin WiFi.h).
  Se separa de redes.h para poder probarla en el PC con un compilador normal (ver pruebas/test_redes.cpp).

  Modelo:
    - hasta REDES_MAX redes confirmadas, la primera es la usada más recientemente;
    - una red "candidata" (la que el padre acaba de escribir): se prueba sola en el arranque siguiente;
      si conecta pasa a confirmada (primera de la lista); si falla se descarta sin tocar las demás.
  Las claves nunca se imprimen desde aquí.
*/
#pragma once

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define REDES_MAX 4
#define REDES_SSID_MAX 32     // límite del estándar 802.11
#define REDES_CLAVE_MIN 8     // WPA2-PSK
#define REDES_CLAVE_MAX 63

struct RedGuardada {
  char ssid[REDES_SSID_MAX + 1];
  char clave[REDES_CLAVE_MAX + 1];
};

struct ListaRedes {
  RedGuardada red[REDES_MAX];
  uint8_t n;                  // cuántas confirmadas
  bool hayCandidata;
  RedGuardada candidata;
};

enum RedesError : uint8_t {
  REDES_OK = 0,
  REDES_SSID_VACIO,
  REDES_SSID_LARGO,
  REDES_CLAVE_CORTA,          // 1..7 caracteres
  REDES_CLAVE_LARGA,
  REDES_SSID_CON_CONTROL,     // caracteres de control (saltos de línea, etc.)
};

inline const char* redesTextoError(RedesError e) {
  switch (e) {
    case REDES_OK: return "ok";
    case REDES_SSID_VACIO: return "Falta el nombre de la red";
    case REDES_SSID_LARGO: return "Nombre de red muy largo (max 32)";
    case REDES_CLAVE_CORTA: return "Clave muy corta (min 8)";
    case REDES_CLAVE_LARGA: return "Clave muy larga (max 63)";
    case REDES_SSID_CON_CONTROL: return "Nombre con caracteres raros";
  }
  return "error";
}

// Clave vacía = red abierta (se admite); si no, 8..63 caracteres.
inline RedesError redesValidar(const char* ssid, const char* clave) {
  if (!ssid || !ssid[0]) return REDES_SSID_VACIO;
  size_t ls = strlen(ssid);
  if (ls > REDES_SSID_MAX) return REDES_SSID_LARGO;
  for (size_t i = 0; i < ls; i++)
    if ((unsigned char)ssid[i] < 0x20 || ssid[i] == 0x7f) return REDES_SSID_CON_CONTROL;
  size_t lc = clave ? strlen(clave) : 0;
  if (lc > 0 && lc < REDES_CLAVE_MIN) return REDES_CLAVE_CORTA;
  if (lc > REDES_CLAVE_MAX) return REDES_CLAVE_LARGA;
  return REDES_OK;
}

inline void redesLimpiar(ListaRedes& l) {
  memset(&l, 0, sizeof(l));
}

inline void redesCopiar(RedGuardada& d, const char* ssid, const char* clave) {
  memset(&d, 0, sizeof(d));
  snprintf(d.ssid, sizeof(d.ssid), "%s", ssid);
  snprintf(d.clave, sizeof(d.clave), "%s", clave ? clave : "");
}

inline int redesBuscar(const ListaRedes& l, const char* ssid) {
  for (int i = 0; i < l.n; i++)
    if (strcmp(l.red[i].ssid, ssid) == 0) return i;
  return -1;
}

// Pone la red de primera de la lista. Si ya estaba (mismo nombre) actualiza su clave y la sube; si no cabe, sale la última.
inline RedesError redesAgregar(ListaRedes& l, const char* ssid, const char* clave) {
  RedesError e = redesValidar(ssid, clave);
  if (e != REDES_OK) return e;
  int i = redesBuscar(l, ssid);
  if (i < 0) {
    i = (l.n < REDES_MAX) ? l.n++ : REDES_MAX - 1;   // si está llena, sobrescribe la última
  }
  for (int k = i; k > 0; k--) l.red[k] = l.red[k - 1];
  redesCopiar(l.red[0], ssid, clave);
  return REDES_OK;
}

inline bool redesOlvidar(ListaRedes& l, const char* ssid) {
  int i = redesBuscar(l, ssid);
  if (i < 0) return false;
  for (int k = i; k < l.n - 1; k++) l.red[k] = l.red[k + 1];
  memset(&l.red[l.n - 1], 0, sizeof(RedGuardada));
  l.n--;
  return true;
}

inline void redesBorrarTodas(ListaRedes& l) {
  redesLimpiar(l);            // también la candidata
}

// ---- candidata ----

inline RedesError redesProponer(ListaRedes& l, const char* ssid, const char* clave) {
  RedesError e = redesValidar(ssid, clave);
  if (e != REDES_OK) return e;
  redesCopiar(l.candidata, ssid, clave);
  l.hayCandidata = true;
  return REDES_OK;
}

// La candidata conectó: pasa a ser la primera confirmada.
inline bool redesConfirmarCandidata(ListaRedes& l) {
  if (!l.hayCandidata) return false;
  RedGuardada c = l.candidata;
  l.hayCandidata = false;
  memset(&l.candidata, 0, sizeof(l.candidata));
  return redesAgregar(l, c.ssid, c.clave) == REDES_OK;
}

// La candidata no conectó: se tira; las confirmadas quedan como estaban.
inline void redesDescartarCandidata(ListaRedes& l) {
  l.hayCandidata = false;
  memset(&l.candidata, 0, sizeof(l.candidata));
}

// ---- qué red intentar ----

// Cantidad de redes que hay que probar en este arranque: si hay candidata, solo ella (1); si no, las confirmadas.
inline int redesCantidadAIntentar(const ListaRedes& l) {
  return l.hayCandidata ? 1 : l.n;
}

// La red número `i` entre las que hay que probar (0 = la primera). Fuera de rango devuelve nullptr.
inline const RedGuardada* redesAIntentar(const ListaRedes& l, int i) {
  if (l.hayCandidata) return i == 0 ? &l.candidata : nullptr;
  return (i >= 0 && i < l.n) ? &l.red[i] : nullptr;
}

// Siguiente índice en rotación (para reintentar con otra red si la actual no conecta).
inline int redesSiguiente(const ListaRedes& l, int actual) {
  int total = redesCantidadAIntentar(l);
  return total <= 1 ? 0 : (actual + 1) % total;
}

// ---- ayudas del portal (W2), también probadas en el PC ----

// "Robot-A3F2" a partir de los dos últimos bytes de la MAC.
inline void redesNombreAp(char* out, size_t n, uint8_t mac4, uint8_t mac5) {
  snprintf(out, n, "Robot-%02X%02X", mac4, mac5);
}

// Clave aleatoria legible (sin 0/O/1/I/l). `rnd` devuelve 32 bits aleatorios (en la placa: esp_random).
inline void redesGenerarClave(char* out, size_t largo, uint32_t (*rnd)()) {
  static const char alfabeto[] = "23456789ABCDEFGHJKMNPQRSTUVWXYZ";   // 31 símbolos
  const size_t k = sizeof(alfabeto) - 1;
  size_t i = 0;
  for (; i + 1 < largo; i++) {
    uint32_t r;
    do { r = rnd(); } while (r >= (0xFFFFFFFFu / k) * k);          // sin sesgo de módulo
    out[i] = alfabeto[r % k];
  }
  out[i] = 0;
}

// Escapa \ ; , : " para el texto del QR "WIFI:T:WPA;S:<ssid>;P:<clave>;;". Devuelve false si no cabe.
inline bool redesEscapeQr(const char* src, char* dst, size_t n) {
  size_t o = 0;
  for (size_t i = 0; src[i]; i++) {
    char c = src[i];
    bool especial = c == '\\' || c == ';' || c == ',' || c == ':' || c == '"';
    if (o + (especial ? 2 : 1) + 1 > n) { if (n) dst[0] = 0; return false; }
    if (especial) dst[o++] = '\\';
    dst[o++] = c;
  }
  dst[o] = 0;
  return true;
}
