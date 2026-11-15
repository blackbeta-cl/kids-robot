"""Pruebas de GET /pendientes y POST /pendientes/<id>/hecho (sin placa ni red).

Se llaman las funciones del puente directamente (como test_puente_memoria): el entorno no
tiene httpx para TestClient. La voz se reemplaza por un WAV falso y el reloj de la agenda
se fija a las 12:00 para que las pruebas no dependan de la hora de ejecución.

Ejecutar: python -m unittest test_pendientes -v
"""
import asyncio
import importlib
import io
import os
import tempfile
import time
import unittest
import wave
from datetime import datetime

os.environ["SERIAL_PORT"] = "COM99"
os.environ["ROBOT_DATOS"] = tempfile.mkdtemp()
os.environ["LLM_API_KEY"] = "clave-falsa"
os.environ["LLM_URL"] = "http://127.0.0.1:9/prueba"      # nada real: las pruebas no llaman a ningún modelo
os.environ["LLM_MODEL"] = "modelo-falso"
os.environ["EXTRAER_AUTOMATICO"] = "0"
os.environ["PANEL_PADRES"] = "0"

import puente
from starlette.requests import Request


def wav_de(segundos=2.0, frecuencia=16000):
    """WAV PCM 16 bits mono con silencio; solo importa su duración y que sea válido."""
    salida = io.BytesIO()
    with wave.open(salida, "wb") as archivo:
        archivo.setnchannels(1)
        archivo.setsampwidth(2)
        archivo.setframerate(frecuencia)
        archivo.writeframes(b"\x00\x00" * int(segundos * frecuencia))
    return salida.getvalue()


def peticion(ruta="/pendientes", host="203.0.113.5", cabeceras=None):
    from starlette.requests import Request
    scope = {
        "type": "http",
        "method": "GET",
        "path": ruta,
        "scheme": "http",
        "query_string": b"",
        "headers": [(k.lower().encode("latin-1"), v.encode("latin-1"))
                    for k, v in (cabeceras or {}).items()],
        "client": (host, 12345),
    }
    return Request(scope)


async def _responder_ok(request):
    from fastapi.responses import JSONResponse
    return JSONResponse({"ok": True})


