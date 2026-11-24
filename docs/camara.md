# Cámara — plan por etapas

Estado: **plan**, nada implementado. La placa principal (ESP32-S3) no cambia: la cámara es un **nodo aparte**.

## Principios

1. **Las imágenes no salen de la cámara.** Por la red solo viajan resultados ("cara a 30°", "tarjeta 4"), nunca fotos ni video. Las etapas 1 a 4 funcionan sin internet.
2. **Sin grabar ni guardar.** No hay tarjeta SD ni copias de imágenes en la placa, en el robot ni en el servidor.
3. **Se ve cuándo mira.** Un LED queda encendido mientras la cámara procesa, y el lente lleva una tapa física deslizable.
4. **Sin reconocimiento de personas.** Se detecta *que hay* una cara, no *de quién* es. Identificar a alguien es un dato biométrico de un menor y queda fuera de este plan.
5. **Enviar una imagen a un modelo externo** (etapa 5) es opcional, lo activa un adulto y queda en el registro de auditoría. Antes se actualizan `README.md` y `docs/privacidad.md` (ver `CONTRIBUTING.md`).

## Hardware

| Pieza | Notas |
|---|---|
| ESP32-CAM AI-Thinker (OV2640), variante USB-C con antena externa | Tiene ~4 MB de PSRAM; alcanza para detectar caras a 96×96–160×120 (QQVGA) |
| Alimentación 5 V propia, con un condensador de 470 µF | Los picos de corriente del Wi-Fi y de la cámara reinician la placa si se alimenta desde los 3V3 del ESP32-S3. **Nunca** desde 3V3 |
| LED indicador | Usar el LED rojo de la placa (GPIO 33, activo en bajo) o uno externo. **No usar** el flash (GPIO 4) como indicador: encandila |
| Tapa del lente | Impresa en la cabeza o una tapita deslizable |

¿Por qué no conectarla a la S3? Una OV2640 usa ~16 GPIO. La S3 ya tiene ocupados OLED, micrófono, amplificador, servo y sensor táctil, y los pines libres chocan con la lista "evitar" (35–37, 19–20, 0/3/45/46, 48). Con un nodo aparte, el firmware actual queda igual.

## Etapas

### Etapa 0 — La cámara funciona (sin código propio)
- Grabar el ejemplo `CameraWebServer` del core esp32 (modelo `CAMERA_MODEL_AI_THINKER`) y abrir el stream en el navegador, **solo en la red de casa**.
- Comprobar: imagen estable a QVGA, sin reinicios al moverla y con buena señal Wi-Fi dentro de la cabeza (anotar el RSSI).
- **Listo cuando:** 10 minutos de stream sin reinicios. Después, borrar ese firmware de ejemplo: expone video sin autenticación.

### Etapa 1 — Te sigue con la mirada
- Firmware propio `firmware/camara/`: detección de caras a bordo (`esp-dl` / ejemplo de ESP-WHO, QQVGA, ~5 fps). El firmware **no expone stream ni ninguna ruta de imagen**.
- Con una cara detectada, calcula el ángulo horizontal y le manda al robot `POST /cmd` con el texto `cabeza N` y la cabecera `x-token`. Limitar a ~3 órdenes por segundo y moverse solo si el cambio supera ~5°, para que no tiemble.
- En el robot: mientras lleguen órdenes de la cámara, la vida en reposo **no mueve la cabeza** (si no, pelean). Se necesita una orden nueva, p. ej. `mirar N`, que marque "alguien me está mirando" durante ~3 s. Es un cambio pequeño en `robot_rostro.ino`.
- **Listo cuando:** con alguien moviéndose frente al robot, la cabeza lo sigue sin temblar, y vuelve a la vida en reposo cuando ya no hay nadie.

### Etapa 2 — Se despierta cuando llega alguien
- Si el robot está dormido (vida en reposo) y aparece una cara durante >1 s: despierta, cara `feliz` y un saludo corto local (sin servidor).
- Como mucho un saludo cada 10 minutos, para no hablarle a quien pasa varias veces.
- **Listo cuando:** se despierta al sentarse alguien frente a él, y no lo hace con fotos ni con la tele de fondo (probar las dos cosas).

### Etapa 3 — Tarjetas mágicas
- Tarjetas impresas con marcadores ArUco (diccionario 4×4, pocos IDs) que el niño puede decorar alrededor del código.
- La cámara solo decodifica el ID y lo manda al robot. Cada ID dispara una acción local o una frase fija hacia el servidor: cuento, baile, "¿qué hay hoy en mi agenda?", juego.
- Plantilla imprimible en `hardware/tarjetas/`.
- **Listo cuando:** de 20 intentos con buena luz, se reconocen al menos 18 sin falsos disparos.

### Etapa 4 — Apoyo a las rutinas
- La agenda (que ya corre local) puede preguntar "¿hay alguien?" a la cámara: p. ej., la alarma de la mañana sigue sonando hasta que hay una cara, o la rutina de tareas empieza cuando alguien se sienta.
- La decisión sigue siendo de la agenda; la cámara solo responde sí o no.

### Etapa 5 — "¿Qué es esto?" (opcional, la activa un adulto)
- Solo con el toque largo y una frase explícita ("mira esto"). La cámara toma **una** foto, la manda por HTTPS al servidor, y el servidor la reenvía a un modelo con visión y la descarta.
- Apagada por defecto (`VISION_ACTIVA=0`), con un interruptor en el panel de padres, y cada uso queda en la auditoría.
- **Antes de empezar:** verificar que los términos del proveedor permiten el uso con menores, recortar o desenfocar caras antes de enviar (si es viable a bordo), y actualizar `docs/privacidad.md`.

## Riesgos y dudas abiertas
- **Token en la LAN:** `POST /cmd` va por HTTP dentro de la casa, así que el token viaja en claro por el Wi-Fi local. Es aceptable en la red de casa, pero no en una red compartida.
- **Calor y consumo:** la ESP32-CAM se calienta con el Wi-Fi siempre activo. Medir la temperatura dentro de la cabeza en la etapa 0.
- **Rendimiento:** el ESP32 clásico detecta caras lento. Si no llega a ~5 fps, la alternativa es la variante con ESP32-S3 (OV3660).
- **Luz:** la OV2640 rinde mal con poca luz; las etapas 2 y 4 deben fallar "callando", no despertando por error.
- **Actualizaciones:** el nodo de la cámara necesitará su propia OTA firmada (por ahora, por cable).
