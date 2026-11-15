"""Vista previa y pruebas de la página del portal cautivo, en el PC (sin placa).

    python vista_portal.py            -> sirve la página en http://127.0.0.1:8099/ con redes de ejemplo (Ctrl+C para salir)
    python vista_portal.py --prueba   -> pruebas automáticas contra ese servidor simulado

El servidor simulado imita las rutas del firmware (portal.h): /, /redes, /guardar, /olvidar y la redirección de
todo lo demás. La página se extrae de robot_rostro/portal_pagina.h, así que lo que se ve aquí es lo que se sirve.
Lo que NO prueba: el AP, el DNS ni el WebServer reales (eso necesita la placa y un móvil).
"""
import json
import re
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent / "robot_rostro"
PAGINA_H = RAIZ / "portal_pagina.h"
TOKEN = "a1b2c3d4"

REDES = [
    {"s": "Mi red WiFi", "r": -48, "a": False},
    {"s": "VTR-1234", "r": -63, "a": False},
    {"s": "Cafe <b>abierto</b> \"x\"", "r": -74, "a": True},      # nombre con HTML: debe mostrarse como texto
    {"s": "Nombre-de-red-de-treinta-y-dos-c", "r": -85, "a": False},
]
guardadas = ["Casa de los abuelos"]
motivo = ""


def leer_pagina():
    texto = PAGINA_H.read_text(encoding="utf-8")
    m = re.search(r'R"PORTALHTML\((.*)\)PORTALHTML"', texto, re.S)
    if not m:
        raise SystemExit("No encuentro la página en portal_pagina.h")
    return m.group(1)


def validar(ssid, clave):
    """Mismas reglas que redesValidar() de redes_logica.h."""
    if not ssid:
        return "Falta el nombre de la red"
    if len(ssid.encode()) > 32:
        return "Nombre de red muy largo (max 32)"
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in ssid):
        return "Nombre con caracteres raros"
    if 0 < len(clave) < 8:
        return "Clave muy corta (min 8)"
    if len(clave) > 63:
        return "Clave muy larga (max 63)"
    return None


