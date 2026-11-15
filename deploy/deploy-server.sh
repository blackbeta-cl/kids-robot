#!/usr/bin/env bash
# deploy-server.sh — copia server/ a tu servidor por SSH, lo reinicia y comprueba que arranca (con vuelta atrás).
# Lo usa el workflow .github/workflows/deploy-server.yml, pero también puedes ejecutarlo a mano desde tu equipo.
#
# Variables (obligatorias):
#   DEPLOY_HOST   nombre o IP del servidor
#   DEPLOY_USER   usuario SSH (con permiso para reiniciar el servicio: ver docs/ci-cd.md)
#   DEPLOY_PATH   carpeta del servidor donde vive el servicio, p. ej. /opt/kids-robot
# Variables (opcionales):
#   DEPLOY_PORT       puerto SSH (22)
#   DEPLOY_SERVICE    nombre del servicio systemd (robot-puente)
#   DEPLOY_VENV       entorno virtual de Python ($DEPLOY_PATH/.venv)
#   DEPLOY_SSH_KEY    ruta a la llave privada (si no, usa tu ssh-agent o la config de ~/.ssh)
#
# Qué copia: los .py del servidor, padres_web/ y requirements.txt.
# Qué NUNCA toca: .env, datos/ (base de datos de la familia), firmware/ (lo publica publicar.sh/.ps1) ni el entorno virtual.
# Antes de copiar guarda los archivos actuales en $DEPLOY_PATH/bak-deploy/<fecha> (conserva los 5 últimos).
set -euo pipefail

: "${DEPLOY_HOST:?Falta DEPLOY_HOST}" "${DEPLOY_USER:?Falta DEPLOY_USER}" "${DEPLOY_PATH:?Falta DEPLOY_PATH}"
PUERTO="${DEPLOY_PORT:-22}"
SERVICIO="${DEPLOY_SERVICE:-robot-puente}"
VENV="${DEPLOY_VENV:-$DEPLOY_PATH/.venv}"
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SSH_OPTS=(-p "$PUERTO" -o BatchMode=yes -o StrictHostKeyChecking=yes)
[ -n "${DEPLOY_SSH_KEY:-}" ] && SSH_OPTS+=(-i "$DEPLOY_SSH_KEY")
DESTINO="$DEPLOY_USER@$DEPLOY_HOST"

echo "== 1/3 Copiando server/ a $DESTINO:$DEPLOY_PATH/.deploy-incoming/"
rsync -az --delete \
  -e "ssh ${SSH_OPTS[*]}" \
  --exclude '.env' --exclude '.env.*' --exclude 'datos/' --exclude 'datos.example/' --exclude 'firmware/' \
  --exclude '.venv/' --exclude '__pycache__/' --exclude 'test_*.py' --exclude 'requirements-pc.txt' \
  "$AQUI/server/" "$DESTINO:$DEPLOY_PATH/.deploy-incoming/"

echo "== 2/3 Instalando, reiniciando y comprobando"
# El script remoto llega por la entrada estándar (nada de secretos en la línea de comandos).
ssh "${SSH_OPTS[@]}" "$DESTINO" env \
  "DEPLOY_PATH=$DEPLOY_PATH" "SERVICIO=$SERVICIO" "VENV=$VENV" bash -s <<'REMOTO'
set -euo pipefail
cd "$DEPLOY_PATH"
TS="$(date +%Y%m%d-%H%M%S)"
RESP="bak-deploy/$TS"
mkdir -p "$RESP"
for f in *.py padres_web requirements.txt; do
  [ -e "$f" ] && cp -a "$f" "$RESP/"
done

restaurar() {
  echo "!! Falló: vuelvo a la versión anterior ($RESP)"
  cp -f "$RESP"/*.py . 2>/dev/null || true
  if [ -d "$RESP/padres_web" ]; then rm -rf padres_web; cp -r "$RESP/padres_web" padres_web; fi
  [ -f "$RESP/requirements.txt" ] && cp -f "$RESP/requirements.txt" requirements.txt
  sudo -n systemctl restart "$SERVICIO" || true
}
trap restaurar ERR

# cp sin -a: los archivos pueden ser de otro usuario del grupo (no se pueden fijar sus fechas ni dueño)
cp -f .deploy-incoming/*.py .
rm -rf padres_web && cp -r .deploy-incoming/padres_web padres_web
cp -f .deploy-incoming/requirements.txt requirements.txt
rm -rf .deploy-incoming

if [ ! -f "$RESP/requirements.txt" ] || ! cmp -s requirements.txt "$RESP/requirements.txt"; then
  echo "requirements.txt cambió: instalo dependencias"
  "$VENV/bin/pip" install --quiet -r requirements.txt
fi

sudo -n systemctl restart "$SERVICIO"
sleep 6
systemctl is-active --quiet "$SERVICIO"
if sudo -n journalctl -u "$SERVICIO" --since "-30s" --no-pager 2>/dev/null | grep -q "Traceback"; then
  echo "El registro del servicio tiene un Traceback tras reiniciar" >&2
  false
fi
curl -fsS -o /dev/null --max-time 10 "http://127.0.0.1:${PUERTO_LOCAL:-8081}/"
trap - ERR
ls -1dt bak-deploy/* | tail -n +6 | xargs -r rm -rf
echo "OK: $SERVICIO activo y respondiendo. Respaldo en $DEPLOY_PATH/$RESP"
REMOTO

echo "== 3/3 Listo"
