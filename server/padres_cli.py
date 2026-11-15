"""Administración de usuarios del panel de padres. Corre en el equipo donde está memoria.db (nunca por la web).

  python padres_cli.py crear-usuario padre            pide la contraseña (no se muestra ni se pasa por argumento)
  python padres_cli.py reiniciar-clave padre          nueva contraseña; cierra todas sus sesiones
  python padres_cli.py cerrar-sesiones [usuario]     cierra las sesiones abiertas (de todos, o de uno)
  python padres_cli.py listar                        usuarios y último acceso
"""
import argparse
import getpass
import sys

import padres_auth as auth


def _pedir_clave():
    clave = getpass.getpass("Contraseña (mínimo %d caracteres): " % auth.MIN_CLAVE)
    if getpass.getpass("Repítela: ") != clave:
        sys.exit("Las contraseñas no coinciden.")
    return clave


def main(argv=None):
    ap = argparse.ArgumentParser(description="Usuarios del panel de padres")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("crear-usuario").add_argument("nombre")
    sub.add_parser("reiniciar-clave").add_argument("nombre")
    sub.add_parser("cerrar-sesiones").add_argument("nombre", nargs="?")
    sub.add_parser("listar")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "crear-usuario":
            auth.crear_usuario(a.nombre, _pedir_clave())
            print(f"Usuario «{a.nombre.strip().lower()}» creado.")
        elif a.cmd == "reiniciar-clave":
            print("Listo; sesiones cerradas." if auth.cambiar_clave(a.nombre, _pedir_clave()) else "No existe ese usuario.")
        elif a.cmd == "cerrar-sesiones":
            print(f"{auth.cerrar_todas_las_sesiones(a.nombre)} sesión(es) cerrada(s).")
        else:
            for u in auth.listar_usuarios():
                print(f"{u['nombre']:<20} familia {u['familia_id']}  último acceso: {u['ultimo_acceso'] or 'nunca'}")
    except (auth.ClaveDebil, ValueError) as error:
        sys.exit(str(error))
    except Exception as error:       # p. ej. usuario duplicado
        sys.exit(f"No se pudo: {error}")


if __name__ == "__main__":
    main()
