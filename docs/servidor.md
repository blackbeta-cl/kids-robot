# Montar el servidor desde cero

El servidor (`server/`) recibe el audio del robot, lo transcribe con Whisper, conversa con un LLM, sintetiza la voz y la devuelve **en streaming**. También sirve la agenda, la memoria, el panel web de padres y las actualizaciones de firmware.

> Lee antes el aviso de privacidad del [README](../README.md): este servidor maneja datos de un menor y **tú** eres quien responde por ellos.

**Probado en:** Ubuntu 24.04, Python 3.12, un VPS de 1 vCPU y 2 GB de RAM con Whisper `base` (~1,6 s por frase; `small` tarda ~5 s en 1 vCPU) y Caddy. El instalador y el Caddyfile de este repositorio están escritos con esa receta; **si algo no te funciona en una máquina limpia, abre un issue** (no se ha ejecutado el instalador completo en todas las distribuciones).

Dos formas de montarlo:

- **A. En la nube (recomendado):** un VPS con un dominio y HTTPS. El robot lo alcanza desde cualquier Wi-Fi.
- **B. En tu casa:** un equipo en tu red local (HTTP, sin dominio). Más simple, pero el robot solo funciona en tu Wi-Fi. Ver el final.

## 1. Servidor y acceso

1. Crea un VPS con **Ubuntu 24.04** (1 vCPU / 2 GB bastan con `WHISPER_MODELO=base`) y un **dominio** (p. ej. `robot.tu-dominio.com`) con un registro **A** hacia su IP.
2. Entra por SSH y endurece lo básico **antes de instalar nada** (sin tocar `sshd` si no tienes otra sesión abierta de respaldo):

   ```bash
   sudo adduser --disabled-password usuario && sudo usermod -aG sudo usuario   # tu usuario administrador, con tu llave en ~/.ssh/authorized_keys
   sudo apt update && sudo apt -y upgrade
   sudo apt install -y ufw fail2ban
   sudo ufw default deny incoming && sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw enable
   ```

   Después de probar el acceso con tu llave desde una **sesión nueva**, desactiva la contraseña y el acceso de root (`PasswordAuthentication no`, `PermitRootLogin no` en `/etc/ssh/sshd_config.d/`) y recarga `sshd`. Los intentos de login fallidos cuentan para `fail2ban`.

## 2. Instalar el servicio

```bash
git clone https://github.com/blackbeta-cl/kids-robot.git
cd kids-robot
sudo bash deploy/instalar-servidor.sh
```

El script instala paquetes, crea el usuario `robot`, copia el servidor a `/opt/kids-robot`, crea el entorno virtual con las dependencias, genera `/opt/kids-robot/.env` con un **`ROBOT_TOKEN` aleatorio** y deja el servicio `robot-puente` escuchando **solo en `127.0.0.1:8081`**.

Edita la configuración (`sudo nano /opt/kids-robot/.env`; plantilla comentada en [`server/.env.example`](../server/.env.example)):

```ini
LLM_API_KEY=...            # clave de tu proveedor de LLM
LLM_URL=https://.../v1/chat/completions   # cualquier API compatible con OpenAI
LLM_MODEL=...
ROBOT_TZ=America/Mexico_City              # tu zona horaria: de ella dependen alarmas y recordatorios
ROBOT_NOMBRE=Robi
WHISPER_MODELO=base
```

> Antes de elegir el proveedor de LLM lee sus términos sobre **menores**. Si quieres un LLM local, apunta `LLM_URL` a tu servidor (Ollama, vLLM, etc.).

```bash
sudo systemctl restart robot-puente
sudo journalctl -u robot-puente -n 30 --no-pager     # sin "Traceback"
curl -s http://127.0.0.1:8081/                       # {"estado":"activo", ...}
```

Whisper descarga su modelo la primera vez que se usa (unos cientos de MB): la primera frase tardará más.

## 3. HTTPS con Caddy

