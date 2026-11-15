## Qué cambia y por qué

## Cómo se probó
- [ ] `server/`: pruebas pasan (`python -m unittest test_xxx`)
- [ ] `firmware/`: compila; si toca hardware, indica en qué placa lo probaste

## Lista de verificación
- [ ] No incluye secretos, claves, tokens, IPs reales, ni datos de ningún niño o familia (ni siquiera en tests o capturas)
- [ ] Si toca firmware: subí `FIRMWARE_VERSION` en `estado.h` (solo si es para publicar)
- [ ] Si toca qué datos salen del servidor o a quién se envían: actualicé `README.md` y `docs/privacidad.md`
