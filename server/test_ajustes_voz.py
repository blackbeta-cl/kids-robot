"""Ajustes del 13-nov: «Robot» oído como «Roblox», día y hora en el prompt, verbos vagos en la memoria.
Ejecutar: python -m unittest test_ajustes_voz -v   (no necesita faster-whisper: se reemplaza por un módulo falso)"""
import os, sys, tempfile, types, unittest
from datetime import datetime, timedelta, timezone
os.environ["ROBOT_DATOS"] = tempfile.mkdtemp()
os.environ.setdefault("SERIAL_PORT", "COM99")
sys.modules.setdefault("faster_whisper", types.SimpleNamespace(WhisperModel=object))
import persona, memoria
from asistente_voz import corregir_robot, HOTWORDS, PROMPT_ASR


class RobotNoRoblox(unittest.TestCase):
    def test_llamada_suelta_es_robot(self):
        for dicho in ("Roblox", "Roblox.", "Roblox, Roblox", "Rolls, rolls, rolls, rolls, rolls.", "Robox", "¡Roblox!", "robots"):
            self.assertEqual(corregir_robot(dicho), "Robot", dicho)

    def test_el_juego_en_una_frase_no_se_toca(self):
        for dicho in ("Roblox es genial", "Quiero jugar Roblox", "¿Sabes qué es Roblox?", "Esto es Roblox.", "Hola robot", "Roblox y Minecraft"):
            self.assertEqual(corregir_robot(dicho), dicho, dicho)

    def test_vacio(self):
        self.assertEqual(corregir_robot(""), "")

    def test_whisper_prefiere_robot_y_su_nombre(self):
        self.assertIn("Robot", HOTWORDS.split()); self.assertIn("Robi", HOTWORDS.split())
        self.assertIn("Robot", PROMPT_ASR)


class DiaYHora(unittest.TestCase):
    viernes = datetime(2026, 11, 13, 17, 50, tzinfo=timezone(timedelta(hours=-3)))

    def test_sin_ahora_el_prompt_no_cambia(self):
        self.assertEqual(persona.construir_sistema(), persona.construir_sistema(ahora=None))
        self.assertNotIn("Hoy es", persona.construir_sistema())

    def test_con_ahora_dice_el_dia_y_no_inventa_obligaciones(self):
        s = persona.construir_sistema(ahora=self.viernes)
        self.assertIn("Hoy es viernes 13 de noviembre de 2026 y son las 17:50 (hora local)", s)
        self.assertIn("no le mandes a hacer cosas", s)
        self.assertLess(len(s), 2500)

    def test_dias_y_meses(self):
        self.assertIn("domingo 1 de marzo", persona.construir_sistema(ahora=datetime(2026, 3, 1, 9, 5)))

    def test_ahora_robot_devuelve_hora_local(self):
        a = persona.ahora_robot()
        self.assertIsNotNone(a.utcoffset())
        self.assertEqual(a.utcoffset(), datetime.now(persona.zona_robot()).utcoffset())


class VerbosVagos(unittest.TestCase):
    def test_me_gustan_los_gatos_no_trae_otro_gusto(self):
        memoria.agregar_candidato("le gusta escuchar historias sobre el planeta Zorbulandia", estado="aprobado")
        self.assertEqual(memoria.recuperar("me gustan los gatos"), [])
        self.assertEqual(memoria.recuperar("cuéntame algo del planeta Zorbulandia"),
                         ["le gusta escuchar historias sobre el planeta Zorbulandia"])


if __name__ == "__main__":
    unittest.main()
