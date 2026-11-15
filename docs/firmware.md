# Firmware de la placa

Código en [`firmware/robot_rostro/`](../firmware/robot_rostro). Para ESP32-S3 (probado con la **N16R8**: 16 MB de flash y 8 MB de PSRAM octal).

## Hardware y pines

| Módulo | Pin del módulo | GPIO / destino |
|---|---|---|
| OLED 0,96" SSD1306 I2C (0x3C) | SDA / SCL | **8 / 9**; VCC a 3V3 (nunca 5 V), GND |
| Servo SG90 (cuello) | señal | **13**; rojo a 5 V, marrón/negro a GND |
| INMP441 (micrófono) | SCK / WS / SD | 4 / 5 / 6; VDD a 3V3 (nunca 5 V), GND y L/R a GND |
| MAX98357A (amplificador) | BCLK / LRC / DIN | 15 / 16 / 17; VIN a 5 V, GND; SD y GAIN libres |
| TTP223 (sensor táctil, "hablar") | OUT | **14**; VCC a 3V3, GND |
| Condensador 470 µF | + / − | + a VIN y − a GND del MAX98357A |

- **Evita** los GPIO 35–37 (PSRAM octal: cuelgan la placa), 19–20 (USB nativo), TX/RX (puerto de programación), 0/3/45/46 (arranque) y 48 (LED RGB de la placa).
- **Nunca** cablees con el USB conectado. Reparte 3V3/5V/GND con un riel de la protoboard.
- La placa tiene dos USB-C: se programa por el del **chip puente CH343** ("USB-Enhanced-SERIAL"). Mantén conectado solo un cable.
- Los sketches de [`firmware/pruebas/`](../firmware/pruebas) prueban cada pieza por separado (micrófono, amplificador, tacto).

## Opción A — Grabar el binario de una release (sin compilar)

