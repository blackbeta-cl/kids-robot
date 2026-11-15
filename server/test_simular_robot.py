"""Pruebas del simulador de robot con un servidor falso (sin red, sin audio).
Ejecutar: python -m unittest test_simular_robot -v
"""
import unittest
from unittest import mock

import simular_robot as sim


class Respuesta:
    def __init__(self, status=200, headers=None, content=b"", cuerpo=None):
        self.status_code = status
        self.headers = headers or {}
        self.content = content
        self._cuerpo = cuerpo

    def raise_for_status(self):
        if self.status_code >= 400:
            raise sim.requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._cuerpo


class Sesion:
    """Guarda las llamadas y devuelve respuestas en orden."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []

    def get(self, url, headers=None, timeout=None):
        self.llamadas.append(("GET", url, headers))
        return self.respuestas.pop(0)

    def post(self, url, json=None, headers=None, timeout=None):
        self.llamadas.append(("POST", url, json, headers))
        return self.respuestas.pop(0)


def aviso(**cambios):
    datos = {"id": "7", "tipo": "recordatorio", "emocion": "neutral", "cuello": "",
             "texto": "Recuerda: tomar agua", "segundos": "2.0", "wav": b"RIFF..."}
    datos.update(cambios)
    return datos


class PedirAviso(unittest.TestCase):
    def test_204_no_hay_nada(self):
        sesion = Sesion(Respuesta(204))
        self.assertIsNone(sim.pedir_aviso("http://127.0.0.1:8000/", "secreto", sesion))
        self.assertEqual(sesion.llamadas, [("GET", "http://127.0.0.1:8000/pendientes",
                                            {"X-Token": "secreto"})])

    def test_sin_token_no_manda_cabecera(self):
        sesion = Sesion(Respuesta(204))
        sim.pedir_aviso("http://127.0.0.1:8000", "", sesion)
        self.assertEqual(sesion.llamadas[0][2], {})

    def test_200_lee_cabeceras_y_decodifica_el_texto(self):
        sesion = Sesion(Respuesta(200, headers={
            "X-Id": "7", "X-Tipo": "alarma", "X-Emocion": "feliz", "X-Cuello": "90",
            "X-Texto": "%C2%A1Alarma%21%20pastilla", "X-Segundos": "3.4",
        }, content=b"RIFF..."))
        aviso = sim.pedir_aviso("http://local", "t", sesion)
        self.assertEqual(aviso["texto"], "¡Alarma! pastilla")
        self.assertEqual((aviso["id"], aviso["tipo"], aviso["emocion"], aviso["cuello"]),
                         ("7", "alarma", "feliz", "90"))
        self.assertEqual(aviso["wav"], b"RIFF...")

    def test_error_http_sube(self):
        with self.assertRaises(sim.requests.HTTPError):
            sim.pedir_aviso("http://local", "", Sesion(Respuesta(503)))

    def test_200_sin_audio_es_error(self):
        with self.assertRaises(ValueError):
            sim.pedir_aviso("http://local", "", Sesion(Respuesta(200, content=b"")))


class Confirmar(unittest.TestCase):
    def test_manda_json_y_token(self):
        sesion = Sesion(Respuesta(200, content=b'{"status":"ok"}', cuerpo={"status": "ok"}))
        self.assertEqual(sim.confirmar("http://local/", "7", "t", sesion=sesion), {"status": "ok"})
        self.assertEqual(sesion.llamadas, [
            ("POST", "http://local/pendientes/7/hecho",
             {"resultado": "dicho", "motivo": ""}, {"X-Token": "t"})])

    def test_motivo_de_omision(self):
        sesion = Sesion(Respuesta(200, content=b"{}", cuerpo={}))
        sim.confirmar("http://local", "9", "", "omitido", "no estaba", sesion)
        self.assertEqual(sesion.llamadas[0][2],
                         {"resultado": "omitido", "motivo": "no estaba"})


class ManejarAviso(unittest.TestCase):
    def setUp(self):
        self.salida = []
        self.sesion = Sesion()
        self.confirmaciones = []

        def falso_confirmar(url, ident, token="", resultado="dicho", motivo="", sesion=None):
            self.confirmaciones.append((ident, resultado, motivo))
            return {}

        self._confirmar = sim.confirmar
        sim.confirmar = falso_confirmar

    def tearDown(self):
        sim.confirmar = self._confirmar

    def test_primera_vez_reproduce_y_confirma(self):
        ya = set()
        with mock.patch.object(sim, "reproducir_aviso", return_value="aviso_7.wav") as reproducir:
            self.assertTrue(sim.manejar_aviso("http://local", "", aviso(), ya,
                                              guardar="x", salida=self.salida.append))
        reproducir.assert_called_once()
        self.assertEqual(self.confirmaciones, [("7", "dicho", "")])
        self.assertIn("7", ya)
        self.assertIn("📣 aviso 7: «Recuerda: tomar agua»", self.salida[0])
        self.assertTrue(any("✅" in linea for linea in self.salida))

    def test_sin_sonido_no_reproduce_pero_confirma(self):
        with mock.patch.object(sim, "reproducir_aviso") as reproducir:
            sim.manejar_aviso("http://local", "", aviso(), set(), sonido=False,
                              salida=self.salida.append)
        reproducir.assert_not_called()
        self.assertEqual(self.confirmaciones, [("7", "dicho", "")])

    def test_repetido_no_vuelve_a_sonar(self):
        ya = {"7"}
        with mock.patch.object(sim, "reproducir_aviso") as reproducir:
            sim.manejar_aviso("http://local", "", aviso(), ya, salida=self.salida.append)
        reproducir.assert_not_called()
        self.assertEqual(self.confirmaciones, [("7", "dicho", "")])
        self.assertIn("repetido", self.salida[0])

    def test_si_falla_la_reproduccion_lo_marca_omitido(self):
        ya = set()
        with mock.patch.object(sim, "reproducir_aviso", side_effect=RuntimeError("sin audio")):
            self.assertTrue(sim.manejar_aviso("http://local", "", aviso(), ya,
                                              salida=self.salida.append))
        self.assertEqual(self.confirmaciones, [("7", "omitido", "no se pudo reproducir")])
        self.assertNotIn("7", ya)

    def test_sin_id_no_confirma(self):
        with mock.patch.object(sim, "reproducir_aviso") as reproducir:
            self.assertFalse(sim.manejar_aviso("http://local", "", aviso(id=""), set(),
                                               salida=self.salida.append))
        reproducir.assert_not_called()
        self.assertEqual(self.confirmaciones, [])

    def test_si_falla_la_confirmacion_se_reintenta(self):
        ya = set()
        sim.confirmar = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sin red"))
        with mock.patch.object(sim, "reproducir_aviso", return_value="x.wav"):
            self.assertFalse(sim.manejar_aviso("http://local", "", aviso(), ya,
                                               salida=self.salida.append))
        self.assertNotIn("7", ya)


class Bucle(unittest.TestCase):
    def test_sondea_y_confirma(self):
        salida = []
        pendientes = [aviso(), None]
        with mock.patch.object(sim, "pedir_aviso",
                               side_effect=lambda *a, **k: pendientes.pop(0)), \
             mock.patch.object(sim, "reproducir_aviso", return_value="x.wav"), \
             mock.patch.object(sim, "confirmar", return_value={}) as confirmar, \
             mock.patch.object(sim.time, "sleep") as dormir:
            sim.bucle("http://local", "t", intervalo=20, veces=2, salida=salida.append)
        self.assertEqual(confirmar.call_count, 1)
        self.assertIn("· sin avisos", salida)
        dormir.assert_called_once_with(20)

    def test_veces_termina_y_no_duerme_al_final(self):
        salida = []
        with mock.patch.object(sim, "pedir_aviso", return_value=None), \
             mock.patch.object(sim.time, "sleep") as dormir:
            sim.bucle("http://local", veces=3, salida=salida.append)
        self.assertEqual(len(salida), 3)
        self.assertEqual(dormir.call_count, 2)


if __name__ == "__main__":
    unittest.main()
