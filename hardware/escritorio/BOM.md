# Lista de materiales — escritorio v1

Precios de referencia en USD (2026), sin envío. Lo importante es que casi todo
lo electrónico ya lo tienes; esta versión agrega el parlante, el micrófono, el
tacto y la energía.

## Ya tienes

| Pieza | Nota |
|---|---|
| ESP32 DevKit 38 pines | El del robot actual |
| OLED SSD1306 128×64 (0,96") | El del robot actual |
| Servo SG90 | El del cuello actual |
| Fuente 5 V / cable USB | Para programar y probar |

## Para el audio y el tacto

| Pieza | Cant. | US$ | Nota |
|---|---:|---:|---|
| Parlante 40 mm, 3 W, 8 Ω | 1 | 3 | Entra en el frente de la cabeza |
| Amplificador I2S MAX98357A | 1 | 5 | Para el parlante; etapa de audio |
| Micrófono I2S INMP441 | 1 | 4 | Costado izquierdo |
| Sensor táctil TTP223 | 2 | 2 | Techo; uno de repuesto |
| Espuma fina + silicona | 1 | 4 | Sellar parlante y micrófono |
| Cable 4/6 hilos flexible | 1 m | 3 | Para pasar por el cuello |

> El audio es opcional para esta primera prueba: la voz actual sigue en el PC.
> El espacio y los agujeros ya están hechos.

## Energía

### Opción A: power bank (la más simple)

| Pieza | Cant. | US$ | Nota |
|---|---:|---:|---|
| Power bank 5 V/2 A, ~100 × 62 × 16 mm | 1 | 12 | Cabe en el cajón; se carga sacándolo |
| Breakout USB o cable USB a bornera | 1 | 3 | Para sacar 5 V/GND |
| Interruptor 3 A | 1 | 2 | En serie con el 5 V |
| Capacitor 470 µF | 1 | 1 | Cerca del servo |
| Cable 22 AWG rojo/negro | 1 m | 2 | Alimentación |

### Opción B: pack 2S (más autonomía)

| Pieza | Cant. | US$ | Nota |
|---|---:|---:|---|
| Pack 2S 18650 3500 mAh + BMS 8 A | 1 | 20 | 78 × 40 × 22 mm |
| Cargador TP5100 (2S, 2 A) | 1 | 4 | Con jack DC |
| Buck 5 V 3 A (XL4015/MP1584) | 1 | 5 | Para ESP32, servo y audio |
| Fusible 5 A + portafusible | 1 | 3 | En el positivo |
| Interruptor 6 A | 1 | 2 | Corte general |
| Jack DC + conector XT30 | 1 | 5 | Carga y pack removible |
| Capacitor 470 µF + 1000 µF | 2 | 2 | Riel de 5 V y entrada del buck |

## Tornillería y varios

| Pieza | Cant. | US$ | Nota |
|---|---:|---:|---|
| Inserto roscado M3 (4,2 × 5 mm) | 8 | 3 | Si quieres reforzar la tapa/panel |
| M3 × 8 | 8 | 2 | Panel trasero, tapa |
| M3 × 10 | 8 | 2 | Tapa de la base, panel |
| M3 × 12 | 4 | 1 | Cabeza al plato |
| M2,5 × 6 | 4 | 2 | Orejas del SG90 |
| M2 × 6 | 6 | 2 | OLED y cuerno |
| Tuercas M3 + arandelas | 10 | 2 | Opcional |
| Patas de goma 20 mm | 4 | 2 | En los alojamientos de la base |
| Filamento PLA+ o PETG | 400 g | 8 | ~350 g de piezas |
| Bridas 100 mm | 5 | 1 | ESP32 en la bandeja |
| Velcro | 1 | 2 | Batería en el cajón |

## Herramientas

Soldador, estaño, multímetro, llaves Allen 2/2,5/3 mm, calibre, alicate,
crimpadora. Si no tienes impresora, manda los STL a imprimir en PLA+/PETG
con 4 perímetros y 20–25 % de relleno.

## Costo aproximado

| Versión | US$ |
|---|---:|
| Solo mecánica + servo + OLED + ESP32 (ya tienes) | 15–25 |
| Con audio y tacto | 30–40 |
| Con power bank | 40–55 |
| Con pack 2S + buck + cargador | 55–80 |

No incluye impresora, herramientas ni envío. La impresión en un servicio
puede costar US$ 15–30 por las ~10 h y 350 g.
