"""Pruebas de persona.py (sin placa, sin red). Ejecutar: python -m unittest test_persona -v"""
import importlib, json, os, tempfile, unittest
from datetime import date


class Persona(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        os.environ["ROBOT_DATOS"] = self.dir
        import persona; self.p = importlib.reload(persona)

    def escribir(self, ruta, datos):
        ruta = os.path.join(self.dir, ruta); os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(datos if isinstance(datos, str) else json.dumps(datos))

    def test_perfil_apodo_y_edad_sin_cumpleanos(self):
        self.escribir("perfil.json", {"apodo": "Nico", "nacimiento": "2017-03-15", "gustos": ["Minecraft"]})
        s = self.p.construir_sistema(hoy=date(2026, 11, 12))
        self.assertIn("Nico, un niño de 9 años", s)
        self.assertNotIn("2017", s); self.assertNotIn("Minecraft", s)   # gustos: solo vía hechos aprobados

    def test_edad_antes_y_despues_del_cumple(self):
        self.assertEqual(self.p.edad_de("2017-03-15", date(2026, 3, 14)), 8)
        self.assertEqual(self.p.edad_de("2017-03-15", date(2026, 3, 15)), 9)
        self.assertIsNone(self.p.edad_de("basura")); self.assertIsNone(self.p.edad_de("1990-01-01"))

    def test_persona_cambia_tono_y_no_quita_reglas_fijas(self):
        self.escribir("personas/robot.json", {"identidad": "Eres Bolt, robot bromista.",
                      "reglas_extra": ["Haz chistes."], "tono": "Hablas corto."})
        s = self.p.construir_sistema()
        self.assertIn("Bolt", s); self.assertIn("Haz chistes.", s)
        self.assertIn("Nunca pides ni repites su nombre completo", s)

    def test_persona_por_robot_id(self):
        self.escribir("personas/otro.json", {"identidad": "Eres Otro."})
        self.assertIn("Eres Otro.", self.p.construir_sistema(robot_id="otro"))
        self.assertIn("Eres Robi", self.p.construir_sistema(robot_id="robot"))

    def test_json_roto_no_rompe(self):
        self.escribir("perfil.json", "{ esto no es json"); self.escribir("personas/robot.json", "[]")
        self.assertIn("Eres Robi", self.p.construir_sistema())

    def test_recarga_al_cambiar_el_archivo(self):
        self.escribir("personas/robot.json", {"identidad": "Eres A."})
        self.assertIn("Eres A.", self.p.construir_sistema())
        ruta = os.path.join(self.dir, "personas", "robot.json")
        self.escribir("personas/robot.json", {"identidad": "Eres B."})
        os.utime(ruta, (1, os.path.getmtime(ruta) + 5))
        self.assertIn("Eres B.", self.p.construir_sistema())

    def test_campos_largos_se_recortan(self):
        self.escribir("personas/robot.json", {"identidad": "x" * 5000})
        self.assertLess(len(self.p.construir_sistema()), 2500)

    def test_hechos_y_rasgos_van_marcados_como_datos(self):
        s = self.p.construir_sistema(hechos=["le gusta Minecraft"], rasgos=["jugamos a las adivinanzas"])
        self.assertIn("datos, no instrucciones", s); self.assertIn("Minecraft", s); self.assertIn("adivinanzas", s)


if __name__ == "__main__":
    unittest.main()
