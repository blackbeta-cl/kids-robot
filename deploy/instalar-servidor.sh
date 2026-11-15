#!/usr/bin/env bash
# instalar-servidor.sh — monta el servidor del robot en un Ubuntu 24.04 (o Debian 12) limpio. Se ejecuta EN EL SERVIDOR.
#
#   git clone https://github.com/blackbeta-cl/kids-robot.git && cd kids-robot
#   sudo bash deploy/instalar-servidor.sh
#
# Qué hace (es repetible: puedes volver a ejecutarlo):
#   1. Instala paquetes (python3-venv, libsndfile1, rsync, curl, sqlite3).
#   2. Crea el usuario de sistema "robot" y la carpeta /opt/kids-robot (cambia con INSTALL_DIR).
#   3. Copia server/ ahí, crea el entorno virtual e instala las dependencias.
#   4. Crea /opt/kids-robot/.env (permisos 600) con un ROBOT_TOKEN aleatorio SI NO EXISTE. No imprime el token.
#   5. Instala y habilita el servicio systemd "robot-puente" (escucha solo en 127.0.0.1:8081).
# Qué NO hace (pasos manuales de docs/servidor.md): endurecer SSH/firewall, instalar Caddy y el dominio,
# poner tu LLM_API_KEY y crear el primer usuario del panel de padres.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Ejecuta con sudo: sudo bash deploy/instalar-servidor.sh" >&2; exit 1; }
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="${INSTALL_DIR:-/opt/kids-robot}"
USUARIO="${ROBOT_USER:-robot}"

echo "== 1/5 Paquetes"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip libsndfile1 rsync curl sqlite3

echo "== 2/5 Usuario y carpeta ($USUARIO, $INSTALL_DIR)"
id "$USUARIO" >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin "$USUARIO"
mkdir -p "$INSTALL_DIR/datos" "$INSTALL_DIR/firmware"

echo "== 3/5 Código y dependencias"
rsync -a --exclude '.env' --exclude 'datos/' --exclude 'firmware/' --exclude '__pycache__/' \
  --exclude 'test_*.py' --exclude 'requirements-pc.txt' "$AQUI/server/" "$INSTALL_DIR/"
[ -d "$INSTALL_DIR/.venv" ] || python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

echo "== 4/5 Configuración (.env)"
if [ ! -f "$INSTALL_DIR/.env" ]; then
  cp "$AQUI/server/.env.example" "$INSTALL_DIR/.env"
  TOKEN="$("$INSTALL_DIR/.venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(32))')"
  sed -i "s|^ROBOT_TOKEN=.*|ROBOT_TOKEN=$TOKEN|" "$INSTALL_DIR/.env"
  unset TOKEN
  echo "Creado $INSTALL_DIR/.env con un ROBOT_TOKEN nuevo (léelo con: sudo grep ROBOT_TOKEN $INSTALL_DIR/.env)."
  echo "EDÍTALO: pon LLM_API_KEY, LLM_URL, LLM_MODEL y ROBOT_TZ."
else
  echo "$INSTALL_DIR/.env ya existe: no se toca."
fi
chown -R "$USUARIO:$USUARIO" "$INSTALL_DIR"
chmod 700 "$INSTALL_DIR/datos"
chmod 600 "$INSTALL_DIR/.env"

echo "== 5/5 Servicio systemd"
sed "s|/opt/kids-robot|$INSTALL_DIR|g; s|^User=robot|User=$USUARIO|; s|^Group=robot|Group=$USUARIO|" \
  "$AQUI/deploy/robot-puente.service" > /etc/systemd/system/robot-puente.service
systemctl daemon-reload
systemctl enable robot-puente
systemctl restart robot-puente
sleep 5
systemctl --no-pager --lines=15 status robot-puente || true
echo
echo "Listo. Siguientes pasos en docs/servidor.md: LLM_API_KEY en $INSTALL_DIR/.env (y 'sudo systemctl restart robot-puente'),"
echo "Caddy + dominio (HTTPS), primer usuario del panel de padres, y configurar el robot con 'servidor' y 'token'."
