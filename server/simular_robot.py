"""Robot simulado en el PC: hace lo mismo que hará la placa con la agenda.

Pregunta GET /pendientes cada 20 s (el robot inicia siempre la conexión), reproduce el WAV
que devuelve el puente y confirma con POST /pendientes/<id>/hecho. Si no hay nada, el
servidor responde 204 y no pasa nada. Sirve para probar el circuito completo desde el
panel («Probar ahora») antes de tocar el ESP32.

Uso (desde la carpeta server, con el puente corriendo):
    python simular_robot.py
    python simular_robot.py --una-vez --sin-sonido
    python simular_robot.py --url https://robot.ejemplo.cl --token ... --guardar avisos

Variables de entorno equivalentes: ROBOT_URL, ROBOT_TOKEN.
El token no se imprime nunca.
"""
import argparse
import os
import sys
import tempfile
import time
from urllib.parse import unquote

import requests

INTERVALO = 20
TIEMPO = (10, 90)          # (conectar, leer): sintetizar la voz puede tardar unos segundos


def cabeceras(token):
    return {"X-Token": token} if token else {}


def pedir_aviso(url, token="", sesion=None):
    """El próximo aviso ya con el WAV, o None si el servidor responde 204 (no hay nada)."""
    sesion = sesion or requests
    respuesta = sesion.get(url.rstrip("/") + "/pendientes", headers=cabeceras(token), timeout=TIEMPO)
    if respuesta.status_code == 204:
        return None
    respuesta.raise_for_status()
    if not respuesta.content:
        raise ValueError("el servidor respondió sin audio")
    return {
        "id": (respuesta.headers.get("X-Id") or "").strip(),
        "tipo": respuesta.headers.get("X-Tipo", ""),
        "emocion": respuesta.headers.get("X-Emocion", ""),
        "cuello": respuesta.headers.get("X-Cuello", ""),
        "texto": unquote(respuesta.headers.get("X-Texto", "")),
        "segundos": respuesta.headers.get("X-Segundos", ""),
        "wav": respuesta.content,
    }


def confirmar(url, id_aviso, token="", resultado="dicho", motivo="", sesion=None):
    """Le dice al puente que el aviso ya se dijo (u omitió). Idempotente en el servidor."""
    sesion = sesion or requests
    respuesta = sesion.post(url.rstrip("/") + f"/pendientes/{id_aviso}/hecho",
                            json={"resultado": resultado, "motivo": motivo},
                            headers=cabeceras(token), timeout=TIEMPO)
    respuesta.raise_for_status()
    return respuesta.json() if respuesta.content else {}


def reproducir_aviso(aviso, guardar=None):
    """Guarda el WAV (si se pide) y lo reproduce en los parlantes de este PC. Devuelve la ruta."""
    if guardar:
        os.makedirs(guardar, exist_ok=True)
        ruta = os.path.join(guardar, f"aviso_{aviso['id']}.wav")
    else:
        archivo = tempfile.NamedTemporaryFile(prefix="aviso_", suffix=".wav", delete=False)
        ruta = archivo.name
        archivo.close()
    with open(ruta, "wb") as salida:
        salida.write(aviso["wav"])
    try:
        from voz_robot import reproducir          # import tardío: --sin-sonido no necesita audio
        reproducir(ruta, "waveaudio")
    finally:
        if not guardar:
            try:
                os.remove(ruta)
            except OSError:
                pass
    return ruta


