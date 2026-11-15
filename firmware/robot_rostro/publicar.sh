#!/usr/bin/env bash
# publicar.sh — compila y firma el firmware en Linux/macOS/CI (equivalente a publicar.ps1).
#
#   ./publicar.sh compilar            compila a build/ (app.bin para la OTA y merged.bin para grabar por cable desde 0x0)
#   ./publicar.sh firmar CLAVE.pem    escribe build/version.json con la firma ECDSA P-256 del texto
#                                     "kids-robot-fw:<version>:<sha256>" (la clave privada nunca sale de tu equipo)
#   ./publicar.sh version             imprime FIRMWARE_VERSION
#
# Los archivos de build/ (app.bin + version.json) son los que el servidor sirve en /firmware/ (carpeta FIRMWARE_DIR).
# El robot solo instala una versión MAYOR que la suya y con firma válida para la clave de firma_publica.h.
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FQBN='esp32:esp32:esp32s3:PSRAM=opi,FlashSize=16M,PartitionScheme=app3M_fat9M_16MB,CDCOnBoot=default'
SALIDA="$AQUI/build"

version() {
  sed -n 's/^#define FIRMWARE_VERSION "\([^"]*\)".*/\1/p' "$AQUI/estado.h" | head -n1
}

compilar() {
  # Sin voz_config.h / wifi_config.h el sketch no compila: se usan las plantillas (sin secretos) si faltan.
  [ -f "$AQUI/wifi_config.h" ] || cp "$AQUI/wifi_config.example.h" "$AQUI/wifi_config.h"
  [ -f "$AQUI/voz_config.h" ] || cp "$AQUI/voz_config.example.h" "$AQUI/voz_config.h"
  mkdir -p "$SALIDA"
  arduino-cli compile -b "$FQBN" --output-dir "$SALIDA" "$AQUI"
  ls -l "$SALIDA"/robot_rostro.ino.bin
  echo "Compilado v$(version)"
}

firmar() {
  local clave="${1:?uso: publicar.sh firmar CLAVE.pem}"
  [ -f "$clave" ] || { echo "No encuentro la clave de firma: $clave" >&2; exit 1; }
  local bin="$SALIDA/robot_rostro.ino.bin"
  [ -f "$bin" ] || { echo "Falta $bin: ejecuta primero './publicar.sh compilar'" >&2; exit 1; }
  local v bytes sha
  v="$(version)"
  bytes="$(wc -c < "$bin" | tr -d ' ')"
  sha="$(sha256sum "$bin" | cut -d' ' -f1)"
  printf 'kids-robot-fw:%s:%s' "$v" "$sha" > "$SALIDA/firma-mensaje.txt"
  openssl dgst -sha256 -sign "$clave" -out "$SALIDA/firma.der" "$SALIDA/firma-mensaje.txt"
  local firma
  firma="$(od -An -v -tx1 "$SALIDA/firma.der" | tr -d ' \n')"
  printf '{"version":"%s","bytes":%s,"sha256":"%s","firma":"%s"}' "$v" "$bytes" "$sha" "$firma" > "$SALIDA/version.json"
  cp "$bin" "$SALIDA/app.bin"
  rm -f "$SALIDA/firma.der"
  echo "Firmado v$v ($bytes bytes, sha256 $sha) -> $SALIDA/version.json"
}

case "${1:-}" in
  compilar) compilar ;;
  firmar) shift; firmar "$@" ;;
  version) version ;;
  *) sed -n '2,10p' "$0"; exit 2 ;;
esac
