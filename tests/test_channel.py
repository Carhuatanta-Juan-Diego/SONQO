import asyncio
import random
import time

from sonqo.link.channel import Canal, Receptor
from sonqo.link.t30 import encode, vector_prueba


def test_llega_despues_del_retraso_y_no_antes():
    async def correr():
        canal = Canal(retraso_s=0.2, copias=1, tasa_bps=1_000_000)
        llegadas = []
        t0 = time.monotonic()
        await canal.enviar(encode(vector_prueba()),
                           lambda envio, raw, k: llegadas.append(time.monotonic() - t0))
        await asyncio.sleep(0.15)
        assert llegadas == []  # todavía no
        await asyncio.sleep(0.2)
        assert len(llegadas) == 1 and llegadas[0] >= 0.2
    asyncio.run(correr())


def test_la_tierra_acepta_solo_la_primera_copia():
    async def correr():
        canal = Canal(retraso_s=0.05, copias=4, tasa_bps=100_000)
        receptor = Receptor()
        aceptadas = []

        def al_llegar(envio, raw, k):
            r = receptor.recibir(envio, raw)
            if r:
                aceptadas.append((k, r))
        raw = encode(vector_prueba())
        await canal.enviar(raw, al_llegar)
        await asyncio.sleep(0.2)
        assert len(aceptadas) == 1
        k, (campos, crc_ok) = aceptadas[0]
        assert k == 0 and crc_ok and encode(campos) == raw
    asyncio.run(correr())


def test_con_perdida_llega_al_menos_una_copia_en_90_por_ciento():
    canal = Canal(retraso_s=0, copias=4, perdida=0.5, rng=random.Random(2026))
    raw = encode(vector_prueba())
    exitos = sum(1 for _ in range(200) if canal.planificar(raw))
    assert exitos / 200 >= 0.9


def test_tiempo_de_las_cuatro_copias_a_500_bps():
    canal = Canal(retraso_s=8, copias=4, tasa_bps=500)
    assert round(canal.tiempo_llegada(30, 3) - 8, 2) == 1.92
