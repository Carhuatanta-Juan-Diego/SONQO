"""Pulsera simulada: pulso por PPG de muñeca a 1 Hz, siempre con sim: true.

Complementa a los sensores del módulo cuando el tripulante no está frente a ellos.
Tiene batería propia: no la maneja la cascada de energía del módulo.
- normal y desvio: sigue el mismo escenario que el radar (mismas rampas de 30 s).
- falla (radar dañado): la pulsera sigue el pulso real de reposo; por eso no coincide con el radar.
Puede vibrar para avisar al tripulante cuando SONQO le recomienda algo.
La batería también es simulada: baja poco a poco y un poco más con cada vibración.
"""

import asyncio
import random

from sonqo.sources.base import Fuente
from sonqo.sources.radar_sim import pulso_objetivo

RUIDO_LPM = 2.0
CALIDAD = 0.8   # el PPG de muñeca es algo menos confiable que el radar quieto
GASTO_S = 0.002        # % de batería por segundo (simulado: ~7 % por hora)
GASTO_VIBRACION = 0.05  # % por vibración (simulado)
VIBRA_S = 3.0          # cuánto se muestra "vibrando" en pantalla


class PulseraSim(Fuente):
    nombre = "pulsera"
    sim = True

    def __init__(self, reloj, emitir, radar, referencia, rng=None, bateria=100.0):
        super().__init__(reloj, emitir)
        self.radar = radar            # comparte el escenario del tripulante con el radar
        self.referencia = referencia
        self.rng = rng or random.Random()
        self.vibraciones = 0
        self.bateria = float(bateria)
        self.ultima = None            # última muestra de pulso
        self.vibro_t = None           # cuándo vibró por última vez
        self._tarea = None

    def leer(self, t):
        """Pulso simulado para el instante t."""
        modo = "normal" if self.radar.modo == "falla" else self.radar.modo
        pulso = pulso_objetivo(modo, self.referencia(), self.radar.fraccion(t))
        return pulso + self.rng.uniform(-RUIDO_LPM, RUIDO_LPM)

    def vibrar(self):
        """Simula la vibración que avisa al tripulante. Devuelve cuántas van."""
        self.vibraciones += 1
        self.vibro_t = self.reloj.t()
        self.bateria = max(0.0, self.bateria - GASTO_VIBRACION)
        return self.vibraciones

    def estado(self, t, tripulante):
        """Lo que muestra la pantalla de pulseras (tema `pulsera`). Todo simulado."""
        m = self.ultima
        return {"tripulante": tripulante, "t": t, "activa": self.running,
                "pulso": m["valor"] if m else None, "calidad": m["calidad"] if m else None,
                "t_muestra": m["t"] if m else None, "bateria": round(self.bateria, 1),
                "vibraciones": self.vibraciones,
                "vibrando": self.vibro_t is not None and t - self.vibro_t < VIBRA_S, "sim": True}

    async def _abrir(self):
        self._tarea = asyncio.create_task(self._bucle())

    async def _cerrar(self):
        self._tarea.cancel()

    async def _bucle(self):
        while True:
            t = self.reloj.t()
            self.ultima = self.muestra("pulso", self.leer(t), CALIDAD, t=t)
            self.bateria = max(0.0, self.bateria - GASTO_S)
            self.emitir(self.ultima)
            await asyncio.sleep(1.0)
