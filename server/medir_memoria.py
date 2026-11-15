"""Mide cuánto añaden perfil, persona, recuperación de hechos, rasgos y extracción al camino de voz.
Sin placa ni red (modelo falso). Con datos de ejemplo en una carpeta temporal; no toca server/datos/.

  python medir_memoria.py [--hechos 500] [--corridas 300] [--modelo]

--modelo además compara el primer trozo del modelo REAL (streaming) con y sin memoria (usa LLM_API_KEY,
manda solo frases de ejemplo y hechos inventados; 10+10 llamadas, alternadas).
Objetivo: memoria + persona ≤ ~100-200 ms antes de la primera frase.
"""
import argparse, json, os, statistics as st, tempfile, threading, time

os.environ.setdefault("SERIAL_PORT", "COM99")
os.environ["ROBOT_DATOS"] = tempfile.mkdtemp()
os.environ["EXTRAER_AUTOMATICO"] = "0"      # la extracción se mide aparte, a propósito

import memoria, persona, puente  # noqa: E402

CONSULTAS = ["¿Jugamos a Minecraft?", "Cuéntame algo de dinosaurios", "¿Qué hago hoy después del colegio?",
             "Tengo prueba de matemáticas el viernes", "¿Cuántas patas tiene una araña?", "Hola Robi"]


def ms(f, n):
    muestras = []
    for i in range(n):
        t = time.perf_counter(); f(CONSULTAS[i % len(CONSULTAS)]); muestras.append((time.perf_counter() - t) * 1000)
    muestras.sort()
    return st.mean(muestras), muestras[len(muestras) // 2], muestras[int(len(muestras) * 0.99) - 1]


def fila(nombre, r):
    print(f"  {nombre:<46} media {r[0]:7.3f} ms   mediana {r[1]:7.3f}   p99 {r[2]:7.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hechos", type=int, default=500)
    ap.add_argument("--corridas", type=int, default=300)
    ap.add_argument("--modelo", action="store_true")
    ap.add_argument("--n-modelo", dest="n_modelo", type=int, default=20)
    a = ap.parse_args()

    # Datos de ejemplo: perfil, persona, hechos aprobados (la mayoría sin relación) y 5 rasgos.
    d = persona.DATOS_DIR
    os.makedirs(os.path.join(d, "personas"), exist_ok=True)
    json.dump({"perfil_id": "demo", "apodo": "Nico", "nacimiento": "2017-03-15"}, open(os.path.join(d, "perfil.json"), "w"))
    json.dump({"identidad": "Eres Robi, un robot bromista.", "reglas_extra": ["Felicita el esfuerzo."]},
              open(os.path.join(d, "personas", "robot.json"), "w"))
    for i in range(a.hechos):
        memoria.agregar_candidato(f"hecho {i} sobre tema{i % 40} cosa{i % 17} palabra{i}", estado="aprobado")
    for t in ("le gusta Minecraft", "le encantan los dinosaurios", "tiene prueba de matemáticas el viernes"):
        memoria.agregar_candidato(t, estado="aprobado")
    for k in range(5):
        memoria.agregar_rasgo(f"recuerdo compartido número{k} alfa{k} beta{k}", "activo")
    print(f"Datos de ejemplo: {a.hechos + 3} hechos aprobados, 5 rasgos activos, perfil y persona. {a.corridas} corridas.\n")

    print("Costo por pieza (lo que se suma antes de llamar al modelo):")
    puente.MEMORIA_ACTIVA = False
    sin = ms(lambda q: puente._sistema_para(q), a.corridas)
    fila("prompt sin memoria (perfil+persona, con archivos)", sin)
    persona.DATOS_DIR = os.path.join(d, "vacio")                     # sin archivos: lo de antes
    base = ms(lambda q: puente._sistema_para(q), a.corridas)
    persona.DATOS_DIR = d
    fila("prompt de antes (sin archivos ni memoria)", base)
    puente.MEMORIA_ACTIVA = True
    fila("recuperar hechos (FTS5)", ms(lambda q: memoria.recuperar(q), a.corridas))
    fila("rasgos activos", ms(lambda q: memoria.rasgos_activos(), a.corridas))
    con = ms(lambda q: puente._sistema_para(q), a.corridas)
    fila("prompt COMPLETO con memoria", con)
    extra = con[0] - base[0]
    print(f"\n  Añadido total sobre lo de antes: {extra:.2f} ms de media (presupuesto 100-200 ms) -> "
          f"{'OK' if extra < 100 else 'REVISAR'}")

    # La extracción corre en un hilo de fondo: ¿molesta al camino de voz mientras escribe en la base?
    def modelo_lento(m):
        time.sleep(0.5); return json.dumps([{"texto": f"le gusta el tema{time.time_ns()}", "categoria": "gusto"} for _ in range(5)])
    stop = threading.Event()
    def trabajo():
        while not stop.is_set():
            memoria.extraer([("juego mucho", "¡qué bien!")] * 10, modelo_lento)
    hilo = threading.Thread(target=trabajo, daemon=True); hilo.start()
    time.sleep(0.2)
    durante = ms(lambda q: puente._sistema_para(q), a.corridas)
    stop.set(); hilo.join(3)
    print("\nCon la extracción corriendo en segundo plano (escribe en la base sin parar):")
    fila("prompt COMPLETO con extracción concurrente", durante)
    print(f"  Peor caso (p99) añadido por la extracción: {durante[2] - con[2]:.2f} ms")

    n_base, n_con = len(puente._sistema_para("hola")), len(puente._sistema_para("¿jugamos a Minecraft con dinosaurios?"))
    print(f"\nTamaño del prompt: {n_base} -> {n_con} caracteres (~{(n_con - n_base) // 4} tokens más).")

    if a.modelo:
        memoria.borrar_todo()                        # para el modelo real, datos verosímiles (los de arriba son relleno)
        for t in ("le gusta Minecraft", "le encantan los dinosaurios", "tiene prueba de matemáticas el viernes",
                  "su mascota es un perro llamado Toby", "está aprendiendo a andar en bicicleta"):
            memoria.agregar_candidato(t, estado="aprobado")
        for t in ("le gusta que le cuente datos de dinosaurios", "estamos animándolo con la prueba de matemáticas"):
            memoria.agregar_rasgo(t, "activo")
        print("\nModelo real (primer trozo, streaming; corridas alternadas en orden aleatorio):")
        q = "Hola, ¿qué hacemos hoy con Minecraft y los dinosaurios?"
        r = {False: [], True: []}
        import random
        for _ in range(a.n_modelo):
            orden = [False, True]; random.shuffle(orden)         # el orden no debe favorecer a ninguno
            for activa in orden:
                puente.MEMORIA_ACTIVA = activa; puente.olvidar()
                t = time.time()
                msgs = [{"role": "system", "content": puente._sistema_para(q)}, {"role": "user", "content": q}]
                for _t in puente._trozos_del_modelo(msgs, time.time() + 25):
                    break
                r[activa].append(time.time() - t)
        for activa in (False, True):
            print(f"  {'con memoria' if activa else 'sin memoria':<12} mediana {st.median(r[activa]):.2f} s  "
                  f"media {st.mean(r[activa]):.2f} s  (n={len(r[activa])})")
        for activa in (False, True):
            print(f"  {'con memoria' if activa else 'sin memoria':<12} min {min(r[activa]):.2f}  max {max(r[activa]):.2f}")


if __name__ == "__main__":
    main()
