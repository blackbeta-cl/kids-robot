# publicar.ps1 — compila el firmware, lo firma y lo publica para la OTA desde el servidor (se ejecuta en tu PC, no en la placa).
# En Linux/CI se usa publicar.sh (mismo formato de manifiesto y de firma).
# Uso:  .\publicar.ps1 -SoloLocal     genera ..\..\server\firmware\ (app.bin + version.json) para probar el servidor en este PC
#       .\publicar.ps1                 además lo copia al servidor con scp (primero app.bin, al final version.json)
# Antes de publicar: sube FIRMWARE_VERSION en estado.h (el robot solo actualiza a una versión MAYOR).
# La copia al servidor cambia el servidor: hazla solo si es el tuyo y sabes lo que publicas.
# Variables para el scp (no se guardan en ningún archivo del repo):
#   $env:ROBOT_SSH_LLAVE   ruta de la llave privada      $env:ROBOT_SSH_DESTINO  p. ej. usuario@tu-servidor:/opt/kids-robot/firmware (la carpeta FIRMWARE_DIR del servidor)
param([switch]$SoloLocal)
$ErrorActionPreference = 'Stop'
$aqui = Split-Path -Parent $MyInvocation.MyCommand.Path
$fqbn = 'esp32:esp32:esp32s3:PSRAM=opi,FlashSize=16M,PartitionScheme=app3M_fat9M_16MB,CDCOnBoot=default'
$salida = Join-Path $aqui 'build'
$destinoLocal = Join-Path $aqui '..\..\server\firmware'

$linea = Select-String -Path (Join-Path $aqui 'estado.h') -Pattern '#define FIRMWARE_VERSION "([^"]+)"'
if (-not $linea) { throw 'No encuentro FIRMWARE_VERSION en estado.h' }
$version = $linea.Matches[0].Groups[1].Value
Write-Host "=== Compilando v$version ==="
& arduino-cli compile -b $fqbn --output-dir $salida $aqui
if ($LASTEXITCODE -ne 0) { throw 'Falló la compilación' }

$bin = Join-Path $salida 'robot_rostro.ino.bin'
$bytes = (Get-Item $bin).Length
$sha = (Get-FileHash $bin -Algorithm SHA256).Hash.ToLower()
# Firma ECDSA P-256 (SHA-256) del texto "kids-robot-fw:<version>:<sha256>" con tu clave privada (nunca va al servidor ni al repositorio).
# El robot solo instala firmware cuyo manifiesto traiga una firma válida para esa versión y ese contenido.
$clave = if ($env:ROBOT_FIRMA_CLAVE) { $env:ROBOT_FIRMA_CLAVE } else { Join-Path $env:USERPROFILE '.kids-robot\firma-privada.pem' }
if (-not (Test-Path $clave)) { throw "No encuentro la clave de firma ($clave). Sin ella el robot rechaza el firmware (ver docs/firmware.md)." }
$openssl = if (Get-Command openssl -ErrorAction SilentlyContinue) { 'openssl' } else { 'C:\Program Files\Git\usr\bin\openssl.exe' }
$mensaje = Join-Path $salida 'firma-mensaje.txt'
$firmaDer = Join-Path $salida 'firma.der'
[IO.File]::WriteAllText($mensaje, "kids-robot-fw:${version}:${sha}", (New-Object Text.UTF8Encoding($false)))
& $openssl dgst -sha256 -sign $clave -out $firmaDer $mensaje
if ($LASTEXITCODE -ne 0) { throw 'Falló la firma con openssl' }
$firma = ([BitConverter]::ToString([IO.File]::ReadAllBytes($firmaDer)) -replace '-', '').ToLower()
$manifiesto = @{ version = $version; bytes = $bytes; sha256 = $sha; firma = $firma } | ConvertTo-Json -Compress

New-Item -ItemType Directory -Force $destinoLocal | Out-Null
Copy-Item $bin (Join-Path $destinoLocal 'app.bin') -Force
[IO.File]::WriteAllText((Join-Path $destinoLocal 'version.json'), $manifiesto, (New-Object Text.UTF8Encoding($false)))   # UTF-8 sin BOM
Write-Host "Listo en $((Resolve-Path $destinoLocal).Path): v$version, $bytes bytes, sha256 $sha"
if ($SoloLocal) { return }

if (-not $env:ROBOT_SSH_LLAVE -or -not $env:ROBOT_SSH_DESTINO) { throw 'Define ROBOT_SSH_LLAVE y ROBOT_SSH_DESTINO (ver el encabezado) o usa -SoloLocal' }
Write-Host "=== Copiando al servidor ($env:ROBOT_SSH_DESTINO) ==="
& scp -i $env:ROBOT_SSH_LLAVE (Join-Path $destinoLocal 'app.bin') "$env:ROBOT_SSH_DESTINO/app.bin"
if ($LASTEXITCODE -ne 0) { throw 'Falló scp de app.bin' }
& scp -i $env:ROBOT_SSH_LLAVE (Join-Path $destinoLocal 'version.json') "$env:ROBOT_SSH_DESTINO/version.json"
if ($LASTEXITCODE -ne 0) { throw 'Falló scp de version.json' }
Write-Host "Publicado v$version. El robot lo verá en su próxima consulta (cada ~10 min)."