def manejar_aviso(url, token, aviso, ya_dichos, sonido=True, guardar=None, salida=print):
    """Reproduce un aviso y lo confirma. Devuelve True si quedó confirmado."""
    ident = aviso.get("id") or ""
    if not ident.isdigit():
        salida("⚠️ El aviso llegó sin X-Id: no puedo confirmarlo (se reintentará).")
        return False

    detalle = " · ".join(parte for parte in (
        aviso.get("tipo"),
        aviso.get("emocion"),
        f"cuello {aviso['cuello']}" if aviso.get("cuello") else "",
        f"{aviso['segundos']} s" if aviso.get("segundos") else "") if parte)

    if ident in ya_dichos:
        # El servidor no recibió la confirmación anterior: no se repite el audio.
        salida(f"↻ aviso {ident} repetido: ya lo dije, confirmo otra vez.")
    else:
        salida(f"📣 aviso {ident}: «{aviso.get('texto', '')}»")
        if detalle:
            salida(f"   {detalle}")
        if sonido:
            try:
                ruta = reproducir_aviso(aviso, guardar)
                if guardar:
                    salida(f"💾 guardado en {ruta}")
            except Exception as error:
                salida(f"⚠️ No pude reproducirlo: {error}")
                try:
                    confirmar(url, ident, token, "omitido", "no se pudo reproducir")
                except Exception as error_confirmar:
                    salida(f"⚠️ Tampoco pude confirmar el aviso {ident}: {error_confirmar}")
                    return False
                return True

    try:
        confirmar(url, ident, token, "dicho")
    except Exception as error:
        salida(f"⚠️ No pude confirmar el aviso {ident}: {error}")
        return False
    ya_dichos.add(ident)
    salida(f"✅ aviso {ident} confirmado")
    return True


def bucle(url, token="", intervalo=INTERVALO, veces=None, sonido=True, guardar=None, salida=print):
    """Pregunta para siempre (o `veces` veces). Un fallo de red no corta el sondeo."""
    ya_dichos = set()
    vueltas = 0
    while veces is None or vueltas < veces:
        vueltas += 1
        try:
            aviso = pedir_aviso(url, token)
        except Exception as error:
            salida(f"⚠️ No pude preguntar al puente: {error}")
        else:
            if aviso is None:
                salida("· sin avisos")
            else:
                manejar_aviso(url, token, aviso, ya_dichos, sonido, guardar, salida)
        if veces is not None and vueltas >= veces:
            return
        time.sleep(max(1, intervalo))


def _entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def main(argv=None):
    # En consolas de Windows con cp1252 (o salida redirigida) los emojis rompen el print.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Simula el robot: pregunta /pendientes y confirma.")
    parser.add_argument("--url", default=os.getenv("ROBOT_URL", "http://127.0.0.1:8000"),
                        help="dirección del puente (ROBOT_URL)")
    parser.add_argument("--token", default=os.getenv("ROBOT_TOKEN", ""),
                        help="token del robot (ROBOT_TOKEN); no se imprime")
    parser.add_argument("--intervalo", type=int, default=INTERVALO,
                        help=f"segundos entre sondeos (por defecto {INTERVALO})")
    parser.add_argument("--una-vez", action="store_true", help="un solo sondeo y termina")
    parser.add_argument("--veces", type=int, default=None, help="cantidad de sondeos")
    parser.add_argument("--sin-sonido", action="store_true", help="no reproduce el WAV")
    parser.add_argument("--guardar", default=None, metavar="CARPETA",
                        help="guarda cada WAV en esa carpeta")
    args = parser.parse_args(argv)

    veces = 1 if args.una_vez else args.veces
    if veces is not None and veces < 1:
        parser.error("--veces debe ser 1 o más.")

    local = args.url.startswith(("http://127.0.0.1", "http://localhost", "http://[::1]"))
    if not local and not args.token:
        print("⚠️ Sin token: el servidor rechazará los sondeos desde la red "
              "(usa --token o ROBOT_TOKEN).", flush=True)

    print(f"🤖 Simulador de robot · {args.url} · "
          f"{'con token' if args.token else 'sin token'} · "
          f"cada {args.intervalo} s · {'con sonido' if not args.sin_sonido else 'sin sonido'}",
          flush=True)
    try:
        bucle(args.url, args.token, args.intervalo, veces,
              sonido=not args.sin_sonido, guardar=args.guardar)
    except KeyboardInterrupt:
        print("\n👋 Simulador detenido.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
