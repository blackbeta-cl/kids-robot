"""Pruebas de agenda.py (sin placa ni red). Ejecutar: python -m unittest test_agenda -v"""
import importlib
import os
import tempfile
import unittest
from datetime import date, datetime, time, timedelta


class Agenda(unittest.TestCase):
    def setUp(self):
        os.environ["ROBOT_DATOS"] = tempfile.mkdtemp()
        import persona
        importlib.reload(persona)
        import memoria
        importlib.reload(memoria)
        import agenda
        self.a = importlib.reload(agenda)
        self.zona = persona.zona_robot()
        self.hoy = persona.ahora_robot().date()

    def ahora(self, hh=12, mm=0, dia=None):
        return datetime.combine(dia or self.hoy, time(hh, mm), tzinfo=self.zona)

    def crear(self, tipo="recordatorio", titulo="hacer la tarea", **kw):
        kw.setdefault("hora", "17:00")
        kw.setdefault("fecha", self.hoy.isoformat())
        return self.a.crear_evento(tipo, titulo, **kw)

    def activar_avisos(self, permitir_alarma=False):
        return self.a.guardar_ajustes(avisos_activos=True, silencio_desde="21:30", silencio_hasta="07:30",
                                      permitir_alarma_silencio=permitir_alarma)

    # ---------- Alta y validación ----------

    def test_crear_recordatorio_y_listar(self):
        evento = self.crear()
        self.assertEqual(evento["tipo"], "recordatorio")
        self.assertEqual(evento["titulo"], "hacer la tarea")
        self.assertEqual(evento["dias"], [])
        self.assertTrue(evento["activo"])
        self.assertEqual(len(self.a.listar_eventos()), 1)
        self.assertEqual(self.a.obtener_evento(evento["id"])["hora"], "17:00")

    def test_validaciones(self):
        malos = [
            dict(tipo="otro"),
            dict(titulo=""),
            dict(titulo="x" * 121),
            dict(texto_voz="x" * 201),
            dict(hora="25:00"),
            dict(hora=None),
            dict(fecha="2026-13-01"),
            dict(fecha=self.hoy.isoformat(), dias=[0]),
            dict(fecha=None, dias=None),
            dict(dias=[7]),
            dict(fecha=(self.hoy - timedelta(days=1)).isoformat()),
            dict(fecha=(self.hoy + timedelta(days=400)).isoformat()),
        ]
        for cambio in malos:
            datos = {"tipo": "recordatorio", "titulo": "algo", "hora": "17:00",
                     "fecha": self.hoy.isoformat(), "dias": None}
            datos.update(cambio)
            with self.assertRaises(ValueError, msg=str(cambio)):
                self.a.crear_evento(datos["tipo"], datos["titulo"], hora=datos["hora"],
                                    fecha=datos["fecha"], dias=datos["dias"],
                                    texto_voz=datos.get("texto_voz", ""))

    def test_limite_de_eventos_activos(self):
        for i in range(20):
            self.crear(dias=[0, 1, 2, 3, 4, 5, 6], titulo=f"evento {i}", fecha=None)
        with self.assertRaises(ValueError):
            self.crear(dias=[0], titulo="uno más", fecha=None)

    def test_dias_de_la_semana(self):
        evento = self.crear(dias=[4, 0, 2, 2], fecha=None)
        self.assertEqual(evento["dias"], [0, 2, 4])

    def test_temporizador(self):
        evento = self.a.crear_temporizador(10, ahora=self.ahora(12, 0))
        self.assertEqual(evento["tipo"], "temporizador")
        self.assertEqual(evento["hora"], "12:10")
        self.assertEqual(evento["fecha"], self.hoy.isoformat())
        self.assertEqual(self.a.texto_de_evento(evento), "¡Se acabó el tiempo!")
        with self.assertRaises(ValueError):
            self.a.crear_temporizador(0)

    # ---------- Repetición y materialización ----------

    def test_repeticion_semanal(self):
        self.crear(dias=[0, 1, 2, 3, 4], fecha=None, titulo="colegio")
        viernes = date(2026, 11, 13)
        self.a.materializar(ahora=self.ahora(7, 0, viernes), horizonte_horas=96)
        avisos = self.a.listar_avisos()
        self.assertEqual(len(avisos), 2)                  # viernes y lunes, sin fin de semana
        fechas = sorted(a["programado"][:10] for a in avisos)
        self.assertEqual(fechas, ["2026-11-13", "2026-11-16"])

    def test_materializar_no_duplica(self):
        self.crear(dias=[0, 1, 2, 3, 4, 5, 6], fecha=None)
        self.assertEqual(self.a.materializar(ahora=self.ahora(7, 0), horizonte_horas=48), 2)
        self.assertEqual(self.a.materializar(ahora=self.ahora(7, 0), horizonte_horas=48), 0)
        self.assertEqual(len(self.a.listar_avisos()), 2)

    def test_fuera_de_la_ventana_no_se_materializa(self):
        self.crear(hora="08:00")
        self.a.materializar(ahora=self.ahora(9, 0), horizonte_horas=1)
        self.assertEqual(len(self.a.listar_avisos()), 0)

    def test_cumpleanos(self):
        import memoria
        memoria.guardar_perfil("Nico", "2017-03-15", [])
        self.assertTrue(self.a.asegurar_cumpleanos())
        evento = [e for e in self.a.listar_eventos() if e["tipo"] == "cumpleanos"][0]
        self.assertEqual(evento["fecha"], "03-15")
        self.a.guardar_ajustes(avisos_activos=True)
        self.a.materializar(ahora=self.ahora(0, 0, date(2027, 3, 14)), horizonte_horas=72)
        aviso = self.a.debido(ahora=self.ahora(9, 0, date(2027, 3, 15)))
        self.assertIsNotNone(aviso)
        self.assertIn("¡Feliz cumpleaños, Nico!", aviso["texto"])
        self.assertIn("10 años", aviso["texto"])
        self.assertEqual(aviso["emocion"], "feliz")

    def test_29_de_febrero(self):
        import memoria
        memoria.guardar_perfil("Nico", "2016-02-29", [])
        self.a.asegurar_cumpleanos()
        self.a.materializar(ahora=self.ahora(0, 0, date(2027, 2, 28)), horizonte_horas=48)
        self.assertEqual(len(self.a.listar_avisos()), 0)          # 2027 no es bisiesto
        self.a.materializar(ahora=self.ahora(0, 0, date(2028, 2, 28)), horizonte_horas=48)
        self.assertEqual(len(self.a.listar_avisos()), 1)

    def test_cambio_de_horario_no_rompe(self):
        self.crear(dias=[0, 1, 2, 3, 4, 5, 6], fecha=None, hora="00:30")
        self.a.materializar(ahora=self.ahora(23, 0, date(2026, 9, 5)), horizonte_horas=6)
        self.assertGreaterEqual(len(self.a.listar_avisos()), 1)

    # ---------- Entrega ----------

    def test_entrega_limite_y_confirmacion(self):
        self.activar_avisos()
        self.crear(hora="12:00")
        self.a.materializar(ahora=self.ahora(11, 55), horizonte_horas=2)

        aviso = self.a.debido(ahora=self.ahora(12, 0))
        self.assertIsNotNone(aviso)
        self.assertIn("hacer la tarea", aviso["texto"])
        self.assertIsNone(self.a.debido(ahora=self.ahora(12, 0, dia=None) + timedelta(seconds=10)))
        self.assertEqual(self.a.debido(ahora=self.ahora(12, 1, ) + timedelta(seconds=1))["id"], aviso["id"])
        self.assertEqual(self.a.confirmar(aviso["id"], "dicho"), "dicho")
        self.assertEqual(self.a.confirmar(aviso["id"], "dicho"), "dicho")     # idempotente
        self.assertIsNone(self.a.debido(ahora=self.ahora(12, 5)))
        self.assertEqual(self.a.listar_avisos()[0]["estado"], "dicho")

    def test_ventana_de_atraso(self):
        self.activar_avisos()
        self.crear(hora="11:50")
        self.a.materializar(ahora=self.ahora(11, 49), horizonte_horas=1)
        self.assertIsNone(self.a.debido(ahora=self.ahora(12, 0)))
        aviso = self.a.listar_avisos()[0]
        self.assertEqual(aviso["estado"], "omitido")
        self.assertEqual(aviso["motivo"], "atrasado")

    def test_silencio(self):
        self.crear(tipo="recordatorio", titulo="tarea", hora="22:00")
        self.crear(tipo="alarma", titulo="dormir", hora="22:00")
        self.a.materializar(ahora=self.ahora(21, 0), horizonte_horas=3)

        self.a.guardar_ajustes(avisos_activos=True, silencio_desde="21:30", silencio_hasta="07:30",
                               permitir_alarma_silencio=False)
        self.assertIsNone(self.a.debido(ahora=self.ahora(22, 0)))

        self.a.guardar_ajustes(avisos_activos=True, silencio_desde="21:30", silencio_hasta="07:30",
                               permitir_alarma_silencio=True)
        aviso = self.a.debido(ahora=self.ahora(22, 0))
        self.assertIsNotNone(aviso)
        self.assertEqual(aviso["tipo"], "alarma")
        self.assertTrue(self.a.en_silencio(ahora=self.ahora(23, 0)))
        self.assertTrue(self.a.en_silencio(ahora=self.ahora(6, 0)))
        self.assertFalse(self.a.en_silencio(ahora=self.ahora(12, 0)))

    def test_avisos_apagados_y_prueba(self):
        evento = self.crear(hora="12:00")
        self.assertIsNone(self.a.debido(ahora=self.ahora(12, 0)))
        self.assertIsNotNone(self.a.probar_evento(evento["id"], ahora=self.ahora(12, 0)))
        aviso = self.a.debido(ahora=self.ahora(12, 0))
        self.assertIsNotNone(aviso)
        self.assertTrue(aviso["prueba"])

    def test_silencio_temporal(self):
        self.activar_avisos()
        self.crear(tipo="recordatorio", titulo="tarea", hora="13:00")
        self.crear(tipo="alarma", titulo="pastilla", hora="13:00")
        self.a.materializar(ahora=self.ahora(12, 0), horizonte_horas=2)
        self.a.silenciar(120, ahora=self.ahora(12, 0))
        self.assertTrue(self.a.en_silencio(ahora=self.ahora(12, 30)))

        aviso = self.a.debido(ahora=self.ahora(13, 0))
        self.assertIsNotNone(aviso)
        self.assertEqual(aviso["tipo"], "alarma")          # las alarmas siguen pasando
        self.a.confirmar(aviso["id"], "dicho")
        self.assertIsNone(self.a.debido(ahora=self.ahora(13, 1)))

        self.a.reactivar(ahora=self.ahora(13, 2))
        self.assertFalse(self.a.en_silencio(ahora=self.ahora(13, 2)))
        aviso = self.a.debido(ahora=self.ahora(13, 2))
        self.assertEqual(aviso["tipo"], "recordatorio")    # vuelve a avisar
        self.assertTrue(self.a.ajustes()["avisos_activos"])
        with self.assertRaises(ValueError):
            self.a.silenciar(0)

    def test_permisos(self):
        del_padre = self.crear(creado_por="padre")
        del_nino = self.crear(titulo="mi tarea", creado_por="nino")
        with self.assertRaises(PermissionError):
            self.a.borrar_evento(del_padre["id"], autor="nino")
        with self.assertRaises(PermissionError):
            self.a.editar_evento(del_padre["id"], autor="nino", titulo="otra cosa")
        self.assertEqual(self.a.borrar_evento(del_nino["id"], autor="nino"), 1)

    def test_familias_aisladas(self):
        uno = self.crear(familia_id="1")
        dos = self.crear(familia_id="2", titulo="otra familia")
        self.assertIsNone(self.a.obtener_evento(uno["id"], familia_id="2"))
        self.assertEqual([e["id"] for e in self.a.listar_eventos("2")], [dos["id"]])

    def test_editar_reprograma(self):
        evento = self.crear(hora="17:00")
        self.a.materializar(ahora=self.ahora(12, 0), horizonte_horas=8)
        self.assertEqual(len(self.a.listar_avisos()), 1)
        self.a.editar_evento(evento["id"], ahora=self.ahora(12, 0), hora="18:00")
        self.assertEqual(len(self.a.listar_avisos()), 0)          # el aviso viejo se descartó
        self.a.materializar(ahora=self.ahora(12, 0), horizonte_horas=8)
        self.assertEqual(self.a.listar_avisos()[0]["programado"][11:16], "18:00")

    # ---------- Consultas para la voz ----------

    def test_consultas_del_dia(self):
        self.crear(titulo="hacer la tarea", hora="17:00")
        self.crear(titulo="lavarte los dientes", hora="20:30")
        hoy = self.a.describir_dia(ahora=self.ahora(12, 0))
        self.assertIn("Hoy tienes dos cosas", hoy)
        self.assertIn("a las 17:00 hacer la tarea", hoy)
        self.assertIn("a las 20:30 lavarte los dientes", hoy)
        self.assertEqual(self.a.describir_dia(dia="manana", ahora=self.ahora(12, 0)),
                         "Mañana no tienes nada programado.")
        self.assertIn("hoy a las 17:00", self.a.describir_proximos(dias=2, ahora=self.ahora(12, 0)))

    def test_proximo_cumple(self):
        import memoria
        memoria.guardar_perfil("Nico", "2017-03-15", [])
        datos = self.a.proximo_cumple(ahora=self.ahora(12, 0, date(2027, 2, 13)))
        self.assertEqual(datos["dias"], 30)
        self.assertEqual(datos["edad"], 10)
        self.assertIn("Faltan 30 días", self.a.describir_cumple(ahora=self.ahora(12, 0, date(2027, 2, 13))))
        self.assertIn("¡Hoy es tu cumpleaños!", self.a.describir_cumple(ahora=self.ahora(12, 0, date(2027, 3, 15))))

    def test_textos_de_evento(self):
        perfil = {"apodo": "Nico", "nacimiento": "2017-03-15"}
        self.assertEqual(self.a.texto_de_evento({"tipo": "recordatorio", "titulo": "tarea", "texto_voz": ""}),
                         "Recuerda: tarea.")
        self.assertEqual(self.a.texto_de_evento({"tipo": "alarma", "titulo": "despertarse", "texto_voz": ""}),
                         "¡Alarma! despertarse.")
        self.assertEqual(self.a.texto_de_evento({"tipo": "rutina", "titulo": "lavarse los dientes", "texto_voz": ""}),
                         "Es hora de lavarse los dientes.")
        self.assertEqual(self.a.texto_de_evento({"tipo": "temporizador", "titulo": "10 minutos", "texto_voz": ""}),
                         "¡Se acabó el tiempo!")
        texto = self.a.texto_de_evento({"tipo": "cumpleanos", "titulo": "mi cumpleaños", "texto_voz": ""},
                                       cuando=self.ahora(9, 0, date(2027, 3, 15)), perfil=perfil)
        self.assertIn("¡Feliz cumpleaños, Nico!", texto)
        self.assertIn("10 años", texto)
        self.assertEqual(self.a.texto_de_evento({"tipo": "recordatorio", "titulo": "tarea",
                                                 "texto_voz": "Texto propio"}), "Texto propio")

    def test_ajustes(self):
        with self.assertRaises(ValueError):
            self.a.guardar_ajustes(silencio_desde="25:00", silencio_hasta="07:00")
        with self.assertRaises(ValueError):
            self.a.guardar_ajustes(silencio_desde="21:30")
        self.assertFalse(self.a.ajustes()["avisos_activos"])
        self.a.guardar_ajustes(avisos_activos=True, silencio_desde="21:30", silencio_hasta="07:30")
        self.assertTrue(self.a.ajustes()["avisos_activos"])
        self.assertEqual(self.a.ajustes()["silencio_desde"], "21:30")


if __name__ == "__main__":
    unittest.main()
