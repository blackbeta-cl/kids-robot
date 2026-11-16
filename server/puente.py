import entorno  # noqa: F401  (carga server/.env antes de leer la configuración)
import asyncio
import ctypes
import difflib
import hmac
import io
import json
import os
import queue
import re
import sys
import tempfile
import threading
import time
import uuid
from collections import deque
from urllib.parse import quote
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
import serial
import serial.tools.list_ports
import requests
import uvicorn

from voz_robot import preparar_wav, reproducir, sintetizar
from modo_nino import RESPUESTA_BLOQUEO, revisar_entrada, revisar_salida
from pronunciacion import preparar_para_voz
import agenda
import intenciones_agenda
import memoria
import persona
from persona import ahora_robot, construir_sistema

# La consola de Windows usa cp850/cp1252 y revienta al imprimir emojis.
for _flujo in (sys.stdout, sys.stderr):
    if hasattr(_flujo, "reconfigure"):
        try:
            _flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# Configuración de FastAPI
app = FastAPI(title="Kids Robot - Servidor Python", version="1.0")

# Habilitar CORS para permitir conexión desde otros dispositivos de la red
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración del Puerto Serie hacia el ESP32
SERIAL_PORT = os.getenv("SERIAL_PORT", "")   # puerto USB de la placa (p. ej. COM7 o /dev/ttyACM0); vacío = modo servidor, sin cable
BAUD_RATE = 115200
arduino = None
_lector_serial = None

# Últimas líneas que dijo el robot. Sirve para confirmar que un comando llegó.
_log_robot = deque(maxlen=200)
_log_lock = threading.Lock()
_log_numero = 0


def _anotar_log(texto):
    global _log_numero
    with _log_lock:
        _log_numero += 1
        _log_robot.append((_log_numero, texto))


def _respuestas_desde(marca, espera=0.35):
    """Devuelve las líneas que el robot dijo después de 'marca'."""
    time.sleep(espera)
    with _log_lock:
        return [t for n, t in _log_robot if n > marca][-4:]


def leer_serial(puerto):
    """Imprime en consola todo lo que el ESP32 escribe por el puerto serie."""
    while puerto.is_open:
        try:
            linea = puerto.readline()          # espera hasta 1 s (timeout del puerto)
        except (serial.SerialException, OSError):
            return
        if linea:
            texto = linea.decode("utf-8", "ignore").rstrip()
            _anotar_log(texto)
            print(f"🤖 {texto}", flush=True)


def conectar_serial():
    global arduino, _lector_serial
    if arduino and arduino.is_open:
        return
    if not SERIAL_PORT:
        print("ℹ️ Sin puerto serie (SERIAL_PORT vacío): modo servidor, el robot se conecta por Wi-Fi.", flush=True)
        return
    try:
        arduino = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        print(f"✅ Puerto serie conectado exitosamente en {SERIAL_PORT}")
    except Exception as e:
        print(f"⚠️ No se pudo abrir el puerto serie en {SERIAL_PORT}: {e}")
        arduino = None
        return

    _lector_serial = threading.Thread(
        target=leer_serial, args=(arduino,), daemon=True, name="serial-reader"
    )
    _lector_serial.start()


def cerrar_serial():
    """Suelta el puerto serie para que no quede ocupado al siguiente arranque."""
    global arduino
    if arduino and arduino.is_open:
        try:
            arduino.close()
            print("🔌 Puerto serie cerrado.")
        except Exception:
            pass


conectar_serial()

# ---------- Voz (TTS con edge-tts, reproducción nativa de Windows) ----------

# Voz de robot infantil: una voz femenina subida de tono y con un toque metálico.
# Se ajusta sin tocar código:
#   VOZ_TTS=es-CL-CatalinaNeural   VOZ_TONO=+35Hz   VOZ_RITMO=+6%   VOZ_ROBOT=0.45
VOZ_TTS = os.getenv("VOZ_TTS", "es-CL-CatalinaNeural")
VOZ_TONO = os.getenv("VOZ_TONO", "+35Hz")          # más agudo = más infantil
VOZ_RITMO = os.getenv("VOZ_RITMO", "+6%")          # un poco más rápido
try:
    VOZ_ROBOT = max(0.0, min(1.0, float(os.getenv("VOZ_ROBOT", "0.45"))))
except ValueError:
    VOZ_ROBOT = 0.45                                # 0 = voz normal, 1 = robot marcado

_cola_voz: "queue.Queue[str]" = queue.Queue()
_hilo_voz = None


def _reproducir(ruta, tipo):
    """Reproduce el audio con la API MCI de winmm. Sin dependencias externas."""
    reproducir(ruta, tipo)


def _trabajador_voz():
    """Sintetiza y reproduce las frases en orden, una tras otra."""
    while True:
        texto = _cola_voz.get()
        if texto is None:
            return
        ruta = os.path.join(tempfile.gettempdir(), f"robot_tts_{uuid.uuid4().hex}.mp3")
        wav = ruta[:-4] + ".wav"
        try:
            preparado = preparar_para_voz(texto)   # "Grrr" -> "groar", "Zzz" -> nada
            if not preparado:
                continue
            sintetizar(preparado, ruta, VOZ_TTS, VOZ_TONO, VOZ_RITMO)
            print(f"🗣️ {texto}", flush=True)
            if VOZ_ROBOT > 0:
                preparar_wav(ruta, wav, VOZ_ROBOT)
                _reproducir(wav, "waveaudio")
            else:
                _reproducir(ruta, "mpegvideo")
        except Exception as e:
            print(f"⚠️ Error de voz: {e}")
        finally:
            for archivo in (ruta, wav):
                try:
                    os.remove(archivo)
                except OSError:
                    pass
            _cola_voz.task_done()


def hablar(texto):
    """Encola una frase para que suene en los parlantes de este PC."""
    global _hilo_voz
    texto = (texto or "").strip()
    if not texto:
        return
    if _hilo_voz is None or not _hilo_voz.is_alive():
        _hilo_voz = threading.Thread(target=_trabajador_voz, daemon=True, name="tts")
        _hilo_voz.start()
    _cola_voz.put(texto)


print(f"🔊 Voz: {VOZ_TTS} · tono {VOZ_TONO} · ritmo {VOZ_RITMO} · robot {VOZ_ROBOT}")


# ---------- Conversación con el modelo ----------
# Las llaves se leen de variables de entorno o de server/.env (fuera de git).
def _leer_env(ruta):
    datos = {}
    try:
        with open(ruta, encoding="utf-8", errors="replace") as archivo:
            for linea in archivo:
                linea = linea.strip()
                if not linea or linea.startswith("#") or "=" not in linea:
                    continue
                clave, valor = linea.split("=", 1)
                datos[clave.strip()] = valor.strip().strip('"').strip("'")
    except OSError:
        pass
    return datos


