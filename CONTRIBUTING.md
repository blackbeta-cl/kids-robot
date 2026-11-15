# Contribuir

¡Gracias por ayudar! Este proyecto lo usan familias con niños pequeños, así que priorizamos la **seguridad, la privacidad y la claridad** sobre la velocidad.

## Reglas básicas

1. **Todo entra por Pull Request** a `main` (protegida: sin pushes directos). Se necesita CI verde y revisión.
2. **Nunca** incluyas secretos, tokens, IPs de tu casa, grabaciones, ni datos de ningún niño/familia, ni siquiera en tests o capturas. Los ejemplos usan datos ficticios (`server/datos.example/`).
3. Los cambios que modifican **qué datos salen del servidor o a quién se envían** deben actualizar `README.md` y `docs/privacidad.md`.
4. No añadas servicios de terceros que reciban voz o texto del niño sin discutirlo antes en un issue.

## Entorno

- **Servidor** (Python 3.12+): `cd server && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt`. Pruebas: `SERIAL_PORT=COM99 python -m unittest test_persona` (una por archivo `test_*.py`).
- **Firmware**: `arduino-cli` + core `esp32:esp32@3.3.12` (ver `.github/actions/arduino/action.yml` para las librerías). Compilar: `bash firmware/robot_rostro/publicar.sh compilar`. Lógica en PC: `firmware/pruebas_pc/`.
- Revisión de secretos antes de commit: `bash tools/revisar_secretos.sh`.

## Firmware: ten en cuenta

- Sube `FIRMWARE_VERSION` en `estado.h` **solo** en el PR que prepara una release (el robot solo instala versiones mayores).
- Los cambios al firmware deben probarse en una placa real si tocan audio, Wi-Fi, OTA o pantalla. Indícalo en el PR.
- **No cambies pines** del plan sin avisar y sin actualizar `docs/firmware.md`. Evita los GPIO 35–37, 19–20, 0/3/45/46 y 48 en la ESP32-S3 N16R8.

## Releases y despliegues

Los hace quien mantiene el proyecto: etiqueta `vX.Y.Z` → compilación → **aprobación manual** → firma → release. Los despliegues al servidor del proyecto original salen de `main` tras la fusión. Detalle en `docs/ci-cd.md`. Si haces un fork, usa tu propia clave de firma y tu propio servidor.
