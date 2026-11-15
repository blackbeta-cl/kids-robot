"""Llamada simple al modelo para herramientas fuera del puente (p. ej. memoria_cli.py semanal).
Mismo proveedor y llaves que el puente: variables de entorno o server/.env (el cerebro se cambia con LLM_URL / LLM_MODEL)."""
import entorno  # noqa: F401  (carga server/.env antes de leer la configuración)
import os
import requests

_AQUI = os.path.dirname(os.path.abspath(__file__))


def _env():
    datos = {}
    for ruta in (os.path.join(_AQUI, ".env"),):
        try:
            with open(ruta, encoding="utf-8-sig", errors="replace") as f:
                for linea in f:
                    linea = linea.strip()
                    if linea and not linea.startswith("#") and "=" in linea:
                        k, v = linea.split("=", 1)
                        datos[k.strip()] = v.strip().strip('"').strip("'")
        except OSError:
            pass
    return datos


def llamar_modelo(mensajes, max_tokens=700, temperatura=0.2, timeout=60):
    env = _env()

    def valor(*nombres):
        for n in nombres:
            v = os.getenv(n) or env.get(n)
            if v:
                return v
        return ""

    clave = valor("LLM_API_KEY", "OPENCODE_API_KEY")
    legado = bool(valor("OPENCODE_API_KEY")) and not valor("LLM_API_KEY")   # clave antigua: se mantiene el proveedor de siempre
    url = valor("LLM_URL", "URL_CHAT") or ("https://opencode.ai/inference/go/openai/v1/chat/completions" if legado else "")
    modelo = valor("LLM_MODEL", "OPENCODE_MODEL") or ("beam-free" if legado else "")
    if not (clave and url and modelo):
        raise RuntimeError("faltan LLM_API_KEY, LLM_URL o LLM_MODEL (variables de entorno o server/.env)")
    r = requests.post(url, headers={"content-type": "application/json", "authorization": f"Bearer {clave}"},
                      json={"model": modelo, "max_tokens": max_tokens, "temperature": temperatura, "messages": mensajes},
                      timeout=timeout)
    r.raise_for_status()
    return (r.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