# .env (junto a este archivo) se lee primero; las variables de entorno del proceso (p. ej. EnvironmentFile de systemd) mandan sobre él.
_ENV = _leer_env(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))


def _config(*nombres, defecto=""):
    """Primer valor que exista entre las variables de entorno y el .env, en el orden dado."""
    for nombre in nombres:
        valor = os.getenv(nombre) or _ENV.get(nombre)
        if valor:
            return valor
    return defecto


# Cualquier API de chat compatible con OpenAI (POST .../chat/completions). Los nombres OPENCODE_* y URL_CHAT
# son los antiguos y siguen funcionando.
CLAVE_MODELO = _config("LLM_API_KEY", "OPENCODE_API_KEY")
# Solo con la clave antigua (OPENCODE_API_KEY) se mantiene el proveedor de siempre por omisión. Con LLM_API_KEY hay que
# decir LLM_URL y LLM_MODEL: así una clave nunca viaja a un proveedor que tú no elegiste.
_LEGADO = bool(_config("OPENCODE_API_KEY")) and not _config("LLM_API_KEY")
MODELO_CHAT = _config("LLM_MODEL", "OPENCODE_MODEL", defecto="beam-free" if _LEGADO else "")
URL_CHAT = _config("LLM_URL", "URL_CHAT", defecto="https://opencode.ai/inference/go/openai/v1/chat/completions" if _LEGADO else "")
if CLAVE_MODELO and not (URL_CHAT and MODELO_CHAT):
    print("⚠️ Hay clave de LLM pero falta LLM_URL o LLM_MODEL: no la envío a ningún sitio. El robot no podrá conversar.", flush=True)
    CLAVE_MODELO = ""
SESION_CHAT = "robot-voz-" + uuid.uuid4().hex
PRESUPUESTO_MODELO_VOZ = float(os.getenv("VOZ_PRESUPUESTO_MODELO", "10"))   # segundos máx. con el modelo, por voz
# beam-free es un modelo que razona: su "pensamiento" (reasoning_content) gasta de los mismos tokens que la
# respuesta. Con 220 se quedaba sin espacio y devolvía la respuesta cortada o vacía (~1 de cada 3 veces en
# la prueba); con 700 sale completa sin tardar más, porque solo gasta el razonamiento que necesita.
CHAT_MAX_TOKENS = int(os.getenv("CHAT_MAX_TOKENS", "700"))


def _respuesta_cortada(texto, motivo=None):
    """True si la respuesta parece cortada a media frase ("Las arañ"): se oiría rota por el parlante."""
    if motivo == "length":
        return True
    limpio = re.sub(r"[^\w.!?…»\")]+$", "", texto.strip())     # sin emojis ni espacios al final
    return len(limpio) < 40 and limpio[-1:] not in tuple(".!?…»\")")

# ---------- Acceso desde la red ----------
# El puente escucha solo en 127.0.0.1 por defecto. Con HOST=0.0.0.0 el robot puede llamar a /voz,
# pero entonces también cualquier equipo de la red. Los clientes de este mismo equipo (asistente de voz,
# scripts locales) siguen entrando sin token; los de la red deben mandar la cabecera
# X-Token con el mismo valor que TOKEN_ROBOT en wifi_config.h (ROBOT_TOKEN en server/.env).
# Sin token configurado, la red queda cerrada.
TOKEN_ROBOT = _config("ROBOT_TOKEN")
_ORIGENES_LOCALES = {"127.0.0.1", "::1", "localhost"}

# La agenda es por familia; cada robot pertenece a una sola. El panel usa su sesión.
FAMILIA_ID = os.getenv("FAMILIA_ID", "1")


# Detrás de un proxy en el mismo equipo (Caddy), TODO llega desde 127.0.0.1: la cabecera X-Forwarded-For
# delata que la petición vino de fuera y entonces también exige token. PUENTE_EXIGIR_TOKEN=1 lo exige a todos.
EXIGIR_TOKEN_A_TODOS = os.getenv("PUENTE_EXIGIR_TOKEN", "") not in ("", "0", "false", "no")


@app.middleware("http")
async def exigir_token_desde_la_red(request: Request, llamar):
    if request.url.path == "/padres" or request.url.path.startswith("/padres/"):
        return await llamar(request)      # el panel de padres usa sesión con login, no X-Token (ver padres_api.py)
    origen = request.client.host if request.client else ""
    viene_de_un_proxy = "x-forwarded-for" in request.headers or "forwarded" in request.headers
    if origen in _ORIGENES_LOCALES and not viene_de_un_proxy and not EXIGIR_TOKEN_A_TODOS:
        return await llamar(request)
    if not TOKEN_ROBOT:
        return JSONResponse(
            {"detail": "El puente no acepta conexiones de la red: falta ROBOT_TOKEN (server/.env)."},
            status_code=403,
        )
    enviado = request.headers.get("x-token", "")
    if not hmac.compare_digest(enviado.encode("utf-8"), TOKEN_ROBOT.encode("utf-8")):
        return JSONResponse({"detail": "Token inválido o ausente (cabecera X-Token)."}, status_code=401)
    return await llamar(request)


# Panel web de padres (perfil y hechos): sub-aplicación propia con login; PANEL_PADRES=0 no la monta.
if os.getenv("PANEL_PADRES", "1") not in ("0", "false", "no"):
    import padres_api
    app.mount("/padres", padres_api.crear_app())

# La personalidad y el perfil vienen de server/datos/ (ver persona.py); sin archivos queda la de siempre.


# ---------- Memoria de la conversación ----------
# Guarda los últimos turnos para poder seguir una conversación ("¿y en qué año?").
# Si pasa mucho rato sin hablarle, se olvida: no queremos que mezcle temas de ayer.
MEMORIA_TURNOS = int(os.getenv("MEMORIA_TURNOS", "3"))        # pares pregunta/respuesta
MEMORIA_MINUTOS = float(os.getenv("MEMORIA_MINUTOS", "10"))

_historial = []
_historial_ultimo = 0.0
_historial_lock = threading.Lock()


def historial_actual():
    """Copia del historial; si quedó viejo, se descarta."""
    global _historial
    with _historial_lock:
        if _historial and time.time() - _historial_ultimo > MEMORIA_MINUTOS * 60:
            _historial = []
        return list(_historial)


def recordar(pregunta, respuesta):
    global _historial_ultimo
    with _historial_lock:
        _historial.extend([
            {"role": "user", "content": pregunta},
            {"role": "assistant", "content": respuesta},
        ])
        sobra = len(_historial) - MEMORIA_TURNOS * 2
        if sobra > 0:
            del _historial[:sobra]
        _historial_ultimo = time.time()
    if MEMORIA_ACTIVA and EXTRAER_AUTOMATICO:
        _extractor.anotar(pregunta, respuesta)


def olvidar():
    global _historial
    with _historial_lock:
        _historial = []
    _extractor.descartar()          # "olvida eso": lo hablado no se convierte en hechos


