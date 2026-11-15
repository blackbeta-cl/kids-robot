"""Carga server/.env en las variables de entorno del proceso (sin pisar las que ya existan).

Se importa lo primero en cada módulo que lee configuración al importarse, para que ROBOT_TZ, ROBOT_ID,
LLM_API_KEY, etc. funcionen igual si vienen del .env, de systemd (EnvironmentFile) o de la consola.
El archivo .env está en .gitignore: nunca se sube.
"""
import os


def cargar(ruta=None):
    ruta = ruta or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(ruta, encoding="utf-8-sig", errors="replace") as archivo:
            for linea in archivo:
                linea = linea.strip()
                if not linea or linea.startswith("#") or "=" not in linea:
                    continue
                clave, valor = linea.split("=", 1)
                valor = valor.strip().strip('"').strip("'")
                if clave.strip() and valor:
                    os.environ.setdefault(clave.strip(), valor)
    except OSError:
        pass


cargar()
