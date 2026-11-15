# Seguridad

Este software procesa la voz y los datos de un menor, así que tomamos la seguridad en serio.

## Reportar una vulnerabilidad

**No abras un issue público.** Usa [Reportar una vulnerabilidad](https://github.com/blackbeta-cl/kids-robot/security/advisories/new) (aviso de seguridad privado de GitHub). Incluye pasos para reproducirla y el impacto. Responderemos en cuanto sea posible.

Nunca incluyas en un reporte, issue o PR: tokens, claves de API, claves de firma, contraseñas, grabaciones de voz ni datos personales de un niño o su familia. Si los compartiste por error, **revócalos o cámbialos de inmediato**.

## Qué consideramos importante

- Ejecución de código o instalación de firmware no autorizado en un robot (la OTA exige firma ECDSA; cualquier forma de saltarla es crítica).
- Acceso a la voz, el perfil o los recuerdos de un niño sin autenticación, o entre familias.
- Fugas de secretos en el repositorio, los registros o las respuestas del servidor.
- Debilidades del panel de padres (login, sesiones, CSRF/origen, inyección).

## Modelo de seguridad resumido

- Robot ↔ servidor: HTTPS con verificación de certificado y token `X-Token` (el servidor rechaza a la red sin token; sin `ROBOT_TOKEN` queda cerrado).
- Firmware: firmado con ECDSA P-256; la clave privada no está en el repositorio ni en el servidor. El robot solo instala versiones mayores y verifica SHA-256 y firma; tiene rollback automático si el nuevo firmware no arranca.
- El servidor local de la placa (`/cmd`, `/estado`) exige el token y está cerrado si no hay token configurado; la ruta de audio de depuración (`/mic/audio`) está desactivada por defecto.
- Panel de padres: contraseñas con scrypt, bloqueo por IP y por usuario, sesiones con cookie `__Host-`, control de origen y auditoría.

## Versiones soportadas

Solo la última versión de `main` y la última release de firmware.