class Pendientes(unittest.TestCase):
    def setUp(self):
        os.environ["ROBOT_DATOS"] = tempfile.mkdtemp()
        import persona
        importlib.reload(persona)
        import memoria
        importlib.reload(memoria)
        import agenda
        importlib.reload(agenda)
        import intenciones_agenda
        importlib.reload(intenciones_agenda)
        self.p, self.m, self.a = persona, memoria, agenda
        self.ia = intenciones_agenda
        self.ia.limpiar()

        puente.agenda = agenda
        puente.intenciones_agenda = intenciones_agenda
        puente.FAMILIA_ID = "1"
        puente.TOKEN_ROBOT = "secreto"

        # Reloj fijo de la agenda: así "hoy a las 12:00" siempre está vencido y es determinista.
        self.zona = persona.zona_robot()
        self.hoy = persona.ahora_robot().date()
        self.ahora = datetime(self.hoy.year, self.hoy.month, self.hoy.day, 12, 0, tzinfo=self.zona)
        self._local_original = agenda._local
        agenda._local = lambda ahora=None: (self.ahora if ahora is None
                                           else self._local_original(ahora))
        self._ia_local_original = intenciones_agenda._local
        intenciones_agenda._local = lambda ahora=None: (self.ahora if ahora is None
                                                        else self._ia_local_original(ahora))

        self.wav = wav_de(2.0)
        self._wav_original = puente._wav_de_frase
        puente._wav_de_frase = lambda frase: self.wav

    def tearDown(self):
        puente._wav_de_frase = self._wav_original
        self.a._local = self._local_original
        self.ia._local = self._ia_local_original
        self.ia.limpiar()

    # ---------- Ayudas ----------

    def crear(self, titulo="tomar agua", tipo="recordatorio", hora="12:00",
              creado_por="padre", familia_id="1"):
        return self.a.crear_evento(tipo, titulo, hora=hora, fecha=self.hoy.isoformat(),
                                   creado_por=creado_por, familia_id=familia_id)

    def encender(self, **cambios):
        datos = {"avisos_activos": True}
        datos.update(cambios)
        return self.a.guardar_ajustes(ahora=self.ahora, **datos)

    # ---------- GET /pendientes ----------

    def test_sin_nada_responde_204(self):
        respuesta = puente.pendientes()
        self.assertEqual(respuesta.status_code, 204)
        self.assertEqual(respuesta.body, b"")

    def test_avisos_apagados_no_entrega(self):
        self.crear()
        self.assertEqual(puente.pendientes().status_code, 204)

    def test_entrega_con_cabeceras_y_audio(self):
        self.encender()
        self.crear(titulo="tomar agua")
        respuesta = puente.pendientes()
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.media_type, "audio/wav")
        self.assertEqual(respuesta.body, self.wav)
        self.assertEqual(respuesta.headers["x-tipo"], "recordatorio")
        self.assertEqual(respuesta.headers["x-emocion"], "neutral")
        self.assertEqual(respuesta.headers["x-segundos"], "2.0")
        self.assertIn("tomar%20agua", respuesta.headers["x-texto"])
        self.assertTrue(respuesta.headers["x-id"].isdigit())
        self.assertNotIn("x-cuello", respuesta.headers)
        self.assertEqual(self.a.listar_avisos()[0]["estado"], "pendiente")

    def test_un_aviso_por_minuto(self):
        self.encender()
        self.crear("tomar agua")
        self.crear("ordenar la pieza", hora="12:01")
        self.assertEqual(puente.pendientes().status_code, 200)
        self.assertEqual(puente.pendientes().status_code, 204)   # el siguiente espera al minuto

    def test_prueba_funciona_con_avisos_apagados(self):
        evento = self.crear()
        aviso = self.a.probar_evento(evento["id"], ahora=self.ahora)
        respuesta = puente.pendientes()
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.headers["x-id"], str(aviso))
        self.assertEqual(respuesta.headers["x-tipo"], "recordatorio")

    def test_cumpleanos_es_feliz(self):
        self.encender()
        self.m.guardar_perfil("Nico", self.hoy.replace(year=self.hoy.year - 9).isoformat(), [])
        self.ahora = self.ahora.replace(hour=9)      # el cumpleaños es a las 09:00
        self.a.asegurar_cumpleanos(ahora=self.ahora)
        respuesta = puente.pendientes()
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.headers["x-tipo"], "cumpleanos")
        self.assertEqual(respuesta.headers["x-emocion"], "feliz")

    def test_silencio_temporal_omite_recordatorio_pero_no_alarma(self):
        self.encender()
        self.crear("tomar agua", tipo="recordatorio")
        self.a.silenciar(30, ahora=self.ahora)
        self.assertEqual(puente.pendientes().status_code, 204)   # «cállate»: recordatorio callado
        self.crear("pastilla", tipo="alarma", hora="12:00")
        respuesta = puente.pendientes()
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.headers["x-tipo"], "alarma")   # las alarmas siguen pasando

    def test_texto_vacio_se_omite(self):
        self.encender()
        self.crear()
        puente._wav_de_frase = lambda frase: None
        self.assertEqual(puente.pendientes().status_code, 204)
        self.assertEqual(self.a.listar_avisos()[0]["estado"], "omitido")

    def test_fallo_de_voz_deja_el_aviso_pendiente(self):
        self.encender()
        self.crear()

        def romper(frase):
            raise RuntimeError("sin internet")

        puente._wav_de_frase = romper
        with self.assertRaises(puente.HTTPException) as error:
            puente.pendientes()
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(self.a.listar_avisos()[0]["estado"], "pendiente")

    # ---------- POST /pendientes/<id>/hecho ----------

    def test_confirmar_dicho(self):
        self.encender()
        self.crear()
        aviso = int(puente.pendientes().headers["x-id"])
        respuesta = puente.confirmar_aviso(aviso, puente.ConfirmacionAviso(resultado="dicho"))
        self.assertEqual(respuesta["estado"], "dicho")
        self.assertEqual(self.a.listar_avisos()[0]["estado"], "dicho")
        self.assertEqual(puente.pendientes().status_code, 204)

    def test_confirmar_es_idempotente(self):
        self.encender()
        self.crear()
        aviso = int(puente.pendientes().headers["x-id"])
        puente.confirmar_aviso(aviso, puente.ConfirmacionAviso(resultado="dicho"))
        otra = puente.confirmar_aviso(aviso, puente.ConfirmacionAviso(resultado="omitido"))
        self.assertEqual(otra["estado"], "dicho")       # repetir no cambia nada

    def test_omitido_queda_omitido(self):
        self.encender()
        self.crear()
        aviso = int(puente.pendientes().headers["x-id"])
        respuesta = puente.confirmar_aviso(
            aviso, puente.ConfirmacionAviso(resultado="omitido", motivo="no estaba"))
        self.assertEqual(respuesta["estado"], "omitido")
        self.assertEqual(self.a.listar_avisos()[0]["motivo"], "no estaba")

    def test_resultado_invalido_400(self):
        aviso = self.a.probar_evento(self.crear()["id"], ahora=self.ahora)
        with self.assertRaises(puente.HTTPException) as error:
            puente.confirmar_aviso(aviso, puente.ConfirmacionAviso(resultado="hecho"))
        self.assertEqual(error.exception.status_code, 400)

    def test_aviso_inexistente_404(self):
        with self.assertRaises(puente.HTTPException) as error:
            puente.confirmar_aviso(999999, puente.ConfirmacionAviso())
        self.assertEqual(error.exception.status_code, 404)

    def test_aviso_de_otra_familia_404(self):
        evento = self.crear(familia_id="2")
        aviso = self.a.probar_evento(evento["id"], familia_id="2", ahora=self.ahora)
        with self.assertRaises(puente.HTTPException) as error:
            puente.confirmar_aviso(aviso, puente.ConfirmacionAviso())
        self.assertEqual(error.exception.status_code, 404)

    # ---------- Token (middleware de /voz) ----------

    def test_token_obligatorio_desde_la_red(self):
        respuesta = asyncio.run(puente.exigir_token_desde_la_red(
            peticion(host="203.0.113.5"), _responder_ok))
        self.assertEqual(respuesta.status_code, 401)

        respuesta = asyncio.run(puente.exigir_token_desde_la_red(
            peticion(host="203.0.113.5", cabeceras={"X-Token": "otro"}), _responder_ok))
        self.assertEqual(respuesta.status_code, 401)

        respuesta = asyncio.run(puente.exigir_token_desde_la_red(
            peticion(host="203.0.113.5", cabeceras={"X-Token": "secreto"}), _responder_ok))
        self.assertEqual(respuesta.status_code, 200)

    def test_red_local_sin_token(self):
        respuesta = asyncio.run(puente.exigir_token_desde_la_red(
            peticion(host="127.0.0.1"), _responder_ok))
        self.assertEqual(respuesta.status_code, 200)

    def test_sin_token_configurado_la_red_queda_cerrada(self):
        puente.TOKEN_ROBOT = ""
        try:
            respuesta = asyncio.run(puente.exigir_token_desde_la_red(
                peticion(host="203.0.113.5"), _responder_ok))
            self.assertEqual(respuesta.status_code, 403)
        finally:
            puente.TOKEN_ROBOT = "secreto"

    # ---------- Precedencia en _plan_de_respuesta ----------

    def test_agenda_antes_que_cara_y_modelo(self):
        frase, emocion, cuello, nota = puente._plan_de_respuesta("recuérdame a las 5 hacer la tarea")
        self.assertIn("hacer la tarea", frase)
        self.assertIn("17:00", frase)
        self.assertEqual(emocion, "feliz")
        self.assertIsNone(cuello)
        self.assertEqual(nota, "")
        self.assertEqual(len(self.a.listar_eventos()), 1)

    def test_pendiente_por_voz_entre_turnos(self):
        frase, *_ = puente._plan_de_respuesta("recuérdame a las 5")
        self.assertEqual(frase, "¿Qué te recuerdo?")
        frase, *_ = puente._plan_de_respuesta("lavarme los dientes")
        self.assertIn("lavarme los dientes", frase)
        self.assertEqual(self.a.listar_eventos()[0]["titulo"], "lavarme los dientes")

    def test_consulta_local_no_llama_al_modelo(self):
        self.crear("hacer la tarea", hora="17:00")
        frase, emocion, cuello, nota = puente._plan_de_respuesta("¿qué tengo hoy?")
        self.assertIn("hacer la tarea", frase)
        self.assertEqual((emocion, cuello, nota), ("neutral", None, ""))

    def test_orden_de_cara_no_la_toca_la_agenda(self):
        frase, *_ = puente._plan_de_respuesta("mueve la cabeza")
        self.assertEqual(frase, "¡Listo, moví la cabeza!")

    def test_frase_normal_sigue_al_modelo(self):
        frase, emocion, cuello, nota = puente._plan_de_respuesta("¿por qué el cielo es azul?")
        self.assertIsNone(frase)
        self.assertEqual(nota, "")

    def test_agenda_rota_no_rompe_la_voz(self):
        original = puente.intenciones_agenda.procesar
        puente.intenciones_agenda.procesar = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db rota"))
        try:
            frase, *_ = puente._plan_de_respuesta("mueve la cabeza")
            self.assertEqual(frase, "¡Listo, moví la cabeza!")
        finally:
            puente.intenciones_agenda.procesar = original


if __name__ == "__main__":
    unittest.main()
