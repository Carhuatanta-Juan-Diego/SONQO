"""Cámara térmica simulada: temperatura de piel y respiración a 1 Hz, sim: true.

Temperatura 36,6 °C con una caminata aleatoria de ±0,05 °C (que vuelve despacio a
su centro). Respiración igual a la del radar, con ruido. En el desvío simulado la
piel sube 0,2 °C, como en el caso del manual.
"""

import asyncio
import random

from sonqo.demo import RESP_BASE, RESP_DESVIO, TEMP_BASE, TEMP_DESVIO
from sonqo.sources.base import Fuente

CALIDAD = 0.85


class TermicaSim(Fuente):
    nombre = "termica"
    sim = True

    def __init__(self, reloj, emitir, radar, rng=None):
        super().__init__(reloj, emitir)
        self.radar = radar
        self.rng = rng or random.Random()
        self.temp = TEMP_BASE
        self._tarea = None

    def leer(self, t):
        frac = self.radar.fraccion(t)
        centro = TEMP_BASE + TEMP_DESVIO * frac
        self.temp += self.rng.uniform(-0.05, 0.05) + 0.1 * (centro - self.temp)
        resp = RESP_BASE + RESP_DESVIO * frac + self.rng.uniform(-0.8, 0.8)
        return self.temp, resp

    async def _abrir(self):
        self._tarea = asyncio.create_task(self._bucle())

    async def _cerrar(self):
        self._tarea.cancel()

    async def _bucle(self):
        while True:
            t = self.reloj.t()
            temp, resp = self.leer(t)
            self.emitir(self.muestra("temp_piel", temp, CALIDAD, t=t))
            self.emitir(self.muestra("resp", resp, CALIDAD, t=t))
            await asyncio.sleep(1.0)
