// voz_config.example.h — copia este archivo a voz_config.h y rellénalo.
// voz_config.h NO se sube a git (cada casa tiene otra dirección). La clave del Wi-Fi y el token siguen en wifi_config.h.
#pragma once

// Opción A: servidor en la nube por HTTPS (verifica el certificado con las raíces del core; usa la hora por NTP).
#define VOZ_PC_IP      "robot.example.com"   // nombre del servidor (con un nombre válido para el certificado)
#define VOZ_PC_PUERTO  "443"
#define VOZ_HTTPS      1

// Opción B: servidor en un equipo de la casa por HTTP (arrancarlo con HOST=0.0.0.0 para que el robot lo alcance):
// #define VOZ_PC_IP      "192.168.1.100"   // IP del equipo que corre server/puente.py
// #define VOZ_PC_PUERTO  "8081"
// #define VOZ_HTTPS      0

// Zona horaria del robot (cadena POSIX TZ; la usa para validar los certificados HTTPS y la hora). Por defecto UTC.
// #define VOZ_ZONA_HORARIA "<-04>4<-03>,M9.1.6/24,M4.1.6/24"   // ejemplo: Chile
// #define VOZ_ZONA_HORARIA "CET-1CEST,M3.5.0,M10.5.0/3"         // ejemplo: Europa central
// #define VOZ_ZONA_HORARIA "CST6CDT,M3.2.0,M11.1.0"             // ejemplo: México y EE. UU. centro
