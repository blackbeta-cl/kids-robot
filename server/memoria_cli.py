"""Herramienta de los padres para la memoria del robot. Corre en el equipo donde está memoria.db.

  python memoria_cli.py pendientes            hechos que el modelo propuso y esperan tu decisión
  python memoria_cli.py aprobar 3 4 | todos   los deja disponibles para el robot
  python memoria_cli.py rechazar 5            no se usará (queda para no proponerlo de nuevo)
  python memoria_cli.py listar [estado]       todos, o solo los 'aprobado', 'pendiente'...
  python memoria_cli.py editar 3 "le gusta Minecraft y Roblox"
  python memoria_cli.py agregar "tiene prueba de matemáticas" [--vence 2026-11-20]   (queda aprobado)
  python memoria_cli.py borrar 3              borra de verdad un hecho
  python memoria_cli.py purgar                borra de verdad los rechazados y olvidados
  python memoria_cli.py buscar "minecraft"    qué recuperaría el robot con esa frase
  python memoria_cli.py exportar              todo en JSON
  python memoria_cli.py borrar-todo           borra toda la memoria (pide confirmación)

Rasgos y recuerdos compartidos (personalidad que evoluciona; máx. 5 activos, nada cambia sin tu aprobación):
  python memoria_cli.py semanal               el modelo propone rasgos a partir de los hechos aprobados de la semana
  python memoria_cli.py rasgos [estado]       lista (pendiente, activo, retirado)
  python memoria_cli.py aprobar-rasgo 2       lo activa (falla si ya hay 5 activos)
  python memoria_cli.py retirar-rasgo 2       lo desactiva
  python memoria_cli.py agregar-rasgo "texto" lo agrega ya activo
  python memoria_cli.py borrar-rasgo 2
"""
import entorno  # noqa: F401  (carga server/.env antes de leer la configuración)
import argparse
import json
import sys

import memoria


def _linea(h):
    vence = f" (vence {h['vence']})" if h["vence"] else ""
    return f"[{h['id']:>3}] {h['estado']:<9} {h['texto']}{vence}\n        {h['fuente'] or ''}"


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Memoria del robot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pendientes")
    p = sub.add_parser("aprobar"); p.add_argument("ids", nargs="+")
    p = sub.add_parser("rechazar"); p.add_argument("ids", nargs="+", type=int)
    p = sub.add_parser("listar"); p.add_argument("estado", nargs="?", choices=memoria.ESTADOS)
    p = sub.add_parser("editar"); p.add_argument("id", type=int); p.add_argument("texto")
    p = sub.add_parser("agregar"); p.add_argument("texto"); p.add_argument("--vence")
    p = sub.add_parser("borrar"); p.add_argument("id", type=int)
    sub.add_parser("purgar")
    p = sub.add_parser("buscar"); p.add_argument("frase")
    sub.add_parser("exportar")
    sub.add_parser("borrar-todo")
    sub.add_parser("semanal")
    p = sub.add_parser("rasgos"); p.add_argument("estado", nargs="?", choices=memoria.ESTADOS_RASGO)
    for nombre in ("aprobar-rasgo", "retirar-rasgo", "borrar-rasgo"):
        p = sub.add_parser(nombre); p.add_argument("id", type=int)
    p = sub.add_parser("agregar-rasgo"); p.add_argument("texto")
    a = ap.parse_args(argv)

    if a.cmd == "pendientes":
        filas = memoria.listar("pendiente")
        print("\n".join(_linea(h) for h in filas) or "No hay hechos pendientes.")
    elif a.cmd == "aprobar":
        ids = [h["id"] for h in memoria.listar("pendiente")] if a.ids == ["todos"] else [int(i) for i in a.ids]
        print(f"Aprobados: {sum(memoria.decidir(i, 'aprobado') for i in ids)}")
    elif a.cmd == "rechazar":
        print(f"Rechazados: {sum(memoria.decidir(i, 'rechazado') for i in a.ids)}")
    elif a.cmd == "listar":
        print("\n".join(_linea(h) for h in memoria.listar(a.estado)) or "Vacío.")
    elif a.cmd == "editar":
        print("Editado." if memoria.editar(a.id, a.texto) else "No existe ese id.")
    elif a.cmd == "agregar":
        id_hecho = memoria.agregar_candidato(a.texto, "escrito por los padres", "", a.vence, estado="aprobado")
        print(f"Agregado ({id_hecho})." if id_hecho else "No se agregó: ya existe, es muy largo o parece un dato sensible.")
    elif a.cmd == "borrar":
        print("Borrado." if memoria.borrar(a.id) else "No existe ese id.")
    elif a.cmd == "purgar":
        print(f"Borrados: {memoria.purgar()}")
    elif a.cmd == "buscar":
        print("\n".join(f"- {t}" for t in memoria.recuperar(a.frase)) or "(nada relevante)")
    elif a.cmd == "exportar":
        print(json.dumps(memoria.listar(), ensure_ascii=False, indent=2))
    elif a.cmd == "semanal":
        import cerebro
        ids = memoria.proponer_rasgos(cerebro.llamar_modelo)
        print(f"Propuestos {len(ids)} rasgo(s). Revísalos con: python memoria_cli.py rasgos pendiente" if ids
              else "Nada que proponer esta semana.")
    elif a.cmd == "rasgos":
        for r in memoria.listar_rasgos(a.estado):
            print(f"[{r['id']:>3}] {r['estado']:<9} {r['texto']}")
    elif a.cmd in ("aprobar-rasgo", "retirar-rasgo"):
        try:
            hecho = memoria.decidir_rasgo(a.id, "activo" if a.cmd == "aprobar-rasgo" else "retirado")
            print("Listo." if hecho else "No existe ese id.")
        except ValueError as error:
            print(error)
    elif a.cmd == "borrar-rasgo":
        print("Borrado." if memoria.borrar_rasgo(a.id) else "No existe ese id.")
    elif a.cmd == "agregar-rasgo":
        id_rasgo = memoria.agregar_rasgo(a.texto, "activo")
        print(f"Agregado ({id_rasgo})." if id_rasgo else "No se agregó: ya existe, es largo, sensible o ya hay 5 activos.")
    elif a.cmd == "borrar-todo":
        if input("Esto borra TODA la memoria. Escribe 'borrar' para confirmar: ").strip() == "borrar":
            print(f"Borrados: {memoria.borrar_todo()}")
        else:
            print("Cancelado.")


if __name__ == "__main__":
    main()