# ---------- Memoria de hechos (memoria.py): se inyectan solo los aprobados y relevantes ----------
MEMORIA_ACTIVA = os.getenv("MEMORIA_ACTIVA", "1") not in ("0", "false", "no")
EXTRAER_AUTOMATICO = os.getenv("EXTRAER_AUTOMATICO", "1") not in ("0", "false", "no")
EXTRAER_MINUTOS = float(os.getenv("EXTRAER_MINUTOS", "10"))


def _llamar_modelo_para_extraer(mensajes):
    """Una llamada al modelo (sin streaming) para proponer hechos. Corre en un hilo de fondo."""
    if not CLAVE_MODELO:
        raise RuntimeError("falta LLM_API_KEY, LLM_URL o LLM_MODEL")
    r = requests.post(URL_CHAT, headers={"content-type": "application/json",
                                         "authorization": f"Bearer {CLAVE_MODELO}",
                                         "x-opencode-session": SESION_CHAT},
                      json={"model": MODELO_CHAT, "max_tokens": CHAT_MAX_TOKENS, "temperature": 0.2,
                            "messages": mensajes}, timeout=60)
    r.raise_for_status()
    return (r.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""


_extractor = memoria.Extractor(_llamar_modelo_para_extraer, EXTRAER_MINUTOS)


def _sistema_para(texto, nota=""):
    """Prompt del sistema: persona + perfil + hechos aprobados relevantes. La memoria nunca rompe la voz."""
    hechos = []
    if MEMORIA_ACTIVA:
        try:
            t0 = time.perf_counter()
            previo = next((m["content"] for m in reversed(historial_actual()) if m["role"] == "user"), "")
            hechos = memoria.recuperar(f"{texto} {previo}")
            ms = (time.perf_counter() - t0) * 1000
            if ms > 50:
                print(f"AVISO: la memoria tardó {ms:.0f} ms", flush=True)
        except Exception as error:
            print(f"AVISO: memoria no disponible: {error}", flush=True)
    rasgos = []
    if MEMORIA_ACTIVA:
        try:
            rasgos = memoria.rasgos_activos()
        except Exception as error:
            print(f"AVISO: rasgos no disponibles: {error}", flush=True)
    return construir_sistema(nota, hechos=hechos, rasgos=rasgos, ahora=ahora_robot())

# Modelo de datos
class ComandoRobot(BaseModel):
    emocion: str = ""
    angulo_cuello: int | None = None
    mensaje_voz: str = ""

class FraseVoz(BaseModel):
    texto: str


@app.get("/")
def leer_raiz():
    return {
        "estado": "activo",
        "descripcion": "Servidor FastAPI de Kids Robot funcionando",
        "rutas": ["/cmd", "/hablar", "/serie", "/conversar", "/voz", "/voz/stream", "/olvidar", "/estado"],
    }


@app.get("/estado")
def leer_estado():
    """Estado del puente: si el robot está conectado por cable y qué dijo al final.

    Lo usa revisar_todo.py para saber si el problema es el puente, el cable
    o el robot, sin tener que mirar la consola.
    """
    with _log_lock:
        ultimas = [texto for _, texto in list(_log_robot)[-5:]]

    ultimo_rostro = ""
    for texto in reversed(ultimas):
        if texto.startswith("Rostro: "):
            ultimo_rostro = texto[len("Rostro: "):].strip()
            break

    return {
        "servidor": "puente",
        "serial_abierto": bool(arduino and arduino.is_open),
        "puerto": SERIAL_PORT,
        "baudios": BAUD_RATE,
        "voz_en_cola": _cola_voz.qsize(),
        "ultimo_rostro": ultimo_rostro,
        "ultimas_lineas": ultimas,
    }


@app.post("/cmd")
def enviar_comando_robot(cmd: ComandoRobot):
    """Mueve el robot por puerto serie y, si viene 'mensaje_voz', lo dice en voz alta.

    El firmware espera las claves 'rostro' y 'cabeza' (ver robot_rostro.ino,
    procesarLinea). Aquí se traducen desde los nombres de esta API.
    """
    global arduino
    emocion = cmd.emocion.strip()
    mensaje = cmd.mensaje_voz.strip()

    payload = {}
    if emocion:
        payload["rostro"] = emocion
    if cmd.angulo_cuello is not None:
        payload["cabeza"] = max(10, min(170, cmd.angulo_cuello))

    if not payload and not mensaje:
        raise HTTPException(
            status_code=400,
            detail="Nada que hacer: indica 'emocion', 'angulo_cuello' o 'mensaje_voz'.",
        )

    marca = _log_numero

    if payload:
        if not (arduino and arduino.is_open):
            raise HTTPException(status_code=503, detail="El ESP32 no está conectado por puerto serie.")
        try:
            arduino.write((json.dumps(payload) + "\n").encode("utf-8"))
            arduino.flush()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    if mensaje:
        hablar(mensaje)

    return {
        "status": "ok",
        "enviado": payload or None,
        "voz": mensaje or None,
        "robot_dijo": _respuestas_desde(marca) if payload else [],
    }


@app.post("/hablar")
def decir_frase(frase: FraseVoz):
    """Solo voz: dice el texto en los parlantes de este PC, sin tocar el robot."""
    texto = frase.texto.strip()
    if not texto:
        raise HTTPException(status_code=400, detail="Texto vacío.")
    if len(texto) > 600:
        raise HTTPException(status_code=400, detail="Texto demasiado largo (máx. 600 caracteres).")
    hablar(texto)
    return {"status": "ok", "en_cola": _cola_voz.qsize()}


class TextoSerie(BaseModel):
    texto: str


@app.post("/serie")
def mandar_texto(entrada: TextoSerie):
    """Depuración: manda texto crudo al robot y devuelve lo que contesta.

    Ejemplos: {"texto": "lista"} (emociones disponibles), {"texto": "wifi"},
    {"texto": "cabeza 90"}. Sirve para saber si el ESP32 está vivo.
    """
    if not (arduino and arduino.is_open):
        raise HTTPException(status_code=503, detail="El ESP32 no está conectado por puerto serie.")

    texto = entrada.texto.strip()
    if not texto or len(texto) > 200:
        raise HTTPException(status_code=400, detail="Texto vacío o demasiado largo.")

    marca = _log_numero
    try:
        arduino.write((texto + "\n").encode("utf-8"))
        arduino.flush()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"enviado": texto, "robot_dijo": _respuestas_desde(marca, espera=0.6)}


class Conversacion(BaseModel):
    texto: str
    hablar: bool = True
    nota: str = ""          # instrucción extra para el modelo en esta respuesta (la usa /voz)
    rapido: bool = False    # voz: no gastar más de PRESUPUESTO_MODELO_VOZ segundos en el modelo


