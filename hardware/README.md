# Hardware

Diseños CAD paramétricos (OpenSCAD) para imprimir en 3D la carcasa del robot. Son **prototipos sin imprimir ni probar**: varias medidas de los módulos son típicas y dicen *MEDIR* en `parametros.scad`; mídelas con pie de metro antes de imprimir.

| Carpeta | Qué es |
|---|---|
| [`redondo/`](redondo/LEEME.md) | Cuerpo redondeado con la cabeza como botón gigante (microswitch en vez de sensor táctil), con espacio para cámara ESP32-CAM, PIR y sensor de distancia VL53L0X |
| [`escritorio/`](escritorio/LEEME.md) | Cabeza sobre una base con batería y servo: el prototipo más simple para empezar |

Los STL **no se versionan**: se generan con OpenSCAD desde cada carpeta (`exportar_stl.bat` en Windows o `python exportar_stl.py`). Los pines y el cableado están en la documentación de [`firmware/`](../docs/firmware.md).
