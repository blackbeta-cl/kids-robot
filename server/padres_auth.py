"""Usuarios, contraseñas y sesiones del panel de padres (misma base que la memoria: datos/memoria.db).

- Contraseña: scrypt de la biblioteca estándar (sin dependencias nuevas), sal aleatoria por usuario.
- Sesión: token aleatorio de 256 bits que solo vive en la cookie; en la base se guarda su SHA-256.
  Caduca a los SESION_DIAS_MAX días desde que se creó o a los SESION_DIAS_INACTIVA sin usarla.
- Límite de intentos: LIMITE_FALLOS fallos en VENTANA_MIN minutos por usuario o por IP -> bloqueado.
- No hay registro de usuarios por la web: los crea padres_cli.py en el equipo que tiene la base.
"""
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta

import memoria

SESION_DIAS_MAX = 30
SESION_DIAS_INACTIVA = 7
LIMITE_FALLOS = 5                 # por IP
LIMITE_FALLOS_USUARIO = 15        # por usuario, desde cualquier IP (más alto: si no, un extraño dejaría fuera al padre)
VENTANA_MIN = 15
MIN_CLAVE = 10
_N, _R, _P = 2 ** 15, 8, 1
_MAXMEM = 64 * 1024 * 1024


class ClaveDebil(ValueError):
    pass


class Bloqueado(Exception):
    def __init__(self, segundos):
        super().__init__("demasiados intentos")
        self.segundos = segundos


def _ahora():
    return datetime.now()


def _iso(t):
    return t.isoformat(timespec="seconds")


def _scrypt(clave, sal):
    return hashlib.scrypt(clave.encode("utf-8"), salt=sal, n=_N, r=_R, p=_P, maxmem=_MAXMEM, dklen=32)


def hashear(clave):
    sal = secrets.token_bytes(16)
    return f"scrypt${_N}${_R}${_P}${sal.hex()}${_scrypt(clave, sal).hex()}"


def verificar_hash(clave, almacenado):
    try:
        _, n, r, p, sal, esperado = almacenado.split("$")
        if (int(n), int(r), int(p)) != (_N, _R, _P):
            return False
        return hmac.compare_digest(_scrypt(clave, bytes.fromhex(sal)), bytes.fromhex(esperado))
    except (ValueError, AttributeError):
        return False


_HASH_FALSO = hashear("clave-que-nadie-tiene")       # para gastar el mismo tiempo si el usuario no existe