@app.post("/conversar")
def conversar(entrada: Conversacion):
    """Contesta con el modelo de lenguaje y lo dice en voz alta.

    Lo usa el asistente de voz cuando la frase no es una orden conocida.
    La llave y el modelo se leen de variables de entorno o de server/.env.
    """
    texto = entrada.texto.strip()
    if not texto:
        raise HTTPException(status_code=400, detail="Texto vacío.")
    if len(texto) > 500:
        raise HTTPException(status_code=400, detail="Frase demasiado larga (máx. 500 caracteres).")
    if not CLAVE_MODELO:
        raise HTTPException(
            status_code=503,
            detail="Faltan LLM_API_KEY, LLM_URL y LLM_MODEL (variables de entorno o server/.env) para poder conversar.",
        )

    # Modo niño: casos claros se cortan antes de gastar una llamada al modelo.
    tema = revisar_entrada(texto)
    if tema:
        if entrada.hablar:
            hablar(RESPUESTA_BLOQUEO)
        return {
            "respuesta": RESPUESTA_BLOQUEO,
            "modelo": None,
            "bloqueado": tema,
            "segundos": 0.0,
        }

    inicio = time.time()
    mensajes = [{"role": "system", "content": _sistema_para(texto, entrada.nota)}]
    mensajes.extend(historial_actual())
    mensajes.append({"role": "user", "content": texto})

    contenido = ""
    problema = ""
    estado = None
    cortado = ""            # última respuesta que parecía cortada, por si no llega una mejor

    for intento in range(3):    # reintentos: el proveedor falla de vez en cuando
        espera_max = 60.0
        if entrada.rapido:      # por voz alguien está esperando: no pasarse del presupuesto de tiempo
            restante = PRESUPUESTO_MODELO_VOZ - (time.time() - inicio)
            if intento > 0 and restante < 3:
                break
            espera_max = max(3.0, restante)
        try:
            respuesta = requests.post(
                URL_CHAT,
                headers={
                    "content-type": "application/json",
                    "authorization": f"Bearer {CLAVE_MODELO}",
                    "x-opencode-session": SESION_CHAT,
                },
                json={
                    "model": MODELO_CHAT,
                    "max_tokens": CHAT_MAX_TOKENS,
                    "temperature": 0.7,
                    "messages": mensajes,
                },
                timeout=espera_max,
            )
        except requests.RequestException as error:
            estado, problema = None, f"No pude hablar con el modelo: {error}"
        else:
            estado = respuesta.status_code
            if respuesta.ok:
                try:
                    datos = respuesta.json()
                except ValueError:
                    datos = {}
                eleccion = (datos.get("choices") or [{}])[0]
                contenido = (eleccion.get("message") or {}).get("content") or ""
                if contenido.strip():
                    motivo = eleccion.get("finish_reason")
                    if motivo not in (None, "stop"):
                        print(f"ℹ️ finish_reason={motivo} ({len(contenido)} caracteres)", flush=True)
                    quedan = PRESUPUESTO_MODELO_VOZ - (time.time() - inicio)
                    if (entrada.rapido and intento < 2 and quedan >= 3
                            and _respuesta_cortada(contenido, motivo)):
                        print(f"⚠️ Respuesta cortada del modelo ({contenido!r}, finish_reason={motivo}): reintento", flush=True)
                        cortado, contenido = contenido, ""
                        problema = "El modelo devolvió una respuesta cortada."
                    else:
                        break
                else:
                    problema = (
                    f"El modelo devolvió texto vacío (finish_reason="
                    f"{eleccion.get('finish_reason')}). Cuerpo: {respuesta.text[:200]}"
                )
            else:
                problema = f"El modelo respondió {estado}. Cuerpo: {respuesta.text[:200]}"
                if estado < 500:
                    break           # un 4xx reintentarlo no sirve
        time.sleep(0.4 * (intento + 1))

    if not contenido.strip() and cortado:
        contenido = cortado     # mejor una respuesta cortada que ninguna

    if not contenido.strip():
        print(f"⚠️ {problema}", flush=True)
        if estado == 429:
            raise HTTPException(
                status_code=429,
                detail="El modelo está ocupado ahora; prueba de nuevo en un momento.",
            )
        # Mejor que un error: una frase amable que el niño pueda escuchar.
        frase = "Mmm, no se me ocurrió qué decir. ¿Me lo preguntas de otra forma?"
        if entrada.hablar:
            hablar(frase)
        return {
            "respuesta": frase,
            "modelo": MODELO_CHAT,
            "bloqueado": None,
            "vacio": True,
            "memoria": len(historial_actual()),
            "segundos": round(time.time() - inicio, 1),
        }

    frase = " ".join(contenido.split())      # sin saltos de línea: se escucha mejor

    frase, bloqueada = revisar_salida(frase)  # red de seguridad del modo niño
    if not bloqueada:
        recordar(texto, frase)                # para poder seguir la conversación

    if entrada.hablar:
        hablar(frase)

    return {
        "respuesta": frase,
        "modelo": MODELO_CHAT,
        "bloqueado": "salida" if bloqueada else None,
        "memoria": len(historial_actual()),
        "segundos": round(time.time() - inicio, 1),
    }


@app.post("/olvidar")
def borrar_memoria():
    """Olvida la conversación anterior (lo que el modelo recordaba)."""
    olvidar()
    return {"status": "ok", "memoria": "vacía"}


# ---------- Voz por toque: el robot manda un WAV y recibe el WAV de la respuesta ----------
# La placa graba mientras se toca el TTP223 y hace POST /voz con el WAV (16 kHz, mono,
# 16 bits). Aquí se transcribe (Whisper), se decide qué hacer (orden de cara/cuello, olvidar
# o conversar con el modelo, con modo niño y memoria) y se devuelve el WAV de la respuesta.
# La respuesta NO suena en los parlantes del PC: la reproduce el robot.
#   Cabeceras de respuesta: X-Emocion (nombre de emociones.h), X-Cuello (grados, opcional),
#   X-Texto y X-Respuesta (lo que se entendió y lo que se contesta; con %xx, sin tildes crudas).
VOZ_MAX_BYTES = int(os.getenv("VOZ_MAX_BYTES", "1000000"))      # 10 s a 16 kHz son ~320 KB
CARA_RESPUESTA = os.getenv("VOZ_CARA_RESPUESTA", "neutral")     # cara que queda tras responder
VOZ_RMS_MINIMO = 0.003                                          # por debajo es silencio

_whisper = None
_whisper_lock = threading.Lock()
_turno_voz_lock = threading.Lock()                              # un turno a la vez


def _cargar_whisper():
    """Carga faster-whisper la primera vez (tarda unos segundos) y lo reutiliza."""
    global _whisper
    with _whisper_lock:
        if _whisper is None:
            try:
                from faster_whisper import WhisperModel
                from asistente_voz import MODELO
            except ImportError as error:
                raise HTTPException(status_code=503, detail=f"Falta faster-whisper: {error}")
            print(f"🧠 Cargando Whisper '{MODELO}'...", flush=True)
            _whisper = WhisperModel(MODELO, device="cpu", compute_type="int8")
        return _whisper


