#!/usr/bin/env bash
# generar_clave_firma.sh — crea TU par de claves para firmar el firmware (ECDSA P-256) y deja la pública en firma_publica.h.
#
#   ./generar_clave_firma.sh [carpeta]      (por defecto ~/.kids-robot)
#
# La privada (firma-privada.pem) queda SOLO en esa carpeta, con permisos 600: respáldala en un gestor de contraseñas.
# Nunca la subas a git ni a un servidor. Si la pierdes, tendrás que grabar por cable un firmware con una pública nueva.
# Para firmar desde el CI de GitHub, guarda su contenido como secreto del entorno "firmware-produccion" (docs/ci-cd.md).
set -euo pipefail
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CARPETA="${1:-$HOME/.kids-robot}"
PRIVADA="$CARPETA/firma-privada.pem"

mkdir -p "$CARPETA"; chmod 700 "$CARPETA"
[ -e "$PRIVADA" ] && { echo "Ya existe $PRIVADA: no la sobrescribo." >&2; exit 1; }
openssl ecparam -name prime256v1 -genkey -noout -out "$PRIVADA"
chmod 600 "$PRIVADA"
PUBLICA="$(openssl ec -in "$PRIVADA" -pubout 2>/dev/null)"

{
  echo '// firma_publica.h — clave PÚBLICA con la que el robot comprueba la firma del firmware que baja del servidor.'
  echo '// Es pública: puede ir en git. La PRIVADA no está en el repositorio ni en el servidor (ver generar_clave_firma.sh).'
  echo '#pragma once'
  echo
  echo 'const char FIRMA_CLAVE_PUBLICA[] ='
  echo "$PUBLICA" | sed 's/.*/  "&\\n"/'
  echo '  ;'
} > "$AQUI/firma_publica.h"
# El último elemento no debe quedar con ';' en línea aparte: se normaliza.
python3 - "$AQUI/firma_publica.h" <<'PY'
import re, sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
s = re.sub(r'"\n  ;\n$', '";\n', s)
open(p, "w", encoding="utf-8").write(s)
PY
echo "Clave privada: $PRIVADA   (respáldala; no la compartas)"
echo "Clave pública escrita en: $AQUI/firma_publica.h  -> compila y graba ese firmware por cable o por OTA local."