def _tablas(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS familias(familia_id TEXT PRIMARY KEY, nombre TEXT, creada TEXT);
    CREATE TABLE IF NOT EXISTS usuarios(
        usuario_id INTEGER PRIMARY KEY, familia_id TEXT NOT NULL, nombre TEXT NOT NULL UNIQUE,
        clave_hash TEXT NOT NULL, creado TEXT, ultimo_acceso TEXT);
    CREATE TABLE IF NOT EXISTS sesiones(
        sesion_hash TEXT PRIMARY KEY, usuario_id INTEGER NOT NULL, creada TEXT, expira TEXT, ultimo_uso TEXT);
    CREATE TABLE IF NOT EXISTS intentos_login(ts TEXT NOT NULL, ip TEXT, usuario TEXT);
    CREATE INDEX IF NOT EXISTS intentos_ts ON intentos_login(ts);
    CREATE TABLE IF NOT EXISTS auditoria(
        id INTEGER PRIMARY KEY, familia_id TEXT, usuario_id INTEGER, accion TEXT, objeto TEXT, fecha TEXT);
    """)


def _db():
    """Conexión a la base de la memoria con las tablas del panel creadas."""
    ruta = memoria.ruta_db()
    con = memoria._abrir()                       # crea/migra las tablas de la memoria
    if ("padres", ruta) not in memoria._inicializadas:
        _tablas(con)
        con.commit()
        memoria._inicializadas.add(("padres", ruta))
    return con


class _Con:
    def __enter__(self):
        self.con = _db()
        return self.con

    def __exit__(self, tipo, valor, tb):
        if tipo is None:
            self.con.commit()
        self.con.close()


def conectar():
    return _Con()


# ---------- Usuarios ----------
def crear_usuario(nombre, clave, familia_id="1", nombre_familia="Mi familia"):
    nombre = nombre.strip().lower()
    if not nombre or len(nombre) > 40:
        raise ValueError("Nombre de usuario vacío o demasiado largo.")
    if len(clave) < MIN_CLAVE:
        raise ClaveDebil(f"La contraseña debe tener al menos {MIN_CLAVE} caracteres.")
    ahora = _iso(_ahora())
    with conectar() as con:
        con.execute("INSERT OR IGNORE INTO familias(familia_id, nombre, creada) VALUES (?,?,?)",
                    (str(familia_id), nombre_familia, ahora))
        cur = con.execute("INSERT INTO usuarios(familia_id, nombre, clave_hash, creado) VALUES (?,?,?,?)",
                          (str(familia_id), nombre, hashear(clave), ahora))
        return cur.lastrowid


def cambiar_clave(nombre, clave_nueva):
    if len(clave_nueva) < MIN_CLAVE:
        raise ClaveDebil(f"La contraseña debe tener al menos {MIN_CLAVE} caracteres.")
    with conectar() as con:
        fila = con.execute("SELECT usuario_id FROM usuarios WHERE nombre=?", (nombre.strip().lower(),)).fetchone()
        if not fila:
            return False
        con.execute("UPDATE usuarios SET clave_hash=? WHERE usuario_id=?", (hashear(clave_nueva), fila[0]))
        con.execute("DELETE FROM sesiones WHERE usuario_id=?", (fila[0],))       # cierra todas las sesiones
        return True


def cerrar_todas_las_sesiones(nombre=None):
    with conectar() as con:
        if nombre:
            return con.execute(
                "DELETE FROM sesiones WHERE usuario_id IN (SELECT usuario_id FROM usuarios WHERE nombre=?)",
                (nombre.strip().lower(),)).rowcount
        return con.execute("DELETE FROM sesiones").rowcount


def listar_usuarios():
    with conectar() as con:
        return [dict(f) for f in con.execute("SELECT usuario_id, familia_id, nombre, ultimo_acceso FROM usuarios")]


# ---------- Límite de intentos ----------
def _bloqueo_activo(con, ip, usuario):
    """Segundos de bloqueo restantes (0 si puede intentar)."""
    desde = _iso(_ahora() - timedelta(minutes=VENTANA_MIN))
    for campo, valor, limite in (("ip", ip, LIMITE_FALLOS), ("usuario", usuario, LIMITE_FALLOS_USUARIO)):
        if not valor:
            continue
        filas = [f[0] for f in con.execute(
            f"SELECT ts FROM intentos_login WHERE {campo}=? AND ts>=? ORDER BY ts", (valor, desde))]
        if len(filas) >= limite:
            libre = datetime.fromisoformat(filas[-limite]) + timedelta(minutes=VENTANA_MIN)
            return max(1, int((libre - _ahora()).total_seconds()))
    return 0


def iniciar_sesion(nombre, clave, ip=""):
    """Devuelve (token, usuario_dict) o None si las credenciales no valen. Lanza Bloqueado si hay demasiados fallos.
    Los fallos de un usuario que NO existe también cuentan (así no se pueden adivinar nombres)."""
    nombre = (nombre or "").strip().lower()[:40]
    with conectar() as con:
        espera = _bloqueo_activo(con, ip, nombre)
        if espera:
            raise Bloqueado(espera)
        fila = con.execute("SELECT * FROM usuarios WHERE nombre=?", (nombre,)).fetchone()
        valida = verificar_hash(clave or "", fila["clave_hash"] if fila else _HASH_FALSO)
        ahora = _ahora()
        if not (fila and valida):
            con.execute("INSERT INTO intentos_login(ts, ip, usuario) VALUES (?,?,?)", (_iso(ahora), ip, nombre))
            con.execute("DELETE FROM intentos_login WHERE ts<?", (_iso(ahora - timedelta(days=2)),))
            return None
        con.execute("DELETE FROM intentos_login WHERE usuario=? OR ip=?", (nombre, ip))
        token = secrets.token_urlsafe(32)
        con.execute("INSERT INTO sesiones(sesion_hash, usuario_id, creada, expira, ultimo_uso) VALUES (?,?,?,?,?)",
                    (_sha(token), fila["usuario_id"], _iso(ahora), _iso(ahora + timedelta(days=SESION_DIAS_MAX)),
                     _iso(ahora)))
        con.execute("UPDATE usuarios SET ultimo_acceso=? WHERE usuario_id=?", (_iso(ahora), fila["usuario_id"]))
        return token, {"usuario_id": fila["usuario_id"], "familia_id": fila["familia_id"], "nombre": fila["nombre"]}


def _sha(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------- Sesiones ----------
def usuario_de_sesion(token):
    """Usuario {usuario_id, familia_id, nombre} de un token válido (y renueva su último uso), o None."""
    if not token or len(token) > 100:
        return None
    ahora = _ahora()
    with conectar() as con:
        fila = con.execute(
            "SELECT s.sesion_hash, s.expira, s.ultimo_uso, u.usuario_id, u.familia_id, u.nombre "
            "FROM sesiones s JOIN usuarios u ON u.usuario_id = s.usuario_id WHERE s.sesion_hash=?",
            (_sha(token),)).fetchone()
        if not fila:
            return None
        vencida = (datetime.fromisoformat(fila["expira"]) < ahora or
                   datetime.fromisoformat(fila["ultimo_uso"]) + timedelta(days=SESION_DIAS_INACTIVA) < ahora)
        if vencida:
            con.execute("DELETE FROM sesiones WHERE sesion_hash=?", (fila["sesion_hash"],))
            return None
        con.execute("UPDATE sesiones SET ultimo_uso=? WHERE sesion_hash=?", (_iso(ahora), fila["sesion_hash"]))
        return {"usuario_id": fila["usuario_id"], "familia_id": fila["familia_id"], "nombre": fila["nombre"]}


def cerrar_sesion(token):
    if not token:
        return
    with conectar() as con:
        con.execute("DELETE FROM sesiones WHERE sesion_hash=?", (_sha(token),))


def comprobar_clave(usuario_id, clave, ip=""):
    """Verifica la contraseña actual (para cambiarla). Cuenta como intento fallido y lanza Bloqueado si hay demasiados."""
    with conectar() as con:
        fila = con.execute("SELECT nombre, clave_hash FROM usuarios WHERE usuario_id=?", (usuario_id,)).fetchone()
        if not fila:
            return False
        espera = _bloqueo_activo(con, ip, fila["nombre"])
        if espera:
            raise Bloqueado(espera)
        if verificar_hash(clave or "", fila["clave_hash"]):
            return True
        con.execute("INSERT INTO intentos_login(ts, ip, usuario) VALUES (?,?,?)", (_iso(_ahora()), ip, fila["nombre"]))
        return False


def cambiar_clave_de(usuario_id, clave_nueva, conservar_token=None):
    """Cambia la clave y cierra las demás sesiones (se conserva la actual)."""
    if len(clave_nueva) < MIN_CLAVE:
        raise ClaveDebil(f"La contraseña debe tener al menos {MIN_CLAVE} caracteres.")
    with conectar() as con:
        con.execute("UPDATE usuarios SET clave_hash=? WHERE usuario_id=?", (hashear(clave_nueva), usuario_id))
        if conservar_token:
            con.execute("DELETE FROM sesiones WHERE usuario_id=? AND sesion_hash!=?", (usuario_id, _sha(conservar_token)))
        else:
            con.execute("DELETE FROM sesiones WHERE usuario_id=?", (usuario_id,))


def auditar(usuario, accion, objeto=""):
    """Registra quién hizo qué (sin contenido de los hechos, solo ids)."""
    with conectar() as con:
        con.execute("INSERT INTO auditoria(familia_id, usuario_id, accion, objeto, fecha) VALUES (?,?,?,?,?)",
                    (usuario["familia_id"], usuario["usuario_id"], accion, str(objeto)[:60], _iso(_ahora())))
