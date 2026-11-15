"""Radar 60 GHz simulado: pulso y respiración a 1 Hz, siempre con sim: true.

Modos:
- normal: sigue el último valor del oxímetro (o la referencia; 68 lpm si no hay), ruido ±1,5 lpm.
- desvio: sube a 141 lpm en 30 s (el caso simulado). Al volver a normal, baja en 30 s.
- falla:  marca 141 lpm de golpe, mientras la cámara sigue normal (los sensores no coinciden).
"""

import asyncio
import random

from sonqo.demo import PULSO_ALTO, RAMPA_S, RESP_BASE, RESP_DESVIO
from sonqo.sources.base import Fuente

MODOS = ["normal", "desvio", "falla"]
RUIDO_LPM = 1.5
CALIDAD = 0.9


def pulso_objetivo(modo, base, frac):
    if modo == "falla":
        return PULSO_ALTO
    return base + (PULSO_ALTO - base) * frac


class RadarSim(Fuente):
    nombre = "radar"
    sim = True

    def __init__(self, reloj, emitir, modo="normal", referencia=lambda: 68.0, rng=None):
        super().__init__(reloj, emitir)
        self.referencia = referencia
        self.rng = rng or random.Random()
        self.modo = modo
        self._t_cambio = 0.0
        self._frac_desde = 0.0
        self._tarea = None
        self.ultimo_pulso = None

    def fraccion(self, t):
        """Avance del desvío (0 a 1), con rampas de 30 s al subir y al bajar."""
        avance = min(1.0, (t - self._t_cambio) / RAMPA_S)
        if self.modo == "desvio":
            return self._frac_desde + (1.0 - self._frac_desde) * avance
        if self.modo == "normal":
            return self._frac_desde * (1.0 - avance)
        return 0.0

    def set_modo(self, modo, t):
        if modo not in MODOS:
            raise ValueError(modo)
        self._frac_desde = self.fraccion(t) if self.modo != "falla" else 0.0
        self.modo, self._t_cambio = modo, t

    def leer(self, t):
        """(pulso, resp) simulados para el instante t."""
        frac = self.fraccion(t)
        pulso = pulso_objetivo(self.modo, self.referencia(), frac)
        pulso += self.rng.uniform(-RUIDO_LPM, RUIDO_LPM)
        resp = RESP_BASE + RESP_DESVIO * frac + self.rng.uniform(-0.5, 0.5)
        return pulso, resp

    async def _abrir(self):
        self._tarea = asyncio.create_task(self._bucle())

    async def _cerrar(self):
        self._tarea.cancel()

    async def _bucle(self):
        while True:
            t = self.reloj.t()
            pulso, resp = self.leer(t)
            self.ultimo_pulso = pulso
            self.emitir(self.muestra("pulso", pulso, CALIDAD, t=t))
            self.emitir(self.muestra("resp", resp, CALIDAD, t=t))
            await asyncio.sleep(1.0)
