@echo off
REM Compila y sube robot_rostro a la ESP32-S3 (por el USB del chip puente CH343).
REM Uso: subir.bat            -> compila y sube
REM      subir.bat compilar   -> solo compila
REM      subir.bat monitor    -> solo abre el monitor serie
REM      subir.bat ota IP     -> compila y sube POR WI-FI (sin cable; IP = la del robot, la muestra "wifi" por Serial).
REM                              Usa OTA_CLAVE de wifi_config.h. La primera vez Windows pregunta por el firewall:
REM                              permitir en red privada (la placa se conecta de vuelta al PC).
REM Puerto: define ROBOT_PUERTO (p. ej. set ROBOT_PUERTO=COM5) o se usa COM7. Cierra el Arduino IDE (monitor serie incluido) antes de subir.
REM Si se queda en "Connecting...": mantener BOOT, pulsar RST y soltar BOOT.
setlocal
set "FQBN=esp32:esp32:esp32s3:PSRAM=opi,FlashSize=16M,PartitionScheme=app3M_fat9M_16MB,CDCOnBoot=default"
set "PUERTO=%ROBOT_PUERTO%"
if "%PUERTO%"=="" set "PUERTO=COM7"
set "SKETCH=%~dp0"
if "%SKETCH:~-1%"=="\" set "SKETCH=%SKETCH:~0,-1%"

if /i "%1"=="monitor" goto monitor
if /i "%1"=="ota" goto ota

echo === Compilando ===
arduino-cli compile -b %FQBN% "%SKETCH%"
if errorlevel 1 (echo ERROR al compilar & exit /b 1)
if /i "%1"=="compilar" exit /b 0

echo === Subiendo a %PUERTO% ===
arduino-cli upload -b %FQBN% -p %PUERTO% "%SKETCH%"
if errorlevel 1 (echo ERROR al subir. Revisa que el IDE este cerrado y el puerto (ROBOT_PUERTO) & exit /b 1)

:monitor
echo === Monitor serie a 115200 (Ctrl+C para salir) ===
arduino-cli monitor -p %PUERTO% -c baudrate=115200,dtr=off,rts=off
exit /b 0

:ota
set "CLAVE="
for /f tokens^=2^ delims^=^" %%a in ('findstr /b /c:"#define OTA_CLAVE" "%SKETCH%\wifi_config.h"') do set "CLAVE=%%a"
if not defined CLAVE (echo Falta OTA_CLAVE en wifi_config.h & exit /b 1)
set "IP=%2"
if "%IP%"=="" (echo Uso: subir.bat ota IP-DEL-ROBOT & exit /b 1)
echo === Compilando ===
arduino-cli compile -b %FQBN% --output-dir "%SKETCH%\build" "%SKETCH%"
if errorlevel 1 (echo ERROR al compilar & exit /b 1)
echo === Subiendo por Wi-Fi a %IP% (pantalla del robot: Actualizando...) ===
"%LOCALAPPDATA%\Arduino15\packages\esp32\hardware\esp32\3.3.12\tools\espota.exe" -r -i %IP% -p 3232 --auth=%CLAVE% -f "%SKETCH%\build\robot_rostro.ino.bin"
if errorlevel 1 (echo ERROR al subir por Wi-Fi. Revisa la IP del robot, que este encendido y el firewall & exit /b 1)
echo === Listo. Comprueba la version en http://%IP%/estado (con la cabecera x-token) ===
exit /b 0