class Manejador(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _enviar(self, codigo, tipo, cuerpo, extra=None):
        datos = cuerpo.encode() if isinstance(cuerpo, str) else cuerpo
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(datos)

    def _json(self, obj, codigo=200):
        self._enviar(codigo, "application/json", json.dumps(obj))

    def _token_ok(self, valores):
        return valores.get("t", [""])[0] == TOKEN

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/":
            self._enviar(200, "text/html; charset=utf-8", leer_pagina().replace("__TOKEN__", TOKEN))
        elif u.path == "/redes":
            if not self._token_ok(q):
                return self._json({"ok": False, "error": "Token invalido"}, 403)
            d = {"redes": REDES, "guardadas": guardadas}
            if motivo:
                d["motivo"] = motivo
            self._json(d)
        else:   # /generate_204, /hotspot-detect.html...
            self._enviar(302, "text/plain", "", {"Location": "http://127.0.0.1:8099/"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        v = urllib.parse.parse_qs(self.rfile.read(n).decode(), keep_blank_values=True)
        if not self._token_ok(v):
            return self._json({"ok": False, "error": "Token invalido"}, 403)
        if self.path == "/guardar":
            err = validar(v.get("ssid", [""])[0], v.get("clave", [""])[0])
            self._json({"ok": False, "error": err} if err else {"ok": True})
        elif self.path == "/olvidar":
            s = v.get("ssid", [""])[0]
            if s in guardadas:
                guardadas.remove(s)
                self._json({"ok": True})
            else:
                self._json({"ok": False, "error": "No tengo esa red"})
        else:
            self._enviar(302, "text/plain", "", {"Location": "http://127.0.0.1:8099/"})


class NoSigueRedireccion(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def pedir(ruta, datos=None):
    req = urllib.request.Request("http://127.0.0.1:8099" + ruta, data=urllib.parse.urlencode(datos).encode() if datos is not None else None)
    abrir = urllib.request.build_opener(NoSigueRedireccion).open
    try:
        with abrir(req) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def pruebas():
    global motivo
    fallos = 0
    total = 0

    def ok(cond, texto):
        nonlocal fallos, total
        total += 1
        if not cond:
            fallos += 1
            print("FALLA:", texto)

    pagina = leer_pagina()
    ok("__TOKEN__" in pagina and pagina.count("__TOKEN__") == 1, "la página tiene un único marcador __TOKEN__")
    ok("innerHTML" not in pagina and "document.write" not in pagina and "eval(" not in pagina, "la página no usa innerHTML, document.write ni eval")
    ok(not re.search(r'https?://', pagina), "la página no carga nada externo (sin http(s):// ni CDN)")
    ok(len(pagina.encode()) < 9000, f"la página pesa {len(pagina.encode())} bytes (< 9000)")
    ok('name="viewport"' in pagina, "tiene viewport para móvil")

    c, h, cuerpo = pedir("/")
    ok(c == 200 and "text/html" in h.get("Content-Type", "") and TOKEN in cuerpo and "__TOKEN__" not in cuerpo, "GET / sirve la página con el token puesto")
    ok(h.get("Cache-Control") == "no-store", "GET / con Cache-Control: no-store")

    c, _, _ = pedir("/redes")
    ok(c == 403, "/redes sin token da 403")
    c, _, _ = pedir("/redes?t=malo")
    ok(c == 403, "/redes con token malo da 403")
    c, _, cuerpo = pedir("/redes?t=" + TOKEN)
    d = json.loads(cuerpo)
    ok(c == 200 and len(d["redes"]) == 4 and d["guardadas"] == ["Casa de los abuelos"], "/redes con token devuelve redes y guardadas")
    ok(any("<b>" in r["s"] for r in d["redes"]), "el nombre con HTML llega como dato JSON (la página lo muestra con textContent)")

    for ssid, clave, bien in [("Casa", "12345678", True), ("Casa", "", True), ("", "12345678", False), ("Casa", "1234567", False),
                              ("Casa", "x" * 64, False), ("x" * 33, "12345678", False), ("Ca\nsa", "12345678", False)]:
        c, _, cuerpo = pedir("/guardar", {"t": TOKEN, "ssid": ssid, "clave": clave})
        ok(c == 200 and json.loads(cuerpo)["ok"] is bien, f"/guardar ssid={ssid!r:.12} clave de {len(clave)} -> ok={bien}")
    c, _, _ = pedir("/guardar", {"ssid": "Casa", "clave": "12345678"})
    ok(c == 403, "/guardar sin token da 403")
    c, _, _ = pedir("/guardar", {"t": "malo", "ssid": "Casa", "clave": "12345678"})
    ok(c == 403, "/guardar con token malo da 403")

    c, _, _ = pedir("/olvidar", {"ssid": "Casa de los abuelos"})
    ok(c == 403, "/olvidar sin token da 403")
    c, _, cuerpo = pedir("/olvidar", {"t": TOKEN, "ssid": "Casa de los abuelos"})
    ok(json.loads(cuerpo)["ok"] is True, "/olvidar con token borra la red")
    c, _, cuerpo = pedir("/olvidar", {"t": TOKEN, "ssid": "Casa de los abuelos"})
    ok(json.loads(cuerpo)["ok"] is False, "/olvidar de una red que no está falla")

    for ruta in ["/generate_204", "/hotspot-detect.html", "/connecttest.txt", "/ncsi.txt", "/fwlink", "/cualquier/cosa"]:
        c, h, _ = pedir(ruta)
        ok(c == 302 and h.get("Location", "").endswith("/"), f"{ruta} redirige al portal")

    print(f"{total} comprobaciones, {fallos} fallos")
    return 1 if fallos else 0


def main():
    srv = HTTPServer(("127.0.0.1", 8099), Manejador)
    if "--prueba" in sys.argv:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        sys.exit(pruebas())
    print("Vista previa del portal en http://127.0.0.1:8099/  (Ctrl+C para salir)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