def _audio_desde_wav(datos):
    """WAV en bytes -> array float32 mono de 16 kHz (lo que espera Whisper)."""
    import numpy as np
    import soundfile as sf
    try:
        audio, frecuencia = sf.read(io.BytesIO(datos), dtype="float32", always_2d=False)
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"No es un WAV válido: {error}")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if frecuencia != 16000 and len(audio):
        destino = int(len(audio) * 16000 / frecuencia)
        audio = np.interp(np.linspace(0, len(audio) - 1, destino), np.arange(len(audio)), audio).astype("float32")
    return audio


STT_PROVEEDOR = _config("STT_PROVEEDOR", defecto="local").lower()   # local | groq
CLAVE_GROQ = _config("GROQ_API_KEY")
MODELO_GROQ = os.getenv("GROQ_MODELO_STT", "whisper-large-v3-turbo")
STT_GROQ_TIMEOUT = float(os.getenv("STT_GROQ_TIMEOUT", "8"))     # s; pasado ese tiempo se usa Whisper local


def _transcribir_groq(audio):
    """Audio float32 16 kHz -> texto con Groq. Lanza excepción si algo falla (el llamador cae a local)."""
    import soundfile as sf
    from asistente_voz import PROMPT_ASR, corregir_robot
    buffer = io.BytesIO()
    sf.write(buffer, audio, 16000, format="WAV", subtype="PCM_16")
    respuesta = requests.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": "Bearer " + CLAVE_GROQ},
        files={"file": ("voz.wav", buffer.getvalue(), "audio/wav")},
        data={"model": MODELO_GROQ, "language": "es", "temperature": "0", "prompt": PROMPT_ASR[:600]},
        timeout=STT_GROQ_TIMEOUT,
    )
    respuesta.raise_for_status()
    texto = respuesta.json().get("text", "").replace("«", "").replace("»", "").strip()   # Whisper copia las «» del prompt
    return corregir_robot(texto)


def _transcribir_audio(audio):
    """Transcribe con el proveedor elegido; si Groq falla o no hay clave, usa Whisper local."""
    from asistente_voz import transcribir
    if STT_PROVEEDOR == "groq" and CLAVE_GROQ:
        try:
            return _transcribir_groq(audio)
        except Exception as error:   # sin red, límite, clave mala: el robot no debe quedar mudo
            print(f"⚠️ Groq falló ({type(error).__name__}); uso Whisper local.", flush=True)
    return transcribir(_cargar_whisper(), audio)


def _wav_de_frase(frase):
    """Frase -> WAV mono de 16 bits con la voz infantil/robot de siempre. None si no hay nada que decir."""
    import numpy as np
    import soundfile as sf
    preparado = preparar_para_voz(frase)
    if not preparado:
        return None
    base = os.path.join(tempfile.gettempdir(), f"robot_voz_{uuid.uuid4().hex}")
    mp3, wav = base + ".mp3", base + ".wav"
    try:
        sintetizar(preparado, mp3, VOZ_TTS, VOZ_TONO, VOZ_RITMO)
        preparar_wav(mp3, wav, VOZ_ROBOT)              # con VOZ_ROBOT=0 solo convierte a wav
        datos, frecuencia = sf.read(wav, dtype="float32")
    finally:
        for archivo in (mp3, wav):
            try:
                os.remove(archivo)
            except OSError:
                pass
    if datos.ndim > 1:
        datos = datos.mean(axis=1)
    salida = io.BytesIO()
    sf.write(salida, np.asarray(datos, dtype="float32"), frecuencia, format="WAV", subtype="PCM_16")
    return salida.getvalue()


ACCION_BUSCAR_ACTUALIZACION = "buscar_actualizacion"


def _es_orden_actualizar(texto):
    """True ante "busca actualizaciones para ti", "revisa si hay actualizaciones", "actualízate"..."""
    from asistente_voz import normalizar
    t = normalizar(texto)
    # Tolera errores de Whisper con voz de niño ("buzca", "actualización es"): basta la raíz "actualiz" junto a un verbo de buscar.
    if (re.search(r"\b(bu[sz]?c?a?r?|(revis|chequ|verific)\w*)\b.*\bactualiz\w*", t) is not None
            or re.search(r"\bhay\s+(alguna\s+)?actualiz", t) is not None
            or re.search(r"\bactualizate\b", t) is not None):
        return True
    # Respaldo para errores más grandes de Whisper ("buscas, polizaciones para ti"): palabras parecidas a "busca" y a
    # "actualizaciones" (en ese orden) y además "para ti", que es como se pide. Así "busca aplicaciones" suelto no activa nada.
    palabras = re.findall(r"[a-zñ]+", t)
    if "para ti" not in t:
        return False
    parecido = lambda p, objetivo, minimo: difflib.SequenceMatcher(None, p, objetivo).ratio() >= minimo
    for i, p in enumerate(palabras):
        if len(p) >= 4 and (parecido(p, "busca", 0.75) or parecido(p, "buscar", 0.75)):
            return any(len(q) >= 8 and (parecido(q, "actualizaciones", 0.72) or parecido(q, "actualizacion", 0.72))
                       for q in palabras[i + 1:])
    return False


def _plan_de_respuesta(texto):
    """Decide qué hace el robot con lo que se entendió, sin llamar todavía al modelo.

    Devuelve (frase, emocion, cuello, nota): con frase, la respuesta es fija (una orden, olvidar...);
    con frase None contesta el modelo, y 'nota' es una instrucción extra para él.
    """
    from asistente_voz import NOMBRES_EMOCION, interpretar, normalizar

    if _es_orden_actualizar(texto):          # el robot consulta al servidor al oír la cabecera X-Accion
        return "Voy a ver si hay una versión nueva.", "feliz", None, ""

    tema = memoria.tema_a_olvidar(texto) if MEMORIA_ACTIVA else None
    if tema:                                  # "olvida que me gusta X": el niño puede olvidar, no aprobar
        n = memoria.olvidar_tema(tema)
        return ("Listo, ya olvidé eso." if n else "No recuerdo nada de eso."), "feliz", None, ""

    if any(p in normalizar(texto) for p in ("olvidalo", "olvida eso", "borra la memoria",
                                            "olvida la conversacion")):
        olvidar()
        return "Listo, ya lo olvidé.", "feliz", None, ""

    # Agenda y consultas: se resuelven con código local, nunca con el modelo.
    # El niño es el que habla con el robot; los padres editan desde el panel.
    try:
        de_agenda = intenciones_agenda.procesar(
            texto, familia_id=FAMILIA_ID, autor="nino",
            robot_id=persona.ROBOT_ID, clave=f"puente:{persona.ROBOT_ID}")
    except Exception as error:
        # Un fallo de la agenda no puede dejar al niño sin respuesta: se sigue como antes.
        print(f"⚠️ Agenda: {error}", flush=True)
        de_agenda = None
    if de_agenda:
        print(f"📅 agenda/{de_agenda.get('intencion', 'pendiente')}: {de_agenda.get('respuesta')}",
              flush=True)
        return (de_agenda.get("respuesta") or "Listo.",
                de_agenda.get("emocion") or "neutral", None, "")

    comando = interpretar(texto)
    emocion = comando.get("emocion") or (CARA_RESPUESTA if CARA_RESPUESTA in NOMBRES_EMOCION else "neutral")
    cuello = comando.get("angulo_cuello")

    if comando and not _es_pedido_compuesto(texto):
        solo_cuello = "¡Listo, moví la cabeza!" if cuello is not None else "Listo."
        return comando.get("mensaje_voz") or solo_cuello, emocion, cuello, ""

    # Sin orden, o una orden más una pregunta ("mueve la cabeza y dime cuántas patas tiene una araña"):
    # la orden ya se cumple con la cara y el cuello, y el modelo contesta lo demás.
    nota = ""
    if comando:
        hechas = []
        if cuello is not None:
            hechas.append("mover la cabeza")
        if comando.get("emocion"):
            hechas.append(f"poner cara de {comando['emocion']}")
        nota = ("Ya cumpliste la orden de " + " y ".join(hechas) + " (el robot lo hace solo). "
                "No repitas la orden: contesta lo que además te preguntó.")
    return None, emocion, cuello, nota


