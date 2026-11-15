"""Pruebas de intenciones_agenda.py (sin placa ni red). Ejecutar: python -m unittest test_intenciones_agenda -v"""
import importlib
import os
import tempfile
import unittest
from datetime import date, datetime, time, timedelta


class Intenciones(unittest.TestCase):
    def setUp(self):
        os.environ["ROBOT_DATOS"] = tempfile.mkdtemp()
        import persona
        importlib.reload(persona)
        import memoria
        importlib.reload(memoria)
        import agenda
        importlib.reload(agenda)
        import intenciones_agenda
        self.ia = importlib.reload(intenciones_agenda)
        self.p = persona
        self.m = memoria
        self.a = agenda
        self.ia.limpiar()
        self.zona = persona.zona_robot()
        self.hoy = persona.ahora_robot().date()
        self.ahora = datetime.combine(self.hoy, time(12, 0), tzinfo=self.zona)

    def decir(self, texto, ahora=None, autor="nino", familia_id="1", clave="test"):
        return self.ia.procesar(texto, familia_id=familia_id, autor=autor,
                                ahora=ahora or self.ahora, clave=clave)

    def eventos(self):
        return self.a.listar_eventos()

    def crear(self, titulo="hacer la tarea", tipo="recordatorio", hora="17:00", fecha=None,
              creado_por="nino", dias=None, familia_id="1"):
        return self.a.crear_evento(tipo, titulo, hora=hora,
                                   fecha=fecha if fecha is not None else self.hoy.isoformat(),
                                   dias=dias, creado_por=creado_por, familia_id=familia_id)

    # ---------- Crear recordatorios ----------

    def test_titulo_antes_y_despues_de_la_hora(self):
        uno = self.decir("recuérdame hacer la tarea a las 5")
        dos = self.decir("a las 5 recuérdame lavarme los dientes")
        self.assertIn("hacer la tarea", uno["respuesta"])
        self.assertIn("17:00", uno["respuesta"])
        self.assertIn("lavarme los dientes", dos["respuesta"])
        eventos = self.eventos()
        self.assertEqual(len(eventos), 2)
        self.assertEqual({e["hora"] for e in eventos}, {"17:00"})
        self.assertTrue(all(e["creado_por"] == "nino" for e in eventos))

    def test_manana_y_de_la_mochila(self):
        r = self.decir("avísame mañana a las 8 de la mochila")
        self.assertIn("mañana a las 08:00", r["respuesta"])
        self.assertIn("la mochila", r["respuesta"])
        evento = self.eventos()[0]
        self.assertEqual(evento["fecha"], (self.hoy + timedelta(days=1)).isoformat())
        self.assertEqual(evento["hora"], "08:00")

    def test_que_haga(self):
        r = self.decir("recuérdame que haga la tarea a las 5")
        self.assertIn("haga la tarea", r["respuesta"])

    def test_variantes_de_whisper(self):
        self.decir("recuérdeme a las 5 hacer la tarea")
        self.decir("avíseme a las 5 lavarme los dientes")
        self.decir("acuérdate de a las 5 ordenar la pieza")
        self.assertEqual(len(self.eventos()), 3)

    def test_variantes_de_whisper_dos(self):
        self.decir("apúntame a las 5 hacer la tarea")
        self.decir("anótame a las 5 lavarme los dientes")
        self.assertEqual(len(self.eventos()), 2)

    # ---------- 12 horas y horas pasadas ----------

    def test_doce_horas_ambiguo(self):
        r = self.decir("recuérdame a las 5 tomar agua")
        self.assertEqual(self.eventos()[0]["hora"], "17:00")
        self.assertIn("17:00", r["respuesta"])

    def test_de_la_manana(self):
        r = self.decir("recuérdame a las 5 de la mañana tomar agua")
        evento = self.eventos()[0]
        self.assertEqual(evento["hora"], "05:00")
        self.assertEqual(evento["fecha"], (self.hoy + timedelta(days=1)).isoformat())
        self.assertTrue(r["respuesta"].startswith("Ya pasaron las 05:00"))

    def test_ocho_de_la_manana_tambien_rueda(self):
        r = self.decir("recuérdame a las 8 de la mañana desayunar")
        self.assertEqual(self.eventos()[0]["hora"], "08:00")
        self.assertTrue(r["respuesta"].startswith("Ya pasaron las 08:00"))

    def test_hora_pasada_pasa_a_manana(self):
        tarde = datetime.combine(self.hoy, time(18, 0), tzinfo=self.zona)
        r = self.decir("recuérdame a las 5 hacer la tarea", ahora=tarde)
        self.assertTrue(r["respuesta"].startswith("Ya pasaron las 17:00"))
        self.assertEqual(self.eventos()[0]["fecha"], (self.hoy + timedelta(days=1)).isoformat())

    def test_hora_con_minutos(self):
        self.decir("recuérdame a las 17:30 hacer la tarea")
        self.assertEqual(self.eventos()[0]["hora"], "17:30")

    def test_mediodia(self):
        once = datetime.combine(self.hoy, time(11, 0), tzinfo=self.zona)
        self.decir("recuérdame al mediodía comer", ahora=once)
        self.assertEqual(self.eventos()[0]["hora"], "12:00")
        self.assertEqual(self.eventos()[0]["fecha"], self.hoy.isoformat())

    # ---------- Alarma y temporizador ----------

    def test_alarma(self):
        r = self.decir("ponme una alarma a las 7")
        evento = self.eventos()[0]
        self.assertEqual(evento["tipo"], "alarma")
        self.assertEqual(evento["titulo"], "despertarse")
        self.assertEqual(evento["hora"], "19:00")
        self.assertIn("alarma", r["respuesta"])

    def test_alarma_con_titulo(self):
        self.decir("ponme una alarma a las 7 para despertarme")
        self.assertEqual(self.eventos()[0]["titulo"], "despertarme")

    def test_alarma_pide_hora(self):
        r = self.decir("ponme una alarma")
        self.assertEqual(r["respuesta"], "¿A qué hora pongo la alarma?")
        r = self.decir("a las 7 de la mañana")
        self.assertEqual(self.eventos()[0]["hora"], "07:00")
        self.assertIn("alarma", r["respuesta"])

    def test_temporizador_minutos(self):
        r = self.decir("pon 10 minutos")
        evento = self.eventos()[0]
        self.assertEqual(evento["tipo"], "temporizador")
        self.assertEqual(evento["hora"], "12:10")
        self.assertIn("10 minutos", r["respuesta"])

    def test_temporizador_media_hora(self):
        self.decir("avísame en media hora")
        self.assertEqual(self.eventos()[0]["hora"], "12:30")

    def test_temporizador_hora_y_media(self):
        self.decir("pon un temporizador de hora y media")
        self.assertEqual(self.eventos()[0]["hora"], "13:30")

    def test_temporizador_pide_minutos(self):
        r = self.decir("pon un temporizador")
        self.assertIn("Cuántos minutos", r["respuesta"])
        self.decir("10")
        self.assertEqual(self.eventos()[0]["hora"], "12:10")

    def test_relativo_con_titulo(self):
        r = self.decir("recuérdame en 10 minutos sacar la basura")
        evento = self.eventos()[0]
        self.assertEqual(evento["tipo"], "recordatorio")
        self.assertEqual(evento["hora"], "12:10")
        self.assertEqual(evento["titulo"], "sacar la basura")
        self.assertIn("sacar la basura", r["respuesta"])

    # ---------- Pendientes ----------

    def test_pide_hora(self):
        r = self.decir("recuérdame hacer la tarea")
        self.assertEqual(r["respuesta"], "¿A qué hora te lo recuerdo?")
        r = self.decir("a las 5")
        self.assertIn("17:00", r["respuesta"])
        self.assertEqual(self.eventos()[0]["titulo"], "hacer la tarea")

    def test_pide_titulo(self):
        r = self.decir("recuérdame a las 5")
        self.assertEqual(r["respuesta"], "¿Qué te recuerdo?")
        r = self.decir("hacer la tarea")
        self.assertIn("hacer la tarea", r["respuesta"])
        self.assertEqual(len(self.eventos()), 1)

    def test_titulo_y_hora_en_la_misma_respuesta(self):
        self.decir("recuérdame")
        r = self.decir("lavarme los dientes a las 5")
        self.assertIn("17:00", r["respuesta"])
        self.assertEqual(self.eventos()[0]["titulo"], "lavarme los dientes")

    def test_pendiente_expira(self):
        self.decir("recuérdame a las 5")
        despues = self.ahora + timedelta(seconds=61)
        self.assertIsNone(self.decir("hacer la tarea", ahora=despues))
        self.assertEqual(self.eventos(), [])

    def test_pendiente_olvidar(self):
        self.decir("recuérdame a las 5")
        self.assertEqual(self.decir("olvídalo")["respuesta"], "Listo, lo olvido.")
        self.assertEqual(self.eventos(), [])

    # ---------- Repetición y fechas ----------

    def test_todos_los_dias(self):
        self.decir("todos los días a las 7 recuérdame lavarme los dientes")
        evento = self.eventos()[0]
        self.assertEqual(evento["dias"], [0, 1, 2, 3, 4, 5, 6])
        self.assertEqual(evento["fecha"], "")
        self.assertEqual(evento["hora"], "19:00")

    def test_lunes_a_viernes(self):
        self.decir("de lunes a viernes a las 7 recuérdame ir al colegio")
        self.assertEqual(self.eventos()[0]["dias"], [0, 1, 2, 3, 4])

    def test_martes_y_jueves(self):
        self.decir("los martes y jueves a las 18:30 recuérdame fútbol")
        evento = self.eventos()[0]
        self.assertEqual(evento["dias"], [1, 3])
        self.assertEqual(evento["titulo"], "fútbol")

    def test_el_lunes(self):
        self.decir("recuérdame el lunes a las 5 hacer la tarea")
        evento = self.eventos()[0]
        fecha = date.fromisoformat(evento["fecha"])
        self.assertEqual(fecha.weekday(), 0)
        self.assertGreaterEqual(fecha, self.hoy)

    def test_fecha_de_diciembre(self):
        self.decir("recuérdame el 15 de diciembre a las 17:00 comprar regalos")
        evento = self.eventos()[0]
        fecha = date.fromisoformat(evento["fecha"])
        self.assertEqual((fecha.month, fecha.day), (12, 15))
        self.assertGreaterEqual(fecha, self.hoy)

    def test_fecha_corta(self):
        self.decir("recuérdame el 15/12 a las 17:00 comprar regalos")
        fecha = date.fromisoformat(self.eventos()[0]["fecha"])
        self.assertEqual((fecha.month, fecha.day), (12, 15))

    # ---------- Consultas ----------

    def test_consultar_hoy(self):
        self.crear(titulo="hacer la tarea", hora="17:00")
        self.crear(titulo="lavarte los dientes", hora="20:30")
        r = self.decir("¿qué tengo hoy?")
        self.assertIn("Hoy tienes dos cosas", r["respuesta"])
        self.assertIn("a las 17:00 hacer la tarea", r["respuesta"])
        self.assertIn("a las 20:30 lavarte los dientes", r["respuesta"])

    def test_consultar_manana(self):
        self.crear(titulo="llevar la mochila", hora="08:00",
                   fecha=(self.hoy + timedelta(days=1)).isoformat())
        r = self.decir("¿qué tengo mañana?")
        self.assertIn("Mañana tienes una cosa", r["respuesta"])
        self.assertIn("a las 08:00 llevar la mochila", r["respuesta"])

    def test_consultar_semana(self):
        self.crear(titulo="hacer la tarea", hora="17:00")
        r = self.decir("¿qué tengo esta semana?")
        self.assertIn("Tienes:", r["respuesta"])
        self.assertIn("hacer la tarea", r["respuesta"])

    def test_consultar_vacio(self):
        r = self.decir("¿qué tengo hoy?")
        self.assertIn("Todavía no sé nada de tu agenda", r["respuesta"])

    def test_a_que_hora_es(self):
        self.crear(titulo="hacer la tarea", hora="17:00")
        r = self.decir("¿a qué hora es la tarea?")
        self.assertIn("Hoy a las 17:00", r["respuesta"])
        self.assertIn("hacer la tarea", r["respuesta"])

    def test_a_que_hora_es_mi_alarma(self):
        self.crear(tipo="alarma", titulo="despertarse", hora="19:00")
        r = self.decir("¿a qué hora es mi alarma?")
        self.assertIn("Hoy a las 19:00", r["respuesta"])

    def test_consultar_evento_inexistente(self):
        r = self.decir("¿a qué hora es la tarea?")
        self.assertIn("No encuentro eso", r["respuesta"])

    def test_hora_y_fecha(self):
        self.assertEqual(self.decir("¿qué hora es?")["respuesta"], "Son las 12:00.")
        fecha = self.decir("¿qué día es hoy?")["respuesta"]
        self.assertIn(self.a.fecha_larga(self.hoy), fecha)
        self.assertIn(str(self.hoy.year), fecha)

    def test_cumple(self):
        self.m.guardar_perfil("Nico", "2017-03-15", [])
        enero = datetime.combine(date(2027, 2, 13), time(12, 0), tzinfo=self.zona)
        r = self.decir("¿cuánto falta para mi cumpleaños?", ahora=enero)
        self.assertIn("Faltan 30 días", r["respuesta"])
        self.assertIn("10 años", r["respuesta"])

    # ---------- Silencio ----------

    def test_silencio_y_reactivar(self):
        r = self.decir("cállate por 15 minutos")
        self.assertIn("15 minutos", r["respuesta"])
        self.assertTrue(self.a.en_silencio(ahora=self.ahora + timedelta(minutes=5)))
        self.assertFalse(self.a.en_silencio(ahora=self.ahora + timedelta(minutes=20)))
        self.decir("vuelve a hablar")
        self.assertFalse(self.a.en_silencio(ahora=self.ahora + timedelta(minutes=5)))
        self.assertEqual(self.a.ajustes()["silencio_temporal_hasta"], "")

    def test_silencio_por_defecto(self):
        r = self.decir("cállate")
        self.assertIn("30 minutos", r["respuesta"])

    def test_no_me_molestes(self):
        r = self.decir("no me molestes por 10 minutos")
        self.assertIn("10 minutos", r["respuesta"])

    # ---------- Cancelar ----------

    def test_cancelar_por_titulo(self):
        self.decir("recuérdame a las 5 hacer la tarea")
        r = self.decir("cancela el recordatorio de la tarea")
        self.assertIn("borré", r["respuesta"])
        self.assertEqual(self.eventos(), [])

    def test_cancelar_lo_del_padre(self):
        self.crear(titulo="hacer la tarea", creado_por="padre")
        r = self.decir("cancela el recordatorio de la tarea")
        self.assertIn("mamá o papá", r["respuesta"])
        self.assertEqual(len(self.eventos()), 1)

    def test_cancelar_ambiguo(self):
        self.crear(tipo="alarma", titulo="despertarse", hora="18:00")
        self.crear(tipo="alarma", titulo="pastilla", hora="19:00")
        r = self.decir("cancela mi alarma")
        self.assertIn("Tienes varios", r["respuesta"])
        r = self.decir("la de las 7")
        self.assertIn("borré", r["respuesta"])
        self.assertEqual([e["hora"] for e in self.eventos()], ["18:00"])

    def test_cancelar_temporizador(self):
        self.decir("pon 10 minutos")
        r = self.decir("cancela el temporizador")
        self.assertIn("borré", r["respuesta"])
        self.assertEqual(self.eventos(), [])

    def test_cancelar_sin_evento(self):
        r = self.decir("cancela mi alarma")
        self.assertIn("No encuentro esa alarma", r["respuesta"])

    # ---------- Otras respuestas locales ----------

    def test_rutina_hecha(self):
        self.assertEqual(self.decir("ya terminé la tarea")["respuesta"], "¡Bien hecho!")

    def test_ayuda(self):
        r = self.decir("¿qué sabes hacer?")
        self.assertIn("alarmas", r["respuesta"])

    def test_limite_de_creaciones(self):
        for hora in ("5", "6", "7"):
            self.decir(f"recuérdame a las {hora} hacer la tarea")
        r = self.decir("recuérdame a las 8 lavarme los dientes")
        self.assertIn("Espera un poquito", r["respuesta"])
        self.assertEqual(len(self.eventos()), 3)

    def test_familias_aisladas(self):
        self.decir("recuérdame a las 5 hacer la tarea", familia_id="1")
        r = self.decir("¿qué tengo hoy?", familia_id="2")
        self.assertIn("Todavía no sé nada", r["respuesta"])

    def test_frases_que_no_son_de_agenda(self):
        for frase in ("me gustan los dinosaurios", "quiero jugar Minecraft",
                      "ponte feliz", "recuerda que mañana hay colegio",
                      "borra la pizarra", "borra la memoria"):
            self.assertIsNone(self.decir(frase), frase)
        self.assertEqual(self.eventos(), [])


if __name__ == "__main__":
    unittest.main()
