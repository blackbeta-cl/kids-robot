"""Voz del robot: síntesis con edge-tts, timbre robótico y reproducción.

Se usa desde puente.py (la voz normal) y desde probar_voces.py (para escuchar
variantes antes de elegir).
"""

import entorno  # noqa: F401  (carga server/.env antes de leer la configuración)
import asyncio
import ctypes
import os

import edge_tts
import numpy as np
import soundfile as sf


def sintetizar(texto, ruta_mp3, voz, tono="+0Hz", ritmo="+0%"):
    """Genera el mp3 con la voz pedida. 'tono' más alto = más infantil."""
    async def _generar():
        await edge_tts.Communicate(texto, voz, pitch=tono, rate=ritmo).save(ruta_mp3)

    asyncio.run(_generar())


def sello_robot(datos, frecuencia, fuerza):
    """Da timbre robótico: modulación metálica y una pizca de cuantización.

    fuerza va de 0 (voz normal) a 1 (robot marcado).
    """
    if fuerza <= 0:
        return datos
    tiempo = np.arange(len(datos)) / frecuencia
    portadora = 0.5 + 0.5 * np.cos(2 * np.pi * 55 * tiempo)    # pulso metálico
    profundidad = min(max(fuerza, 0.0), 1.0) * 0.35
    salida = datos * (1 - profundidad + profundidad * portadora)
    bits = max(4, int(round(12 - 5 * fuerza)))                # de 12 a 7 bits
    paso = 2 ** (bits - 1)
    salida = np.round(salida * paso) / paso
    # El efecto baja el volumen; lo devolvemos al nivel original.
    pico_entrada = float(np.max(np.abs(datos))) or 1.0
    pico_salida = float(np.max(np.abs(salida))) or 1.0
    return salida * (pico_entrada / pico_salida)


def preparar_wav(mp3, wav, fuerza):
    """Decodifica el mp3, le pone el sello de robot y guarda un wav PCM."""
    datos, frecuencia = sf.read(mp3, dtype="float32")
    sf.write(wav, sello_robot(datos, frecuencia, fuerza), frecuencia, subtype="PCM_16")


def reproducir(ruta, tipo="waveaudio"):
    """Reproduce el audio con la API MCI de winmm. Sin dependencias externas."""
    if os.name != "nt":
        print("🔇 Reproducción de audio implementada solo para Windows.")
        return
    winmm = ctypes.windll.winmm
    winmm.mciSendStringW("close tts_robot", None, 0, None)
    error = winmm.mciSendStringW(f'open "{ruta}" type {tipo} alias tts_robot', None, 0, None)
    if error != 0:
        print(f"⚠️ No pude abrir el audio (MCI {error}).")
        return
    try:
        winmm.mciSendStringW("play tts_robot wait", None, 0, None)
    finally:
        winmm.mciSendStringW("close tts_robot", None, 0, None)
