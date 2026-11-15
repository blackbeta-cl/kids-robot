// firma_publica.h — clave PÚBLICA con la que el robot comprueba la firma del firmware que baja del servidor.
// Es pública: puede ir en git. La clave PRIVADA no está en el repositorio ni en el servidor: quien publica firmware la guarda aparte
// (por defecto ~/.kids-robot/firma-privada.pem, o un secreto del CI) y la usa publicar.ps1 / publicar.sh para firmar.
// Si haces un fork, genera tu propio par (docs/firmware.md) y pon aquí tu clave pública: con la actual solo se
// instala firmware firmado por el proyecto original.
// Si se pierde la privada: generar otra, poner aquí la nueva pública y subir ese firmware por cable o por la OTA local (subir.bat ota).
#pragma once

const char FIRMA_CLAVE_PUBLICA[] =
  "-----BEGIN PUBLIC KEY-----\n"
  "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEB5fQkgwTUxTvz8l5Dp/PyPnzS3Cq\n"
  "7plPcv0oYObP/nXaP9yv5PiMTIGIg2AI30rlQANHqoIRhzGijULKVCz8Sg==\n"
  "-----END PUBLIC KEY-----\n";
