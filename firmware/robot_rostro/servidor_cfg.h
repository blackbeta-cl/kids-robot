/*
  servidor_cfg.h — a qué servidor habla el robot y con qué token, configurable SIN recompilar.

  Valores por defecto: los de voz_config.h (VOZ_PC_IP, VOZ_PC_PUERTO) y wifi_config.h (TOKEN_ROBOT), si existen.
  Valores propios: se guardan en la NVS (namespace "srv") con comandos por cable (Serial 115200, "Nueva línea"):
    servidor                      muestra el servidor y si hay token (el token nunca se imprime)
    servidor robot.ejemplo.com    guarda el servidor (puerto 443 por defecto con HTTPS)
    servidor mi-pc.local:8081     guarda servidor y puerto
    servidor borrar               vuelve a los valores de compilación
    token UNA-CLAVE-LARGA         guarda el token (el mismo valor que ROBOT_TOKEN del servidor)
    token borrar                  borra el token guardado
  Tras guardar, el robot se reinicia solo. Estos comandos solo valen por cable (no pasan por /cmd).
  HTTPS o HTTP se elige al compilar (VOZ_HTTPS en voz_config.h); los binarios de los releases usan HTTPS.
*/
#pragma once

#include <Preferences.h>

#ifndef VOZ_PC_IP
#define VOZ_PC_IP ""
#endif
#ifndef VOZ_PC_PUERTO
#define VOZ_PC_PUERTO "443"
#endif
#ifndef TOKEN_ROBOT
#define TOKEN_ROBOT ""
#endif

#define CFG_HOST_MAX 64
#define CFG_TOKEN_MAX 80

char cfgHost[CFG_HOST_MAX + 1] = VOZ_PC_IP;
char cfgPuerto[6] = VOZ_PC_PUERTO;
char cfgToken[CFG_TOKEN_MAX + 1] = TOKEN_ROBOT;

static bool cfgHostValido(const char* s) {
  if (!s[0] || strlen(s) > CFG_HOST_MAX) return false;
  for (const char* p = s; *p; p++) {
    char c = *p;
    if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.' || c == '-')) return false;
  }
  return true;
}

void cfgCargar() {
  Preferences p;
  if (p.begin("srv", true)) {
    String h = p.getString("host", "");
    String pt = p.getString("puerto", "");
    String t = p.getString("token", "");
    p.end();
    if (h.length() && cfgHostValido(h.c_str())) snprintf(cfgHost, sizeof(cfgHost), "%s", h.c_str());
    int n = atoi(pt.c_str());
    if (n > 0 && n < 65536) snprintf(cfgPuerto, sizeof(cfgPuerto), "%d", n);
    if (t.length() && t.length() <= CFG_TOKEN_MAX) snprintf(cfgToken, sizeof(cfgToken), "%s", t.c_str());
  }
  Serial.printf("Servidor: %s:%s (%s), token %s.\n", cfgHost[0] ? cfgHost : "(sin configurar: usa el comando 'servidor')",
                cfgPuerto, VOZ_HTTPS ? "HTTPS" : "HTTP", cfgToken[0] ? "configurado" : "vacío");
}

static void cfgReiniciar(const char* motivo) {
  Serial.printf("%s Reinicio en 1 s para aplicar.\n", motivo);
  delay(1000);
  ESP.restart();
}

// Comandos "servidor ..." y "token ...": solo por cable.
void cfgComando(bool esToken, char* args) {
  while (*args == ' ') args++;
  size_t n = strlen(args);
  while (n && (args[n - 1] == ' ' || args[n - 1] == '\r')) args[--n] = 0;
  Preferences p;
  if (esToken) {
    if (strcasecmp(args, "borrar") == 0) {
      if (p.begin("srv", false)) { p.remove("token"); p.end(); }
      cfgReiniciar("Token: borrado.");
    } else if (!args[0] || strlen(args) > CFG_TOKEN_MAX) {
      Serial.printf("Token: uso: token UNA-CLAVE (1 a %d caracteres) | token borrar\n", CFG_TOKEN_MAX);
    } else {
      if (p.begin("srv", false)) { p.putString("token", args); p.end(); }
      cfgReiniciar("Token: guardado.");
    }
    return;
  }
  if (!args[0]) {
    Serial.printf("Servidor: %s:%s (%s), token %s.\n", cfgHost[0] ? cfgHost : "(sin configurar)", cfgPuerto,
                  VOZ_HTTPS ? "HTTPS" : "HTTP", cfgToken[0] ? "configurado" : "vacío");
    return;
  }
  if (strcasecmp(args, "borrar") == 0) {
    if (p.begin("srv", false)) { p.remove("host"); p.remove("puerto"); p.end(); }
    cfgReiniciar("Servidor: vuelvo a los valores de compilación.");
    return;
  }
  char* dosPuntos = strchr(args, ':');
  int puerto = 0;
  if (dosPuntos) {
    *dosPuntos = 0;
    puerto = atoi(dosPuntos + 1);
    if (puerto <= 0 || puerto > 65535) { Serial.println("Servidor: puerto inválido."); return; }
  }
  if (!cfgHostValido(args)) { Serial.println("Servidor: nombre inválido (letras, números, punto y guion; sin http://)."); return; }
  if (p.begin("srv", false)) {
    p.putString("host", args);
    if (puerto) p.putString("puerto", String(puerto)); else p.remove("puerto");
    p.end();
  }
  cfgReiniciar("Servidor: guardado.");
}
