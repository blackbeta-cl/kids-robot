# Privacidad y datos de menores — detalle técnico

Complementa el aviso del [README](../README.md). Describe **qué datos maneja el software y por dónde pasan**, para que quien lo despliega pueda decidir con información. No es asesoría legal.

## Flujo de datos

1. **Placa → tu servidor.** Mientras se mantiene el sensor táctil, la placa graba el micrófono (16 kHz, mono, máx. 10 s) en su memoria y, al soltar, lo envía por HTTPS a `POST /voz/stream`. El audio no se guarda en la placa más allá de la grabación en curso.
2. **Voz → texto.**
   - `STT_PROVEEDOR=local` (por defecto): Whisper (`faster-whisper`) corre **en tu servidor**. El audio no sale de él.
   - `STT_PROVEEDOR=groq`: el servidor **reenvía el audio a Groq** (`api.groq.com`). Solo con `GROQ_API_KEY`. Si falla, vuelve a Whisper local.
3. **Texto → respuesta.** El servidor envía al **LLM que configuraste en `LLM_URL`** la frase del niño junto con las instrucciones del robot (`server/persona.py`), el **apodo y la edad** del niño (no la fecha de nacimiento exacta), los últimos turnos de la conversación y los **recuerdos que los padres aprobaron**.
4. **Respuesta → voz.** El texto de la respuesta se sintetiza con `edge-tts`, que usa un **servicio en línea de Microsoft**. Recibe solo el texto que dice el robot.
5. **Memoria automática.** Si `EXTRAER_AUTOMATICO=1` (valor por defecto), tras unos minutos de conversación el servidor envía fragmentos al LLM para **proponer hechos** ("le gustan los dinosaurios"). Quedan **pendientes** hasta que un adulto los aprueba en el panel; mientras no se aprueban no se usan. Se apaga con `EXTRAER_AUTOMATICO=0` o `MEMORIA_ACTIVA=0`.

## Qué guarda tu servidor

| Dato | Dónde | Notas |
|---|---|---|
| Perfil (apodo, fecha de nacimiento, gustos) | `datos/memoria.db` | Lo edita un adulto en el panel. Al modelo solo llegan apodo y edad |
| Recuerdos (hechos y rasgos) y su estado | `datos/memoria.db` | Revisables y borrables desde el panel |
| Personalidad del robot | `datos/memoria.db` | Editable en el panel |
| Agenda (recordatorios, alarmas, rutinas, cumpleaños) | `datos/memoria.db` | |
| Usuarios del panel (hash scrypt), sesiones, intentos de login, auditoría | `datos/memoria.db` | Las contraseñas nunca se guardan en claro |
| Conversación reciente | **Solo en RAM** | Se descarta tras `MEMORIA_MINUTOS` (10 por defecto) sin hablar o al reiniciar |
| Audio | Archivos temporales mientras se procesa | El servidor no lo guarda de forma permanente |
| Registros del servicio (`journalctl`) y de Caddy | Disco del servidor | Revisa su rotación. La configuración de ejemplo no guarda `X-Token`, cookies ni `Authorization` |

## Recomendaciones para quien despliega

- Pon la carpeta `datos/` en un disco cifrado o, al menos, con permisos `700`; respáldala de forma cifrada.
- Usa un LLM cuyos términos permitan expresamente el uso con menores, o uno local. Lee los términos de **cada** proveedor (LLM, Groq si lo activas, Microsoft/edge-tts).
- Informa a la familia de qué se envía a quién y obtén el consentimiento de los tutores.
- No pongas en las instrucciones del robot ni en los recuerdos datos como dirección, colegio, teléfono o apellidos: el robot tiene reglas para no pedirlos, pero lo que tú escribas en la personalidad viaja al LLM.
- Mantén el servidor actualizado y expuesto solo por HTTPS (ver [servidor.md](servidor.md)).
- Si un niño dijo algo que no debía quedar registrado: bórralo desde el panel de padres y revisa los registros del servidor.

## Lo que este repositorio NO contiene

Ningún dato de ninguna familia: ni perfiles, ni personalidades, ni grabaciones de voz, ni bases de datos, ni claves. Los ejemplos de `server/datos.example/` son ficticios. **Si trabajas con una copia del proyecto y guardas datos reales, asegúrate de que `datos/`, `.env` y cualquier grabación estén en `.gitignore` (ya lo están) antes de hacer commit.**