Descarga de la [última release](https://github.com/blackbeta-cl/kids-robot/releases/latest) `kids-robot-vX.Y.Z.merged.bin` y verifica `SHA256SUMS`. Es la imagen completa (arranque + particiones + aplicación) para la ESP32-S3 de 16 MB.

```bash
pip install esptool
esptool.py --chip esp32s3 --port COM7 --baud 460800 write_flash 0x0 kids-robot-vX.Y.Z.merged.bin
```

(Cambia `COM7` por tu puerto, p. ej. `/dev/ttyACM0` en Linux.) Si se queda en "Connecting...": mantén BOOT, pulsa RST y suelta BOOT.

Después, **configura el robot por cable** (monitor serie a 115200 baudios, terminador "Nueva línea"):

```text
servidor robot.tu-dominio.com        # tu servidor (HTTPS, puerto 443). Para otro puerto: servidor host:8443
token LA-CLAVE-QUE-PUSISTE-EN-ROBOT_TOKEN
```

El robot se reinicia solo tras cada comando. Para el Wi-Fi, ver abajo ("Conectar al Wi-Fi"). Los binarios de las releases se compilan con **HTTPS** y con la zona horaria **UTC**; si necesitas otra zona, compila tú (opción B).

> Los binarios de las releases verifican el firmware que bajan por OTA contra la clave pública del proyecto original (`firma_publica.h`). Si quieres OTA con **tu** firmware, haz tu propio build con tu propia clave (más abajo).

## Opción B — Compilar tú

```bash
arduino-cli config add board_manager.additional_urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core update-index
arduino-cli core install esp32:esp32@3.3.12
arduino-cli lib install "Adafruit SSD1306@2.5.17" "Adafruit GFX Library@1.13.0" "Adafruit BusIO@1.17.4" "ArduinoJson@7.4.3"
```

Configuración local (ninguno de estos archivos se sube a git):

```bash
cd firmware/robot_rostro
cp wifi_config.example.h wifi_config.h     # Wi-Fi de desarrollo, TOKEN_ROBOT, OTA_CLAVE (opcionales)
cp voz_config.example.h voz_config.h       # servidor por defecto (VOZ_PC_IP), HTTPS/HTTP, zona horaria
```

Compilar y subir (FQBN verificado):

```bash
FQBN="esp32:esp32:esp32s3:PSRAM=opi,FlashSize=16M,PartitionScheme=app3M_fat9M_16MB,CDCOnBoot=default"
arduino-cli compile -b "$FQBN" firmware/robot_rostro
arduino-cli upload  -b "$FQBN" -p COM7 firmware/robot_rostro
```

En Windows, `firmware\robot_rostro\subir.bat` hace lo mismo (`subir.bat compilar`, `subir.bat monitor`, `subir.bat ota IP` para subir por Wi-Fi con `OTA_CLAVE`). El puerto se toma de la variable `ROBOT_PUERTO` (por defecto COM7).

Importante en las opciones de la placa: **PSRAM = OPI PSRAM** (no QSPI: puede dejar la placa en bucle de reinicios), Flash 16 MB, USB CDC On Boot = Disabled. El servo usa el PWM nativo (`ledcAttach`), **no** la librería ESP32Servo (se cuelga en la S3).

## Conectar al Wi-Fi (portal cautivo)

El robot funciona solo en redes de **2,4 GHz**. Sin redes guardadas, abre un portal: crea la red `Robot-XXXX` (clave aleatoria que muestra en la pantalla), y en la página que se abre eliges tu red y escribes la clave.

- Mantener tocado el sensor al encender: **4 s = abrir el portal**; **10 s = borrar las redes guardadas** (pide confirmación).
- Por cable: `wifi lista`, `wifi agregar NOMBRE|CLAVE`, `wifi olvidar NOMBRE`, `wifi borrar`, `wifi portal`.

## Comandos por el monitor serie

`feliz`, `triste`…, `cabeza 120`, `demo`, `lista`, `wifi`, `vol 30`, `repetir`, `conv`, `version`, `buscar` (busca firmware nuevo ahora), `agenda`, `servidor`, `token`. Las claves de red y del servidor **solo** se pueden poner por cable, no por la red.

## Servidor local de la placa

La placa levanta un servidor HTTP en el puerto 80 (`POST /cmd`, `GET /estado`) que **exige la cabecera `x-token`** con el mismo token; sin token configurado rechaza todo. No lo expongas a internet. La ruta de depuración `GET /mic/audio` (audio del micrófono) está **desactivada** (`MIC_AUDIO_HTTP 0`).

## Actualizaciones por OTA firmadas

1. El robot consulta cada ~10 min `GET /firmware/version` en tu servidor. Si hay una versión **mayor**, y lleva ≥2 min en reposo, muestra una cuenta regresiva de 30 s (toque corto = más tarde; mantener = ya).
2. Descarga `app.bin`, verifica el **SHA-256** y la **firma ECDSA P-256** del manifiesto contra `firma_publica.h`, instala y valida el arranque a los 45 s; si el nuevo firmware se cuelga, vuelve solo al anterior.
3. **Tu propia clave de firma** (obligatorio si haces tu propio build para OTA):

   ```bash
   cd firmware/robot_rostro
   ./generar_clave_firma.sh            # crea ~/.kids-robot/firma-privada.pem y reescribe firma_publica.h
   ```

   Respalda la clave privada. Graba ese firmware una vez por cable (o por OTA local con `subir.bat ota`). Después:

   ```bash
   ./publicar.sh compilar && ./publicar.sh firmar ~/.kids-robot/firma-privada.pem   # genera build/app.bin y build/version.json
   # copia ambos a la carpeta FIRMWARE_DIR de tu servidor (app.bin primero, version.json al final)
   ```

   En Windows: `.\publicar.ps1` (compila, firma y, con `ROBOT_SSH_LLAVE`/`ROBOT_SSH_DESTINO`, copia por `scp`).
4. Sube `FIRMWARE_VERSION` en `estado.h` con cada versión que quieras publicar.

## Datos y privacidad en la placa

El audio se guarda solo en la RAM mientras se graba (máx. 10 s) y se envía a tu servidor. Las redes Wi-Fi y el servidor/token se guardan en la memoria NVS de la placa (la clave de Wi-Fi nunca se imprime). El hardware no tiene telemetría hacia ningún sitio que no sea tu servidor, NTP (`pool.ntp.org`, `time.google.com`, `time.cloudflare.com`) y los servicios que configures.
