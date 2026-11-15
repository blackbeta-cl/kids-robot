#!/usr/bin/env bash
# deploy-firmware.sh — publica en tu servidor un firmware YA FIRMADO (app.bin + version.json) para la OTA.
# Orden seguro: primero app.bin y al final version.json (el robot solo mira version.json para decidir).
# Lo usa .github/workflows/release-firmware.yml tras la aprobación manual; también puedes usarlo a mano.
#
# Variables: DEPLOY_HOST, DEPLOY_USER, DEPLOY_FIRMWARE_PATH (carpeta FIRMWARE_DIR del servidor, p. ej. /opt/kids-robot/firmware)
# Opcionales: DEPLOY_PORT (22), DEPLOY_SSH_KEY, FIRMWARE_BUILD_DIR (firmware/robot_rostro/build)
set -euo pipefail

: "${DEPLOY_HOST:?Falta DEPLOY_HOST}" "${DEPLOY_USER:?Falta DEPLOY_USER}" "${DEPLOY_FIRMWARE_PATH:?Falta DEPLOY_FIRMWARE_PATH}"
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="${FIRMWARE_BUILD_DIR:-$AQUI/firmware/robot_rostro/build}"
[ -f "$BUILD/app.bin" ] && [ -f "$BUILD/version.json" ] || { echo "Faltan app.bin y version.json en $BUILD (compila y firma primero)" >&2; exit 1; }
grep -q '"firma":"[0-9a-f]\{100,\}"' "$BUILD/version.json" || { echo "version.json no trae firma: el robot la rechazaría" >&2; exit 1; }

SSH_OPTS=(-P "${DEPLOY_PORT:-22}" -o BatchMode=yes -o StrictHostKeyChecking=yes)
SSH_CMD=(-p "${DEPLOY_PORT:-22}" -o BatchMode=yes -o StrictHostKeyChecking=yes)
if [ -n "${DEPLOY_SSH_KEY:-}" ]; then SSH_OPTS+=(-i "$DEPLOY_SSH_KEY"); SSH_CMD+=(-i "$DEPLOY_SSH_KEY"); fi
DESTINO="$DEPLOY_USER@$DEPLOY_HOST"

echo "== Copiando app.bin"
scp "${SSH_OPTS[@]}" "$BUILD/app.bin" "$DESTINO:$DEPLOY_FIRMWARE_PATH/app.bin.nuevo"
echo "== Copiando version.json"
scp "${SSH_OPTS[@]}" "$BUILD/version.json" "$DESTINO:$DEPLOY_FIRMWARE_PATH/version.json.nuevo"
echo "== Activando (renombrado atómico: app.bin primero, version.json al final)"
ssh "${SSH_CMD[@]}" "$DESTINO" "cd '$DEPLOY_FIRMWARE_PATH' && mv -f app.bin.nuevo app.bin && mv -f version.json.nuevo version.json && ls -l app.bin version.json"
echo "Publicado: $(sed -n 's/.*"version":"\([^"]*\)".*/\1/p' "$BUILD/version.json")"