def _decidir_respuesta(texto):
    """Qué contesta el robot a lo que se entendió. Devuelve (frase, emocion, cuello|None)."""
    frase, emocion, cuello, nota = _plan_de_respuesta(texto)
    if frase is not None:
        return frase, emocion, cuello
    try:
        resultado = conversar(Conversacion(texto=texto, hablar=False, nota=nota, rapido=True))
        frase = resultado.get("respuesta") or "Mmm, no se me ocurrió qué decir."
    except HTTPException as error:
        print(f"⚠️ /voz: el modelo falló ({error.status_code}): {error.detail}", flush=True)
        frase = "Estoy un poco ocupado pensando. ¿Me lo preguntas en un momento?"
    return frase, emocion, cuello


def _es_pedido_compuesto(texto):
    """True si, además de una orden, hay una pregunta o un pedido ("... y dime cuántas patas tiene")."""
    from asistente_voz import normalizar
    t = normalizar(texto)
    if "?" in texto:
        return True
    return re.search(r"\b(y|luego|despues|ademas)\b.*\b(dime|cuentame|explicame|contesta|responde|"
                     r"cuanto|cuantos|cuantas|que|quien|donde|cuando|como|porque|por que)\b", t) is not None


def _procesar_voz(datos):
    if not _turno_voz_lock.acquire(timeout=2):
        raise HTTPException(status_code=429, detail="Todavía estoy respondiendo la frase anterior.")
    try:
        inicio = time.time()
        audio = _audio_desde_wav(datos)
        segundos = len(audio) / 16000
        rms = float((audio ** 2).mean() ** 0.5) if len(audio) else 0.0

        texto = ""
        if segundos >= 0.25 and rms >= VOZ_RMS_MINIMO:
            texto = _transcribir_audio(audio)

        t_stt = time.time()
        if texto:
            print(f"🎤 {texto}", flush=True)
            frase, emocion, cuello = _decidir_respuesta(texto)
        else:
            print(f"🎤 (no se entendió nada: {segundos:.1f} s, nivel {rms:.4f})", flush=True)
            frase, emocion, cuello = "No te escuché bien. ¿Me lo repites?", CARA_RESPUESTA, None

        t_decidir = time.time()
        wav = _wav_de_frase(frase)
        if wav is None:
            raise HTTPException(status_code=500, detail="No pude generar la voz de la respuesta.")
        fin = time.time()
        print(f"🗣️ {frase}  ({fin - inicio:.1f} s: whisper {t_stt - inicio:.1f}, "
              f"modelo/reglas {t_decidir - t_stt:.1f}, voz {fin - t_decidir:.1f})", flush=True)
        return wav, texto, frase, emocion, cuello, time.time() - inicio
    finally:
        _turno_voz_lock.release()


@app.post("/voz")
async def voz_por_toque(request: Request):
    """Recibe el WAV que grabó el robot y devuelve el WAV de la respuesta."""
    datos = await request.body()
    if not datos:
        raise HTTPException(status_code=400, detail="Cuerpo vacío: se espera un WAV.")
    if len(datos) > VOZ_MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"Audio demasiado grande (máx. {VOZ_MAX_BYTES} bytes).")

    wav, texto, frase, emocion, cuello, segundos = await run_in_threadpool(_procesar_voz, datos)

    cabeceras = {
        "X-Emocion": emocion,
        "X-Texto": quote(texto[:200], safe=""),
        "X-Respuesta": quote(frase[:200], safe=""),
        "X-Segundos": f"{segundos:.1f}",
    }
    if cuello is not None:
        cabeceras["X-Cuello"] = str(max(10, min(170, int(cuello))))
    if _es_orden_actualizar(texto):
        cabeceras["X-Accion"] = ACCION_BUSCAR_ACTUALIZACION
    return Response(content=wav, media_type="audio/wav", headers=cabeceras)


# ---------- Avisos programados: el robot pregunta y confirma ----------
# El robot inicia siempre la conexión: cada 20-30 s hace GET /pendientes. Aquí se materializan las
# ocurrencias próximas y se entrega como mucho una por minuto (agenda.debido). El aviso NO se marca
# como dicho hasta que la placa confirma que lo reprodujo; si la respuesta se pierde, se reintenta
# dentro de la ventana de 5 minutos (la placa deduplica por X-Id).

class ConfirmacionAviso(BaseModel):
    resultado: str = "dicho"        # dicho | omitido
    motivo: str = ""


def _segundos_de_wav(datos):
    """Duración en segundos del WAV generado (para que la placa sepa cuánto esperar)."""
    import wave
    try:
        with wave.open(io.BytesIO(datos), "rb") as archivo:
            frecuencia = archivo.getframerate()
            return archivo.getnframes() / frecuencia if frecuencia else 0.0
    except (wave.Error, EOFError):
        return 0.0


