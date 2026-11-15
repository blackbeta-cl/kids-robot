// wifi_config.example.h — copia este archivo a wifi_config.h y rellénalo.
// wifi_config.h NO se sube a git (tiene la clave del Wi-Fi y el token). Sin él el sketch no compila.
// OJO: la placa solo funciona en redes de 2,4 GHz (no 5 GHz).
#pragma once

#define WIFI_SSID  ""                  // nombre de tu red Wi-Fi (vacío = el robot funciona solo por Serial)
#define WIFI_CLAVE ""                  // clave de tu red Wi-Fi
#define NOMBRE_ROBOT "kids-robot"      // dirección: http://kids-robot.local/
#define TOKEN_ROBOT ""                 // el mismo valor que ROBOT_TOKEN en server/.env (el servidor se lo exige al robot).
                                       // También protege el servidor local del robot (/cmd, /estado). Sin token ese servidor rechaza todo.
                                       // Se puede dejar vacío y usar el comando "token" por cable (servidor_cfg.h).
#define OTA_CLAVE ""                   // clave para actualizar el firmware por Wi-Fi (subir.bat ota). Vacía = OTA apagada. Pon una larga y aleatoria.
