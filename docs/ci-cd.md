# CI/CD, releases y despliegue

Este documento describe cómo se integra, se libera y se despliega el proyecto **original** (`blackbeta-cl/kids-robot`), y cómo hacer lo mismo con tu fork. **El despliegue automático al servidor del proyecto original es solo para su mantenedor**: el resto de usuarios descarga el firmware de las releases y monta su propio servidor ([servidor.md](servidor.md)).

## Flujo

```
PR ──▶ CI (secretos, pruebas del servidor, lógica y compilación del firmware) ──▶ revisión ──▶ merge a main
                                                                                        │
                                       ┌────────────────────────────────────────────────┤
                                       ▼                                                ▼
              deploy-server.yml (si cambió server/)                      etiqueta vX.Y.Z (sobre main)
              CI otra vez ─▶ entorno "produccion"                          release-firmware.yml
              ─▶ rsync + reinicio + comprobación                           compila ─▶ ⏸ APROBACIÓN MANUAL
                 (con vuelta atrás si falla)                               (entorno "firmware-produccion")
                                                                           ─▶ firma ─▶ GitHub Release ─▶ OTA al servidor
```

| Workflow | Cuándo | Qué hace |
|---|---|---|
| `ci.yml` | cada PR y push a `main` | `tools/revisar_secretos.sh`; pruebas de `server/`; pruebas de lógica del firmware; compila el firmware con las plantillas (sin secretos) |
| `deploy-server.yml` | push a `main` que toca `server/` (o a mano) | Reejecuta el CI y despliega `server/` por SSH con `deploy/deploy-server.sh`. **Solo en `blackbeta-cl/kids-robot`** |
| `release-firmware.yml` | al subir una etiqueta `vX.Y.Z` | Compila → **espera la aprobación manual** → firma → crea la GitHub Release con los binarios → publica `app.bin`+`version.json` en el servidor |

Nada llega al servidor ni a una release sin pasar por una **PR aprobada** (`main` protegida) y, en el caso del firmware, por la **aprobación manual** del entorno `firmware-produccion`.

## Protección de `main`

Configurada con un *ruleset* del repositorio:

- Solo se acepta por **Pull Request** (sin pushes directos, ni borrar ni reescribir `main`).
- Requiere **1 aprobación**, de quien figure en `CODEOWNERS`, y que se resuelvan las conversaciones.
- Requiere los checks del CI: `Sin secretos ni datos`, `Servidor (pruebas)`, `Firmware (lógica en el PC)`, `Firmware (compila)`.
- La rama debe estar al día con `main` antes de fusionar.
- Las etiquetas `v*` solo las puede crear el administrador.
- Quien administra el repo puede fusionar su propio PR usando *bypass* **únicamente a través de un PR** (nunca push directo), para no quedar bloqueado cuando es la única persona del proyecto. Si hay un segundo revisor, quita ese bypass.

## Secretos y variables (solo el proyecto original)

Entorno **`produccion`** (restringido a la rama `main`):

| Tipo | Nombre | Contenido |
|---|---|---|
| variable | `DEPLOY_HOST` | nombre del servidor |
| variable | `DEPLOY_USER` | usuario SSH de despliegue |
| variable | `DEPLOY_PATH` | carpeta del servicio (p. ej. `/opt/kids-robot`) |
| variable | `DEPLOY_PORT`, `DEPLOY_SERVICE`, `DEPLOY_VENV` | opcionales (22, `robot-puente`, `$DEPLOY_PATH/.venv`) |
| secreto | `DEPLOY_SSH_KEY` | llave privada **exclusiva para el CI** (no la tuya personal) |
| secreto | `DEPLOY_KNOWN_HOSTS` | salida de `ssh-keyscan` **verificada** (la huella del servidor queda fijada) |

Entorno **`firmware-produccion`** (restringido a las etiquetas `v*`, con **revisores requeridos**): las mismas variables más `DEPLOY_FIRMWARE_PATH` (la carpeta `FIRMWARE_DIR` del servidor), los secretos `DEPLOY_SSH_KEY` y `DEPLOY_KNOWN_HOSTS`, y el secreto **`FIRMWARE_SIGNING_KEY`** (el contenido de `firma-privada.pem`). Sin `FIRMWARE_SIGNING_KEY` la release se crea igual (para grabar a mano) pero no se firma ni se publica por OTA.