@app.get("/pendientes")
def pendientes():
    """Nada que decir -> 204. Si hay un aviso, su WAV y las cabeceras para reproducirlo."""
    try:
        agenda.materializar(familia_id=FAMILIA_ID)
        aviso = agenda.debido(familia_id=FAMILIA_ID, robot_id=persona.ROBOT_ID)
    except Exception as error:
        print(f"⚠️ Agenda: no pude revisar pendientes: {error}", flush=True)
        raise HTTPException(status_code=503, detail="La agenda no está disponible ahora.")
    if not aviso:
        return Response(status_code=204)

    try:
        wav = _wav_de_frase(aviso["texto"])
    except Exception as error:
        # La voz falló (red, TTS): el aviso sigue pendiente y se reintenta en el próximo minuto.
        print(f"⚠️ Agenda: no pude sintetizar el aviso {aviso['id']}: {error}", flush=True)
        raise HTTPException(status_code=503, detail="No pude generar la voz del aviso.")
    if wav is None:
        # Texto vacío tras la limpieza de pronunciación: se omite para no repetirlo cada 20 s.
        agenda.confirmar(aviso["id"], "omitido", familia_id=FAMILIA_ID, motivo="sin texto")
        return Response(status_code=204)

    cabeceras = {
        "X-Id": str(aviso["id"]),
        "X-Tipo": aviso["tipo"],
        "X-Emocion": aviso["emocion"],
        "X-Texto": quote(aviso["texto"][:400], safe=""),
        "X-Segundos": f"{_segundos_de_wav(wav):.1f}",
        "Cache-Control": "no-store",
    }
    if aviso.get("cuello") is not None:
        cabeceras["X-Cuello"] = str(max(10, min(170, int(aviso["cuello"]))))
    return Response(content=wav, media_type="audio/wav", headers=cabeceras)


@app.post("/pendientes/{id_aviso}/hecho")
def confirmar_aviso(id_aviso: int, entrada: ConfirmacionAviso | None = None):
    """El robot confirma que dijo (u omitió) el aviso. Idempotente."""
    entrada = entrada or ConfirmacionAviso()
    try:
        estado = agenda.confirmar(id_aviso, entrada.resultado, familia_id=FAMILIA_ID,
                                  motivo=entrada.motivo)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    if estado is None:
        raise HTTPException(status_code=404, detail="Ese aviso no existe.")
    return {"status": "ok", "id": id_aviso, "estado": estado}


# ---------- Voz en streaming: empieza a sonar con la primera frase ----------
# POST /voz/stream recibe el mismo WAV que /voz, pero responde con un WAV "sin fin" (cabecera con tamaño
# desconocido, 16 bits, mono) que se va llenando frase por frase: el modelo escribe, cada frase se sintetiza
# apenas está completa y se envía mientras el modelo sigue con la siguiente. Así el robot empieza a hablar
# sin esperar la respuesta completa. Las cabeceras (X-Emocion, X-Cuello, X-Texto) salen antes del audio.
# X-Respuesta no existe aquí: el texto aún no se conoce. Cliente: pedir HTTP/1.0 para no recibir "chunked".
_stream_ocupado = {"hasta": 0.0}    # un turno a la vez; caduca solo por si un cliente se cae a medias


def _tomar_turno_stream():
    with _turno_voz_lock:
        ahora = time.time()
        if ahora < _stream_ocupado["hasta"]:
            return False
        _stream_ocupado["hasta"] = ahora + 45
        return True


def _soltar_turno_stream():
    _stream_ocupado["hasta"] = 0.0


def _cabecera_wav_stream(frecuencia):
    """Cabecera WAV de 44 bytes con tamaño desconocido (0xFFFFFFFF): PCM 16 bits mono."""
    import struct
    return (b"RIFF" + struct.pack("<I", 0xFFFFFFFF) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, 1, frecuencia, frecuencia * 2, 2, 16)
            + b"data" + struct.pack("<I", 0xFFFFFFFF))


