"""Puente a la voz: cortar una frase no debe congelar el servidor de SONQO."""

import asyncio
import threading
import time

from sonqo.server import _voz_trozos

ESPERA_S = 1.0   # lo que tarda la voz en mandar el siguiente trozo


class RespuestaLenta:
    """Como http.client.HTTPResponse: la segunda lectura espera al siguiente trozo,
    y cerrar espera a que la lectura en curso termine (comparten un candado)."""

    def __init__(self):
        self.candado = threading.Lock()
        self.lecturas = 0
        self.cerrada = threading.Event()

    def read1(self, n):
        with self.candado:
            self.lecturas += 1
            if self.lecturas == 1:
                return b"\x00\x00" * 100
            time.sleep(ESPERA_S)
            return b""

    def close(self):
        with self.candado:
            self.cerrada.set()


async def _mayor_pausa_del_bucle(resp):
    """Corta la frase a mitad de una lectura y mide cuánto se congela el bucle de eventos."""
    trozos = _voz_trozos(resp)

    async def consumir():
        async for _ in trozos:
            pass

    pausas, seguir = [], True

    async def latido():
        antes = time.perf_counter()
        while seguir:
            await asyncio.sleep(0.01)
            ahora = time.perf_counter()
            pausas.append(ahora - antes)
            antes = ahora

    pulso = asyncio.create_task(latido())
    tarea = asyncio.create_task(consumir())
    await asyncio.sleep(0.2)          # ya leyó el primer trozo y espera el segundo
    tarea.cancel()                    # el navegador cortó (empezó otra frase)
    try:
        await tarea
    except asyncio.CancelledError:
        pass
    await asyncio.sleep(0.3)
    seguir = False
    await pulso
    return max(pausas)


def test_cortar_una_frase_no_congela_el_bucle():
    resp = RespuestaLenta()
    assert asyncio.run(_mayor_pausa_del_bucle(resp)) < 0.25


def test_cortar_una_frase_cierra_la_conexion_con_la_voz():
    resp = RespuestaLenta()
    asyncio.run(_mayor_pausa_del_bucle(resp))
    assert resp.cerrada.wait(ESPERA_S + 1.0)