> **Decisión de seguridad que debes tomar:** guardar la clave de firma como secreto de GitHub significa que quien pueda ejecutar ese workflow aprobado puede firmar firmware. El entorno la protege (solo etiquetas `v*`, solo tras aprobación manual, y las etiquetas están restringidas), pero es más seguro que la clave viva **solo en tu equipo** y firmes tú (`publicar.sh firmar`) subiendo `version.json` a mano. Elige conscientemente.

### Usuario de despliegue en el servidor

Crea un usuario dedicado con permisos mínimos (no uses tu usuario administrador):

```bash
sudo adduser --disabled-password --gecos "" deploy
sudo install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
# pega la clave PÚBLICA del par que generaste para el CI:
echo "ssh-ed25519 AAAA... ci-kids-robot" | sudo tee /home/deploy/.ssh/authorized_keys && sudo chown deploy:deploy /home/deploy/.ssh/authorized_keys && sudo chmod 600 /home/deploy/.ssh/authorized_keys
# puede escribir en la carpeta del servicio y firmware:
sudo usermod -aG robot deploy && sudo chmod -R g+rwX /opt/kids-robot && sudo chmod g+s /opt/kids-robot
# y reiniciar SOLO el servicio:
echo 'deploy ALL=(root) NOPASSWD: /usr/bin/systemctl restart robot-puente, /usr/bin/journalctl -u robot-puente *' | sudo tee /etc/sudoers.d/deploy-robot && sudo chmod 440 /etc/sudoers.d/deploy-robot && sudo visudo -c
```

Genera la llave del CI y su `known_hosts` en tu equipo (no la pegues en chats):

```bash
ssh-keygen -t ed25519 -f ./ci-key -N "" -C ci-kids-robot
ssh-keyscan -p 22 robot.tu-dominio.com   # compara la huella con la del servidor antes de guardarla
gh secret set DEPLOY_SSH_KEY --env produccion < ci-key && gh secret set DEPLOY_KNOWN_HOSTS --env produccion < known_hosts
```

(Y lo mismo con `--env firmware-produccion`.) Borra `ci-key` de tu equipo cuando termines.

> Si el servicio ya existía con otros nombres o rutas (otra carpeta, otro usuario de servicio, otro entorno virtual), ajusta `DEPLOY_PATH`, `DEPLOY_SERVICE` y `DEPLOY_VENV`. **Antes del primer despliegue automático** añade `ROBOT_TZ` y, si ya usabas el robot, `ROBOT_ID` con el valor que tenía tu instalación al `.env` del servidor: las claves de persona y recuerdos se guardan bajo ese `ROBOT_ID`.

## Cómo publicar una versión de firmware

1. En un PR: sube `FIRMWARE_VERSION` en `firmware/robot_rostro/estado.h` (por ejemplo `1.0.1`) y fusiónalo.
2. Etiqueta el commit de `main`: `git tag v1.0.1 && git push origin v1.0.1`.
3. En *Actions → Release de firmware*, revisa la compilación y **aprueba** el entorno `firmware-produccion`.
4. Se crea la Release con `kids-robot-vX.merged.bin` (grabar a mano en `0x0`), `kids-robot-vX.app.bin`, `bootloader`, `partitions`, `SHA256SUMS` y, si hay clave, `version.json` firmado. Los robots del servidor la ven en ≤10 min.

## Tu fork

1. Haz un fork. No habrá secretos: `deploy-server.yml` no corre porque `github.repository` no es el original (cambia ese texto en los workflows por el nombre de tu fork para activarlo).
2. Genera **tu clave de firma** (`firmware/robot_rostro/generar_clave_firma.sh`), commitea la nueva `firma_publica.h` y crea tus propios entornos y secretos como arriba.
3. O no uses el CI para desplegar: `deploy/deploy-server.sh` y `deploy/deploy-firmware.sh` se pueden ejecutar a mano.
