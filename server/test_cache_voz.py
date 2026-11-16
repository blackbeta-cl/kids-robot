"""Caché de voz en memoria: aciertos, expulsión y clave. Ejecutar: python -m unittest test_cache_voz -v
La síntesis real se reemplaza por una falsa que cuenta las llamadas (no usa la red)."""
import os, sys, tempfile, types, unittest
os.environ["ROBOT_DATOS"] = tempfile.mkdtemp()
os.environ.setdefault("SERIAL_PORT", "COM99")
os.environ["CACHE_VOZ_PRECALENTAR"] = "0"
sys.modules.setdefault("faster_whisper", types.SimpleNamespace(WhisperModel=object))
import puente


class CacheDeVoz(unittest.TestCase):
    def setUp(self):
        self.llamadas = []
        self.original = puente._sintetizar_pcm
        puente._sintetizar_pcm = lambda texto: (self.llamadas.append(texto) or (b"\x01\x00" * 100, 24000))
        with puente._cache_voz_lock:
            puente._cache_voz.clear(); puente._cache_voz_bytes[0] = 0
        self.max_entradas = puente.CACHE_VOZ_MAX_ENTRADAS
        self.max_bytes = puente.CACHE_VOZ_MAX_BYTES

    def tearDown(self):
        puente._sintetizar_pcm = self.original
        puente.CACHE_VOZ_MAX_ENTRADAS = self.max_entradas
        puente.CACHE_VOZ_MAX_BYTES = self.max_bytes

    def test_la_segunda_vez_no_sintetiza(self):
        a = puente._pcm_de_frase("¡Hola! Me alegra escucharte.")
        b = puente._pcm_de_frase("¡Hola! Me alegra escucharte.")
        self.assertEqual(a, b)
        self.assertEqual(len(self.llamadas), 1)

    def test_frases_distintas_se_sintetizan(self):
        puente._pcm_de_frase("Hola."); puente._pcm_de_frase("Adiós.")
        self.assertEqual(len(self.llamadas), 2)

    def test_vacio_no_llama_al_tts(self):
        self.assertIsNone(puente._pcm_de_frase("   "))
        self.assertEqual(self.llamadas, [])

    def test_la_voz_forma_parte_de_la_clave(self):
        puente._pcm_de_frase("Hola.")
        tono = puente.VOZ_TONO
        try:
            puente.VOZ_TONO = "+0Hz"
            puente._pcm_de_frase("Hola.")
        finally:
            puente.VOZ_TONO = tono
        self.assertEqual(len(self.llamadas), 2)

    def test_expulsa_la_mas_vieja_por_entradas(self):
        puente.CACHE_VOZ_MAX_ENTRADAS = 2
        for f in ("Uno.", "Dos.", "Tres."):
            puente._pcm_de_frase(f)
        self.assertEqual(len(puente._cache_voz), 2)
        puente._pcm_de_frase("Uno.")             # fue expulsada: se vuelve a sintetizar
        self.assertEqual(self.llamadas.count("Uno."), 2)

    def test_lo_usado_se_conserva(self):
        puente.CACHE_VOZ_MAX_ENTRADAS = 2
        puente._pcm_de_frase("Uno."); puente._pcm_de_frase("Dos.")
        puente._pcm_de_frase("Uno.")             # la reutilizo: ahora la vieja es "Dos."
        puente._pcm_de_frase("Tres.")
        puente._pcm_de_frase("Uno.")
        self.assertEqual(self.llamadas.count("Uno."), 1)

    def test_tope_en_bytes(self):
        puente.CACHE_VOZ_MAX_BYTES = 450          # cada frase pesa 200 bytes: caben 2
        for f in ("Uno.", "Dos.", "Tres."):
            puente._pcm_de_frase(f)
        self.assertEqual(len(puente._cache_voz), 2)
        self.assertLessEqual(puente._cache_voz_bytes[0], 450)

    def test_frase_muy_larga_no_se_guarda(self):
        larga = "palabra " * 40
        puente._pcm_de_frase(larga); puente._pcm_de_frase(larga)
        self.assertEqual(len(self.llamadas), 2)
        self.assertEqual(len(puente._cache_voz), 0)

    def test_sin_cache_si_el_maximo_es_cero(self):
        puente.CACHE_VOZ_MAX_ENTRADAS = 0
        puente._pcm_de_frase("Hola."); puente._pcm_de_frase("Hola.")
        self.assertEqual(len(self.llamadas), 2)


if __name__ == "__main__":
    unittest.main()
