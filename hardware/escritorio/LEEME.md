# Kids Robot — versión escritorio v1

Primer prototipo simple: **una cabeza sobre una base**, sin ruedas ni cuerpo.
Usa lo que ya tienes (ESP32, OLED y SG90) y reserva espacio para el parlante,
el micrófono y el sensor táctil. La base lleva la batería/power bank y el servo
de giro; la cabeza lleva la pantalla, el ESP32 y los módulos de audio/tacto.

> **Estado:** v1 para probar. El CAD y los STL están generados y revisados en
> OpenSCAD, pero **no está impreso ni probado**. Los encajes son nominales:
> imprime el cupón de calibración y mide tus piezas antes de imprimir todo.

El cuerpo tipo WALL-E de `cuerpo\` queda como etapa 2. Este escritorio es el
que conviene probar primero.

## Medidas

| Qué | mm |
|---|---|
| Base (ancho × fondo × alto) | 130 × 130 × 60 |
| Cabeza (ancho × fondo × alto) | 110 × 70 × 82 |
| Alto total | 152 |
| Plato giratorio | 70 (labio 80) |
| Pantalla | OLED SSD1306 128×64 (0,96"), ventana 24 × 12,5 |
| Parlante | 40 mm, 3 W, 8 Ω |
| Micrófono | INMP441 I2S (14 × 14) |
| Tacto | TTP223 detrás de una almohadilla de 30 mm |
| ESP32 | DevKit 38 pines, vertical en el panel trasero |
| Servo | SG90 / MG90S, giro ±80° |
| Cajón de batería | 111 × 68 × 28 (interior ~105 × 63 × 25) |
| Peso estimado | 350–500 g según batería |

## Archivos

```
escritorio/
├── escritorio.scad          CAD paramétrico y selector
├── parametros.scad          todas las medidas
├── exportar_stl.py          exporta las 7 piezas + calibración
├── stl/                     (se genera con exportar_stl; no está en el repo)
├── planos/
│   ├── conjunto.svg         plano frontal, lateral y superior
│   └── generar_planos.py    regenera el plano
├── vista_ensamble.png       vista 3D del ensamble
├── vista_3d.scad            vista auxiliar para regenerar la imagen
├── BOM.md                   lista de materiales
└── LEEME.md                 este archivo
```

Las 7 piezas son: base, tapa de la base, cajón, plato giratorio, cabeza,
panel trasero y rejilla. Más el cupón de calibración.

## Qué lleva cada parte

- **Base:** servo SG90 centrado, anillo de apoyo, plato giratorio, cajón
  deslizante para la batería, interruptor y conector de carga atrás.
- **Cabeza:** OLED al frente, parlante de 40 mm abajo, micrófono en el
  costado izquierdo, almohadilla táctil de 30 mm arriba, ESP32 vertical en el
  panel trasero, USB accesible por el panel.
- **Cuello:** el servo gira la cabeza ±80°; los cables bajan por un agujero
  a 24 mm del eje y una ranura en arco en la tapa de la base. No hay slip
  ring: deja un lazo de servicio.

## Antes de imprimir

1. **Mide tus piezas:**
   - OLED 27,3 × 27,3 mm, agujeros a 23,5 mm (algunos módulos traen 24,5 o
     ninguno; si no coinciden, cambia `OLED_AGUJ` y reexporta).
   - SG90 con orejas a 27,8 mm y cuerpo 22,8 × 12,2 × 22,5 mm.
   - Parlante de 40 mm con o sin orejas; el anillo está pensado para pegarlo
     con silicona.
   - Power bank de hasta 100 × 62 × 16 mm o pack 2S 18650 de 78 × 40 × 22 mm.
2. **Imprime `stl/calibracion.stl`:** agujeros de 1,8 / 2,1 / 2,2 / 2,5 /
   2,7 / 3,4 / 4,2 mm y el alojamiento del inserto M3. Prueba un inserto en
   un resto.
3. **Imprime `plato_giro` y `tapa_base`:** comprueba que el servo entra, que
   las orejas apoyan y que el plato gira libre sobre el anillo.
4. **Imprime la cabeza después**, cuando ya sepas que el servo y la OLED
   calzan.

## Impresión

| Pieza | Cant. | Orientación (STL ya orientado) | Nota | Tiempo |
|---|---:|---|---|---|
| base | 1 | piso abajo | Sin soportes; el hueco del interruptor puentea poco | 3 h |
| tapa_base | 1 | plano | Anillo del cuello hacia arriba | 0,8 h |
| cajon | 1 | fondo abajo | Frente y uñero; sin soportes | 1 h |
| plato_giro | 1 | girado, labio arriba | 2 agujeros del cuerno y 4 de la cabeza | 0,6 h |
| cabeza | 1 | frente abajo | Sin soportes; 70 mm de alto | 3 h |
| tapa_cabeza | 1 | plano, cara exterior abajo | Bandeja del ESP32 arriba | 0,8 h |
| rejilla | 1 | plano | Entra en el agujero de 40 mm | 0,5 h |
| calibracion | 1 | plano | Primero | 0,2 h |

Totales: **~10 h** y **300–400 g** de PLA+ o PETG. Configuración: boquilla
0,4 mm, capa 0,2 mm, 4 perímetros, 20–25 % de relleno (giroide). Brim de 5 mm
en base y cabeza. Sin soportes.

## Armado

### 1. Base y servo

1. Sujeta el SG90 a la tapa de la base desde arriba: las orejas apoyan en la
   tapa y van con 2 M2,5 × 6. El cuerpo queda colgando dentro de la base.
2. Coloca el anillo de apoyo (ya impreso en la tapa) y comprueba que el plato
   gira libre.
3. Atornilla la tapa a la base con 4 M3 × 10.
4. Monta el interruptor y el conector de carga en los huecos traseros.

### 2. Batería o power bank

El cajón está pensado para dos opciones:

- **Power bank (lo más simple):** uno de 5 V/2 A, 100 × 62 × 16 mm. Va en el
  cajón, con un cable USB hasta un pequeño breakout de 5 V o directo al
  ESP32. La batería se carga sacando el cajón.
- **Pack 2S 18650:** 78 × 40 × 22 mm en el cajón. El buck de 5 V y el TP5100
  van en el espacio detrás del cajón. Pon fusible de 5 A, interruptor y jack
  DC en la parte trasera.

Sujeta la batería con velcro o una correa por las ranuras del cajón. Deja el
cable con holgura en la ranura trasera del cajón.

### 3. Plato y cabeza

1. Monta el cuerno en el servo y atorníllalo con su tornillo central.
2. Atornilla el plato al cuerno con 2 M2 × 6 desde arriba. Hazlo **antes** de
   poner la cabeza: la cabeza tapa la parte superior del plato.
3. Atornilla la cabeza al plato con 4 M3 × 12 desde abajo. Los tornillos pasan
   por el plato y entran en los jefes del fondo de la cabeza.
4. Pasa los cables por el agujero de 12 mm del plato y de la cabeza antes de
   cerrar.

### 4. Cabeza

1. **OLED:** 4 M2 × 6 en los postes interiores. La ventana de 24 × 12,5 deja
   ver el área activa; el módulo queda 4 mm detrás de la cara interior.
2. **Parlante:** pégalo con silicona contra el anillo interior de 46 mm, con
   una junta de espuma; la rejilla de 39,4 mm entra a presión en el agujero.
3. **Micrófono:** INMP441 pegado por dentro contra el agujero de 2 mm del
   costado izquierdo, con espuma. Aléjalo del parlante (está en el frente).
4. **Tacto:** TTP223 pegado por dentro de la almohadilla del techo, entre los
   cuatro postes; el cable sale hacia el panel.
5. **ESP32:** apóyalo en la bandeja del panel trasero, con el USB mirando
   hacia el agujero de 12 × 5. Sujétalo con una brida por las ranuras.
6. **Panel trasero:** 4 M3 × 10. Antes, conecta todo y deja un lazo de cables.

### 5. Cables y giro

El cable de la cabeza baja por el agujero del plato (24 mm detrás del eje),
atraviesa la ranura en arco de la tapa de la base y llega al interruptor, al
buck y al servo. Deja un lazo: el giro es ±80° y no hay slip ring. No lo
aprietes contra la bisagra.

## Electrónica

### Lo que ya tienes

| Función | GPIO | Nota |
|---|---:|---|
| OLED SDA / SCL | 8 / 9 | ESP32-S3; ya está en el firmware actual |
| Servo de giro | 13 | SG90 a 5 V |
| Táctil TTP223 OUT | 14 | Entrada digital (RTC: puede despertar de deep sleep). TTP223 a 3,3 V, sin pull-up |
| 5 V / GND | — | Del buck o del power bank |
| USB | — | Programación por el panel trasero |

### Audio (reservado, para la siguiente etapa)

El firmware actual no usa audio: la voz sigue en el PC (micrófono y parlante
del PC). La cabeza tiene el espacio y los agujeros para agregarlo:

- **Parlante** de 40 mm + **MAX98357A** I2S (3 W). Alimentación 5 V, salida
  al parlante; no pongas el negativo a GND.
- **Micrófono** INMP441 I2S. Alimentación 3,3 V.
- Pines en la ESP32-S3: micrófono SCK 4, WS 5, SD 6; amplificador BCLK 15,
  LRC 16, DIN 17. Van en puertos I2S distintos (micrófono y parlante no
  comparten reloj). Probados con los sketches de `robot\prueba_microfono` y
  `robot\prueba_amplificador`.
- Con el audio en la cabeza, el robot puede hablar solo si el modelo corre en
  el PC o en una Raspberry Pi; el ESP32 no ejecuta el LLM.

### Alimentación

- **Power bank:** 5 V/2 A; alimenta el ESP32 y el servo. Pon 470 µF cerca del
  servo. El USB del ESP32 queda libre para programar.
- **2S:** pack 2S con BMS, fusible 5 A, interruptor y buck 5 V/3 A. El TP5100
  y el jack DC van atrás. No cargues sin supervisión.
- **Servo:** el SG90 en movimiento lento consume poco; si lo fuerzas, el
  buck/power bank puede caer. No dejes el cuello trabado.

## Módulos futuros

- El cajón acepta un power bank o un pack 2S sin cambiar la base.
- El panel trasero y la bandeja del ESP32 son el punto de acceso para
  programar y para agregar una Raspberry Pi más adelante.
- El agujero del micrófono y la almohadilla táctil ya están; el parlante
  también. Falta el audio y el firmware.
- La cabeza no tiene cámara ni inclinación: esta versión es solo giro. La
  cámara y el tilt son la siguiente iteración.
- El cuerpo con orugas de `cuerpo\` sigue disponible para la etapa 2.

## Limitaciones honestas

- **No está impreso ni probado.** Es un v1; los encajes pueden pedir ajustes
  de 0,2–0,5 mm.
- El ESP32 vertical en el panel deja poco espacio para los cables; armalo con
  calma y prueba el cierre antes de cerrar la tapa.
- El parlante va pegado, no atornillado; el sonido sale por la rejilla y la
  caja no está sellada. El micrófono está en el costado para separarlo, pero
  puede acoplar; usa AEC o pulsar-para-hablar.
- La OLED de 0,96" es chica para una cabeza de 11 cm; una TFT de 2,4" es el
  siguiente salto y requiere cambiar el bisel y el firmware.
- El SG90 alcanza para esta cabeza liviana; si agregas cámara, Pi o brazos,
  pasa a MG90S o a un servo más grande.
- El power bank puede apagarse solo si el consumo es muy bajo; revisa que
  aguante el ESP32. Si no, usa el pack 2S con buck.
- El giro es ±80° y no hay slip ring; el lazo de cables es obligatorio.
- No hay cámara, inclinación ni ruedas en esta versión.

## Siguientes pasos

1. Imprime calibración, tapa de la base y plato; prueba el servo.
2. Imprime base y cajón; monta la batería/power bank y el interruptor.
3. Imprime la cabeza y el panel; monta OLED, parlante, micro y tacto.
4. Prueba el giro y la OLED con el firmware actual.
5. Después: audio I2S, wake word, cámara/tilt o el cuerpo WALL-E.

## Seguridad

- Li-ion: BMS, fusible, cables gruesos, carga supervisada. No dejes el pack
  conectado semanas.
- El servo en stall calienta; el firmware debe limitar el rango y no dejarlo
  forcejeando.
- La base es pesada por la batería; no la pongas al borde de la mesa.