Instala Caddy desde su repositorio oficial (sigue [la guía de Caddy](https://caddyserver.com/docs/install#debian-ubuntu-raspbian) y **verifica la huella de la clave** de firma que ahí se indica), y usa el Caddyfile de ejemplo:

```bash
sudo cp deploy/Caddyfile.example /etc/caddy/Caddyfile
sudo sed -i 's/robot.example.com/robot.tu-dominio.com/' /etc/caddy/Caddyfile
sudo mkdir -p /var/log/caddy && sudo chown caddy:caddy /var/log/caddy
sudo -u caddy caddy validate --config /etc/caddy/Caddyfile      # NO uses "sudo caddy validate"
sudo systemctl reload caddy
```

> ⚠️ `sudo caddy validate` (como root) crea el archivo de registro con dueño root y Caddy deja de arrancar. Valida siempre como el usuario `caddy`.

Caddy obtiene y renueva solo el certificado de Let's Encrypt. Solo se publican `/voz`, `/voz/stream`, `/firmware/version`, `/firmware/app.bin`, `/pendientes` y `/padres`; todo lo demás (incluidos `/docs` y `/openapi.json`) responde 404 y el registro de accesos no guarda `X-Token`, cookies ni `Authorization`.

Comprueba desde fuera:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://robot.tu-dominio.com/voz/stream -X POST      # 401 (falta el token)
curl -s -o /dev/null -w "%{http_code}\n" https://robot.tu-dominio.com/                         # 404
curl -s -o /dev/null -w "%{http_code}\n" https://robot.tu-dominio.com/padres/                  # 200
```

## 4. Panel de padres

El panel (`https://robot.tu-dominio.com/padres/`) sirve para guardar el perfil del niño, revisar y aprobar recuerdos, editar la personalidad, programar recordatorios y activar los avisos. Crea tu usuario **en el servidor** (nunca por la web):

```bash
cd /opt/kids-robot && sudo -u robot .venv/bin/python padres_cli.py crear-usuario tu-usuario   # pide la contraseña
```

Otros comandos: `reiniciar-clave`, `cerrar-sesiones`, `listar`. Se apaga con `PANEL_PADRES=0` en el `.env`.

## 5. Probar sin la placa

- **Voz:** envía un WAV de prueba (16 kHz, mono, 16 bits) como lo hace la placa y guarda la respuesta:

  ```bash
  curl -sS -X POST https://robot.tu-dominio.com/voz -H "X-Token: $ROBOT_TOKEN" -H "Content-Type: audio/wav"        --data-binary @prueba.wav -o respuesta.wav -D -
  ```
- **Agenda:** `server/simular_robot.py` imita a la placa consultando `/pendientes` y reproduciendo los avisos (útil con el botón «Probar ahora» del panel):

  ```bash
  python simular_robot.py --url https://robot.tu-dominio.com --token "$ROBOT_TOKEN" --una-vez --sin-sonido
  ```

## 6. Conectar el robot

Con la placa grabada ([docs/firmware.md](firmware.md)), por el monitor serie:

```text
servidor robot.tu-dominio.com
token <el valor de ROBOT_TOKEN en /opt/kids-robot/.env>
```

(`sudo grep ROBOT_TOKEN /opt/kids-robot/.env` lo muestra; no lo pegues en chats ni en issues.)

## 7. Actualizaciones de firmware por OTA (opcional)

El servidor sirve `app.bin` y `version.json` desde `FIRMWARE_DIR` (por defecto `/opt/kids-robot/firmware`). Se generan y **firman** en tu equipo o en tu CI con tu clave ([docs/firmware.md](firmware.md#actualizaciones-por-ota-firmadas)); el servidor solo los entrega y no puede firmar nada.

## 8. Operación

| Tarea | Comando |
|---|---|
| Ver el registro | `sudo journalctl -u robot-puente -f` |
| Reiniciar | `sudo systemctl restart robot-puente` |
| Actualizar el código | `git pull && sudo bash deploy/instalar-servidor.sh` (no toca `.env`, `datos/` ni `firmware/`) |
| Respaldo de la base | `sudo -u robot sqlite3 /opt/kids-robot/datos/memoria.db ".backup '/ruta/segura/memoria-$(date +%F).db'"` — cífralo; contiene datos del niño |
| Apagar la memoria automática | `EXTRAER_AUTOMATICO=0` en el `.env` y reiniciar |
| Apagar el panel | `PANEL_PADRES=0` en el `.env` y reiniciar |

Para **desplegar automáticamente** desde GitHub a tu propio servidor, ver [ci-cd.md](ci-cd.md).

## Opción B — En una red local (sin dominio)

1. Instala en un equipo de casa (Linux, o Windows con Python 3.12/3.13): `cd server && python -m venv .venv && .venv/bin/pip install -r requirements.txt` (en Windows: `.venv\Scripts\pip`).
2. Crea `server/.env` con `ROBOT_TOKEN`, `LLM_*`, `ROBOT_TZ`.
3. Arranca con `HOST=0.0.0.0 python puente.py` (escucha en toda la red local; **solo en una red de confianza** y apágalo si no lo usas: el token protege el acceso, pero no hay cifrado).
4. Firmware: compílalo con `VOZ_HTTPS 0` y `VOZ_PC_IP` = la IP del equipo en `voz_config.h` (opción "B" de `voz_config.example.h`), o usa el comando `servidor IP:8081` con un binario compilado en HTTP.
5. Pon IP fija o reservada en el router para ese equipo.

## Solución de problemas

- **401 en `/voz`:** el token del robot no coincide con `ROBOT_TOKEN` del servidor.
- **403 "falta ROBOT_TOKEN":** el servidor no tiene token y exige uno a todo lo que no sea `127.0.0.1` directo.
- **El robot no habla / tarda mucho:** `journalctl -u robot-puente`; prueba `WHISPER_MODELO=base` y revisa que `LLM_API_KEY`/`LLM_URL` funcionan.
- **Alarmas a la hora equivocada:** falta `ROBOT_TZ`.
- **Caddy no arranca tras validar:** mira el aviso sobre `sudo caddy validate` arriba.
- **El certificado no se emite:** el dominio debe apuntar a la IP del servidor y los puertos 80/443 estar abiertos.
