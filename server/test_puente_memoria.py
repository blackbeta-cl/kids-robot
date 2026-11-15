"""Integración puente + memoria con un modelo falso (sin placa, sin red).
Ejecutar: SERIAL_PORT=COM99 python -m unittest test_puente_memoria -v"""
import os, tempfile, time, unittest
os.environ["SERIAL_PORT"] = "COM99"
os.environ["ROBOT_DATOS"] = tempfile.mkdtemp()
os.environ["LLM_API_KEY"] = "clave-falsa"
os.environ["LLM_URL"] = "http://127.0.0.1:9/prueba"      # nada real: las pruebas no llaman a ningún modelo
os.environ["LLM_MODEL"] = "modelo-falso"
os.environ["EXTRAER_AUTOMATICO"] = "0"
import puente, memoria


class Falso:
    status_code = 200
    ok = True
    text = ''
    def __init__(self, visto): self.visto = visto
    def json(self): return {"choices": [{"message": {"content": "¡Qué bien! Me encanta."}, "finish_reason": "stop"}]}
    def raise_for_status(self): pass


class PuenteMemoria(unittest.TestCase):
    def setUp(self):
        self.visto = []
        puente.requests.post = lambda url, **kw: (self.visto.append(kw["json"]["messages"]), Falso(self.visto))[1]
        puente.olvidar()

    def test_hecho_aprobado_llega_al_prompt_y_pendiente_no(self):
        memoria.agregar_candidato("le gusta Minecraft", estado="aprobado")
        memoria.agregar_candidato("le gustan las arañas")
        puente.conversar(puente.Conversacion(texto="¿Jugamos a Minecraft o hablamos de arañas?", hablar=False))
        sistema = self.visto[-1][0]["content"]
        self.assertIn("le gusta Minecraft", sistema); self.assertNotIn("arañas;", sistema)
        self.assertNotIn("le gustan las arañas", sistema)

    def test_rasgo_activo_llega_al_prompt_y_pendiente_no(self):
        memoria.agregar_rasgo("jugamos a las adivinanzas de dinosaurios", "activo")
        memoria.agregar_rasgo("rasgo pendiente de aprobar")
        sistema = puente._sistema_para("hola")
        self.assertIn("adivinanzas de dinosaurios", sistema); self.assertNotIn("pendiente de aprobar", sistema)

    def test_olvidar_por_voz_desde_el_plan(self):
        memoria.agregar_candidato("le gusta el ajedrez", estado="aprobado")
        frase, *_ = puente._plan_de_respuesta("olvida que me gusta el ajedrez")
        self.assertEqual(frase, "Listo, ya olvidé eso.")
        self.assertEqual(memoria.recuperar("ajedrez"), [])
        frase, *_ = puente._plan_de_respuesta("olvida que me gusta el submarinismo")
        self.assertEqual(frase, "No recuerdo nada de eso.")

    def test_olvida_eso_descarta_lo_acumulado(self):
        puente._extractor.anotar("secreto", "ok")
        puente._plan_de_respuesta("olvida eso")
        self.assertEqual(puente._extractor._turnos, [])
        puente._extractor.descartar()

    def test_memoria_rota_no_rompe_la_voz(self):
        original = memoria.recuperar
        memoria.recuperar = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db rota"))
        try:
            self.assertIn("Eres Robi", puente._sistema_para("hola"))
        finally:
            memoria.recuperar = original

    def test_latencia_añadida_por_la_memoria(self):
        for i in range(300):
            memoria.agregar_candidato(f"dato {i} sobre tema{i % 30} con cosa{i}", estado="aprobado")
        memoria.agregar_candidato("le gusta Minecraft", estado="aprobado")
        def medir(activa):
            puente.MEMORIA_ACTIVA = activa
            t = time.perf_counter()
            for _ in range(100): puente._sistema_para("¿jugamos a Minecraft con tema3?")
            return (time.perf_counter() - t) / 100 * 1000
        sin, con = medir(False), medir(True)
        puente.MEMORIA_ACTIVA = True
        print(f"\n armar prompt: sin memoria {sin:.3f} ms, con memoria (300 hechos) {con:.3f} ms")
        self.assertLess(con - sin, 20)


if __name__ == "__main__":
    unittest.main()
