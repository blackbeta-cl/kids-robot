# Kids Robot

Robot de escritorio con IA para niños: una cara animada en una pantalla OLED, un cuello con servo, un micrófono, un parlante y un servidor que lo hace conversar, recordar y avisar (recordatorios, alarmas, rutinas y cumpleaños).

> **English TL;DR** — Open-source firmware (ESP32-S3) and server (Python/FastAPI) for a desktop companion robot for kids. Spanish-speaking by default. The child talks, the board streams audio to *your* server, which transcribes it (Whisper), asks an LLM, and streams the synthesized answer back. **Read the privacy disclaimer below before you use it with a child.**

---

## ⚠️ Aviso importante: privacidad y datos de menores

**Este proyecto está pensado para que lo monten y supervisen madres, padres o tutores. Antes de ponerlo en manos de un niño, entiende por dónde viajan sus datos.**

Un robot que escucha a un niño procesa **datos personales de un menor** (su voz, lo que dice, su nombre o apodo, su edad, sus gustos). En este proyecto esos datos pasan por varios sitios, y **algunos son servicios de terceros que tú eliges y contratas**:

| Qué sale | A dónde | Cuándo |
|---|---|---|
| **El audio de la voz del niño** | A **tu** servidor (el que montes tú) | Siempre: es el diseño del robot |
| **El audio de la voz del niño** | A **Groq** (`api.groq.com`) | **Solo si activas** `STT_PROVEEDOR=groq` y pones una `GROQ_API_KEY`. **Por defecto está apagado**: la transcripción se hace en tu servidor con Whisper local y el audio no sale de él |
| **Lo que dice el niño, como texto** (más su apodo y edad, y recuerdos aprobados) | Al **proveedor de modelo de lenguaje (LLM)** que configures en `LLM_URL` | Siempre que el robot conversa |
| **El texto de las respuestas del robot** | A **Microsoft** (servicio en línea de síntesis de voz de Edge, vía `edge-tts`) | Siempre que el robot habla |
| Fragmentos de conversación para proponer "recuerdos" | Al mismo proveedor LLM | Si la memoria automática está activa (`EXTRAER_AUTOMATICO`, por defecto sí) |

Lo que debes saber:

- **Los mantenedores de este repositorio no recogen, reciben ni almacenan ningún dato.** No hay telemetría ni servidor central: todo corre en el equipo que tú montes. **Quien despliega el servidor es el responsable del tratamiento de los datos de su hijo o hija** (y de cumplir las leyes que le apliquen: COPPA en EE. UU., RGPD/GDPR y su artículo 8 en la UE, la Ley 19.628 y la nueva Ley 21.719 en Chile, etc.).
- **Groq, el proveedor de LLM, Microsoft y cualquier otro servicio de terceros tienen sus propios términos de uso y políticas de privacidad, que pueden prohibir o restringir su uso con menores de edad, o exigir consentimiento verificable de los padres.** Los mantenedores **no han verificado** que esos términos permitan este uso. **Lee los términos vigentes de cada proveedor antes de activarlo**, porque cambian. Si un proveedor no permite apps para menores, no lo uses.
- **Nada de esto es asesoría legal.** Si lo vas a usar fuera de tu propia casa (un colegio, un producto, un grupo de familias), consulta con un abogado.
- Si quieres que **el audio no salga de tu casa**, déjalo con Whisper local (`STT_PROVEEDOR=local`, el valor por defecto) y usa un LLM que corras tú mismo (cualquier servidor compatible con la API de OpenAI, p. ej. Ollama o vLLM, en `LLM_URL`). La síntesis de voz (`edge-tts`) hoy siempre usa un servicio en línea de Microsoft; solo recibe el texto de las respuestas del robot, no el audio del niño.
- El robot **no es un juguete certificado ni un producto de seguridad**. Tiene filtros básicos de contenido y reglas para el modelo (`server/modo_nino.py`, `server/persona.py`), pero **los modelos de IA pueden equivocarse**. Supervisa el uso, sobre todo al principio.
- Los datos que guarda el servidor (perfil, recuerdos aprobados, agenda, usuarios del panel de padres) están en una base SQLite en `datos/` de **tu** servidor. Los padres pueden revisarlos, aprobarlos y borrarlos desde el panel web. **Protege y respalda esa carpeta; nunca la subas a ningún repositorio.**
- Este software se entrega **"tal cual", sin garantía de ningún tipo** (ver [LICENSE](LICENSE)).