def _pcm_de_frase(frase):
    """Frase -> (PCM 16 bits mono, frecuencia) con la voz de siempre. None si no hay nada que decir."""
    import numpy as np
    import soundfile as sf
    preparado = preparar_para_voz(frase)
    if not preparado:
        return None
    base = os.path.join(tempfile.gettempdir(), f"robot_voz_{uuid.uuid4().hex}")
    mp3, wav = base + ".mp3", base + ".wav"
    try:
        sintetizar(preparado, mp3, VOZ_TTS, VOZ_TONO, VOZ_RITMO)
        preparar_wav(mp3, wav, VOZ_ROBOT)
        datos, frecuencia = sf.read(wav, dtype="float32")
    finally:
        for archivo in (mp3, wav):
            try:
                os.remove(archivo)
            except OSError:
                pass
    if datos.ndim > 1:
        datos = datos.mean(axis=1)
    pcm = (np.clip(datos, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    return pcm, int(frecuencia)


_FIN_DE_FRASE = re.compile(r"(?<=[.!?…])\s+")


def _frases_de(trozos):
    """Junta trozos de texto y entrega cada frase completa apenas se puede ("¡Hola!" no espera al resto)."""
    pendiente = ""
    for trozo in trozos:
        pendiente += trozo
        partes = _FIN_DE_FRASE.split(pendiente)
        for parte in partes[:-1]:
            if parte.strip():
                yield parte.strip()
        pendiente = partes[-1]
    if pendiente.strip():
        yield pendiente.strip()


def _trozos_del_modelo(mensajes, limite):
    """Trozos de texto de la respuesta del modelo por streaming (SSE). Ignora su razonamiento."""
    respuesta = requests.post(
        URL_CHAT,
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {CLAVE_MODELO}",
            "x-opencode-session": SESION_CHAT,
        },
        json={"model": MODELO_CHAT, "max_tokens": CHAT_MAX_TOKENS, "temperature": 0.7,
              "messages": mensajes, "stream": True},
        timeout=(5, 15), stream=True,
    )
    try:
        if not respuesta.ok:
            raise RuntimeError(f"El modelo respondió {respuesta.status_code}")
        for linea in respuesta.iter_lines(decode_unicode=False):     # bytes: el SSE no declara UTF-8
            if time.time() > limite:
                return
            if not linea.startswith(b"data:"):
                continue
            dato = linea[5:].strip()
            if dato == b"[DONE]":
                return
            try:
                objeto = json.loads(dato.decode("utf-8"))
            except ValueError:
                continue
            trozo = ((objeto.get("choices") or [{}])[0].get("delta") or {}).get("content") or ""
            if trozo:
                yield trozo
    finally:
        respuesta.close()


def _frases_del_modelo(texto, nota):
    """Frases que contesta el modelo, con modo niño y memoria (como /conversar, pero por frases)."""
    tema = revisar_entrada(texto)
    if tema:
        yield RESPUESTA_BLOQUEO
        return
    mensajes = [{"role": "system", "content": _sistema_para(texto, nota)}]
    mensajes.extend(historial_actual())
    mensajes.append({"role": "user", "content": texto})

    dichas, bloqueada = [], False
    try:
        for frase in _frases_de(_trozos_del_modelo(mensajes, time.time() + 25)):
            segura, mala = revisar_salida(frase)            # red de seguridad del modo niño, frase por frase
            if mala:
                bloqueada = True
                yield segura
                break
            dichas.append(frase)
            yield frase
    except (requests.RequestException, RuntimeError) as error:
        print(f"⚠️ /voz/stream: el modelo falló: {error}", flush=True)    # la disculpa sale abajo, una sola vez
    if not dichas and not bloqueada:
        print("⚠️ /voz/stream: el modelo no devolvió texto", flush=True)
        yield "Mmm, no se me ocurrió qué decir. ¿Me lo preguntas de otra forma?"
    elif dichas and not bloqueada:
        recordar(texto, " ".join(dichas))


def _preparar_turno_stream(datos):
    """Transcribe y decide qué contestar. Devuelve lo necesario para empezar a responder."""
    if not _tomar_turno_stream():
        raise HTTPException(status_code=429, detail="Todavía estoy respondiendo la frase anterior.")
    try:
        inicio = time.time()
        audio = _audio_desde_wav(datos)
        segundos = len(audio) / 16000
        rms = float((audio ** 2).mean() ** 0.5) if len(audio) else 0.0

        texto = ""
        if segundos >= 0.25 and rms >= VOZ_RMS_MINIMO:
            texto = _transcribir_audio(audio)
        t_stt = time.time()

        if texto:
            print(f"🎤 {texto}", flush=True)
            fija, emocion, cuello, nota = _plan_de_respuesta(texto)
        else:
            print(f"🎤 (no se entendió nada: {segundos:.1f} s, nivel {rms:.4f})", flush=True)
            fija, emocion, cuello, nota = "No te escuché bien. ¿Me lo repites?", CARA_RESPUESTA, None, ""
        frases = iter([fija]) if fija is not None else _frases_del_modelo(texto, nota)
        return {"frases": frases, "emocion": emocion, "cuello": cuello, "texto": texto,
                "inicio": inicio, "t_stt": t_stt}
    except BaseException:
        _soltar_turno_stream()
        raise


def _audio_en_streaming(turno):
    """Genera la cabecera WAV y, frase a frase, el audio. Libera el turno al terminar o si el cliente se va."""
    inicio, enviada = turno["inicio"], None
    primer_audio, hablado = None, []
    t_modelo = t_voz = None      # medición: del fin del STT a la 1.ª frase del modelo; y lo que tarda en sintetizarse
    try:
        for frase in turno["frases"]:
            ahora = time.time()
            if t_modelo is None:
                t_modelo = ahora - turno["t_stt"]
            hecho = _pcm_de_frase(frase)
            if t_voz is None:
                t_voz = time.time() - ahora
            if hecho is None:
                continue
            pcm, frecuencia = hecho
            if enviada is None:
                enviada = frecuencia
                yield _cabecera_wav_stream(frecuencia)
            elif frecuencia != enviada:                     # no debería pasar: mismo TTS en todas las frases
                import numpy as np
                v = np.frombuffer(pcm, dtype="<i2").astype("float32")
                n = int(len(v) * enviada / frecuencia)
                pcm = np.interp(np.linspace(0, len(v) - 1, n), np.arange(len(v)), v).astype("<i2").tobytes()
            if primer_audio is None:
                primer_audio = time.time() - inicio
            hablado.append(frase)
            for i in range(0, len(pcm), 8192):
                yield pcm[i:i + 8192]
    finally:
        total = time.time() - inicio
        t_stt = turno["t_stt"] - inicio
        if primer_audio is not None:
            print(f"🗣️ (stream) {' '.join(hablado)}\n   primer audio a los {primer_audio:.1f} s "
                  f"(whisper {t_stt:.1f}, modelo/reglas hasta la 1.ª frase {t_modelo:.1f}, "
                  f"voz de la 1.ª frase {t_voz:.1f}), total {total:.1f} s, {len(hablado)} frase(s)", flush=True)
        else:
            print(f"🗣️ (stream) sin audio ({total:.1f} s)", flush=True)
        _soltar_turno_stream()


@app.post("/voz/stream")
async def voz_por_toque_en_streaming(request: Request):
    """Como /voz, pero el audio de la respuesta empieza a llegar con la primera frase."""
    datos = await request.body()
    if not datos:
        raise HTTPException(status_code=400, detail="Cuerpo vacío: se espera un WAV.")
    if len(datos) > VOZ_MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"Audio demasiado grande (máx. {VOZ_MAX_BYTES} bytes).")

    turno = await run_in_threadpool(_preparar_turno_stream, datos)
    cabeceras = {
        "X-Emocion": turno["emocion"],
        "X-Texto": quote(turno["texto"][:200], safe=""),
        "X-Stream": "1",
        "Cache-Control": "no-store",
    }
    if turno["cuello"] is not None:
        cabeceras["X-Cuello"] = str(max(10, min(170, int(turno["cuello"]))))
    if _es_orden_actualizar(turno["texto"]):
        cabeceras["X-Accion"] = ACCION_BUSCAR_ACTUALIZACION
    return StreamingResponse(_audio_en_streaming(turno), media_type="audio/wav", headers=cabeceras)


# ---------- Firmware del robot (actualización OTA desde el servidor) ----------
# El robot (siempre es él quien inicia la conexión) pregunta por /firmware/version y, si hay una versión mayor,
# baja /firmware/app.bin. Los dos archivos los deja firmware/robot_rostro/publicar.ps1 (o publicar.sh) en FIRMWARE_DIR.
# Pasan por el mismo control de token que /voz (desde la red o un proxy hace falta X-Token).
FIRMWARE_DIR = os.getenv("FIRMWARE_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "firmware")


@app.get("/firmware/version")
def firmware_version():
    ruta = os.path.join(FIRMWARE_DIR, "version.json")
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
        manifiesto = {"version": str(datos["version"]), "bytes": int(datos["bytes"]), "sha256": str(datos["sha256"]).lower()}
        if datos.get("firma"):          # firma ECDSA hecha fuera del servidor (publicar.ps1 / publicar.sh); el servidor solo la reenvía, no puede crearla
            manifiesto["firma"] = str(datos["firma"]).lower()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="No hay firmware publicado.")
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=500, detail="version.json inválido (se espera version, bytes y sha256).")
    return JSONResponse(manifiesto, headers={"Cache-Control": "no-store"})


@app.get("/firmware/app.bin")
def firmware_binario():
    ruta = os.path.join(FIRMWARE_DIR, "app.bin")
    if not os.path.isfile(ruta):
        raise HTTPException(status_code=404, detail="No hay firmware publicado.")
    return FileResponse(ruta, media_type="application/octet-stream", headers={"Cache-Control": "no-store"})


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    puerto = int(os.getenv("PUERTO", "8081"))
    print(f"🌐 Servidor en http://{host}:{puerto}")
    if host not in _ORIGENES_LOCALES:
        if TOKEN_ROBOT:
            print("🔒 Acceso desde la red solo con la cabecera X-Token (ROBOT_TOKEN).")
        else:
            print("⚠️ Abierto a la red pero SIN ROBOT_TOKEN: las conexiones de la red se rechazan (403).")
    try:
        uvicorn.run(app, host=host, port=puerto)
    finally:
        cerrar_serial()