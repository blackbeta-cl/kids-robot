@echo off
REM Compila y corre las pruebas de la logica de redes Wi-Fi en el PC (no usa la placa).
REM Necesita un g++ en el PATH (por ejemplo WinLibs/MinGW: winget install BrechtSanders.WinLibs.POSIX.UCRT).
setlocal
cd /d "%~dp0"
where g++ >nul 2>nul
if errorlevel 1 (echo No hay g++ en el PATH. Ver el comentario de este archivo. & exit /b 2)
g++ -std=c++17 -Wall -Wextra -o test_redes.exe test_redes.cpp
if errorlevel 1 (echo ERROR al compilar las pruebas & exit /b 1)
"%~dp0test_redes.exe"
exit /b %errorlevel%