Más detalle técnico en [docs/privacidad.md](docs/privacidad.md).

---

## Cómo funciona

```
 ┌───────────────────────┐   WAV por HTTPS    ┌──────────────────────────────┐
 │ Placa ESP32-S3        │ ─────────────────▶ │ Servidor (Python / FastAPI)  │
 │  · OLED con caras     │                    │  · Whisper (voz → texto)     │
 │  · micrófono INMP441  │ ◀───────────────── │  · LLM (tú eliges proveedor) │
 │  · amplificador+parl. │  WAV en streaming  │  · edge-tts (texto → voz)    │
 │  · sensor táctil      │   + cara + cuello  │  · agenda, memoria, panel    │
 │  · servo (cuello)     │                    │    de padres (web)           │
 └───────────────────────┘                    └──────────────────────────────┘
```

- Mantienes tocado el sensor, hablas, sueltas; el robot contesta con voz y con cara. El primer sonido llega en unos 3–5 s.
- **Lo importante lo ejecuta código local, no el modelo:** alarmas, recordatorios, rutinas y cumpleaños son lógica determinista (`server/agenda.py`); el modelo solo conversa.
- El robot actualiza su firmware por Wi-Fi (OTA) desde tu servidor, solo con **firmware firmado**.

## Contenido del repositorio

| Carpeta | Qué hay |
|---|---|
| [`firmware/robot_rostro/`](firmware/robot_rostro) | Firmware de la placa (Arduino, ESP32-S3): cara, voz, Wi-Fi con portal, agenda, OTA firmada |
| [`firmware/pruebas/`](firmware/pruebas) | Sketches para probar cada pieza de hardware por separado (micrófono, amplificador, sensor táctil) |
| [`firmware/pruebas_pc/`](firmware/pruebas_pc) | Pruebas de la lógica del firmware que corren en el PC |
| [`server/`](server) | El servidor: voz, modelo, agenda, memoria, panel de padres, API de firmware |
| [`deploy/`](deploy) | Servicio systemd, Caddyfile de ejemplo, instalador y scripts de despliegue |
| [`docs/`](docs) | Guías: [servidor desde cero](docs/servidor.md), [firmware](docs/firmware.md), [privacidad](docs/privacidad.md), [CI/CD](docs/ci-cd.md) |

La estructura física (carcasa, cuerpo, piezas impresas) **no** forma parte de este repositorio: aquí solo está el software de la placa y del servidor.

## Empezar

1. **Hardware**: ESP32-S3 N16R8 + OLED SSD1306 + INMP441 + MAX98357A + TTP223 + servo SG90. Pines y conexiones en [docs/firmware.md](docs/firmware.md).
2. **Servidor**: sigue [docs/servidor.md](docs/servidor.md) (VPS pequeño con Ubuntu 24.04 y un dominio, o un equipo de tu casa).
3. **Firmware**: descarga el `.merged.bin` de la [última release](https://github.com/blackbeta-cl/kids-robot/releases/latest) y grábalo con `esptool` (ver [docs/firmware.md](docs/firmware.md)); luego dile al robot tu servidor y token por cable con los comandos `servidor` y `token`. O compílalo tú con `arduino-cli`.

## Seguridad

- El robot y el servidor se hablan por **HTTPS** con verificación de certificado y un **token** (`X-Token`).
- El firmware que se baja por OTA debe estar **firmado (ECDSA P-256)**; la clave privada nunca está en el servidor ni en el repositorio.
- El panel de padres usa login con contraseña (scrypt), bloqueo por intentos, sesiones con cookie `__Host-` y control de origen.
- Reporta vulnerabilidades según [SECURITY.md](SECURITY.md). **No abras un issue público con datos de un niño, tokens o claves.**

## Contribuir

Lee [CONTRIBUTING.md](CONTRIBUTING.md). `main` está protegida: todo entra por Pull Request con CI verde y revisión. Las releases de firmware y los despliegues al servidor del proyecto original los aprueba su responsable; si haces un fork, despliegas **tu** propio servidor (ver [docs/ci-cd.md](docs/ci-cd.md)).

## Licencia

[MIT](LICENSE). Las voces y modelos de terceros (Whisper, edge-tts) tienen sus propias licencias y términos.
