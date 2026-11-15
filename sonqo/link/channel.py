"""Canal Tierra-nave con retraso emulado.

Cada envío sale en `copias` copias seguidas. La copia k termina de llegar en
retraso + (k + 1) · tiempo de transmisión de una copia. Cada copia puede
perderse con probabilidad `perdida`. La Tierra acepta la primera copia con
CRC correcto y descarta las demás.
"""

import asyncio
import random

from sonqo.link.t30 import decode


class Canal:
    def __init__(self, retraso_s, copias=4, perdida=0.0, tasa_bps=500, rng=None):
        self.retraso_s = retraso_s
        self.copias = copias
        self.perdida = perdida
        self.tasa_bps = tasa_bps
        self.rng = rng or random.Random()
        self._envios = 0

    def tiempo_llegada(self, nbytes, k):
        """Segundos desde el envío hasta que termina de llegar la copia k."""
        return self.retraso_s + (k + 1) * nbytes * 8 / self.tasa_bps

    def planificar(self, raw):
        """Lista de (segundos, copia) de las copias que sobreviven al canal."""
        plan = []
        for k in range(self.copias):
            if self.rng.random() >= self.perdida:
                plan.append((self.tiempo_llegada(len(raw), k), k))
        return plan

    async def enviar(self, raw, al_llegar):
        """Programa la llegada de las copias; `al_llegar(envio, raw, copia)` se llama al llegar.

        Devuelve (id del envío, plan) sin esperar a que lleguen.
        """
        self._envios += 1
        envio = self._envios
        plan = self.planificar(raw)
        for segundos, k in plan:
            asyncio.create_task(self._entregar(segundos, envio, bytes(raw), k, al_llegar))
        return envio, plan

    @staticmethod
    async def _entregar(segundos, envio, raw, k, al_llegar):
        await asyncio.sleep(segundos)
        resultado = al_llegar(envio, raw, k)
        if asyncio.iscoroutine(resultado):
            await resultado


class Receptor:
    """Lado Tierra: acepta la primera copia válida de cada envío."""

    def __init__(self):
        self._aceptados = set()

    def recibir(self, envio, raw):
        """Devuelve (campos, crc_ok) si es la primera copia válida, o None si se descarta."""
        if envio in self._aceptados:
            return None
        campos, crc_ok = decode(raw)
        if not crc_ok:
            return None
        self._aceptados.add(envio)
        return campos, crc_ok
