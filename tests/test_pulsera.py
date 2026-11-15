"""Pulsera simulada: sigue el escenario del radar, salvo cuando el radar está dañado."""

import random

from sonqo.demo import PULSO_ALTO
from sonqo.sources.pulsera_sim import PulseraSim
from sonqo.sources.radar_sim import RadarSim


class RelojFijo:
    def __init__(self):
        self.ahora = 0.0

    def t(self):
        return self.ahora

    def tm(self, t):
        return t


def armar():
    reloj = RelojFijo()
    radar = RadarSim(reloj, lambda m: None, referencia=lambda: 54.0, rng=random.Random(1))
    pulsera = PulseraSim(reloj, lambda m: None, radar, lambda: 54.0, rng=random.Random(2))
    return radar, pulsera


def test_en_reposo_sigue_el_pulso_de_reposo():
    _, pulsera = armar()
    assert abs(pulsera.leer(10.0) - 54.0) <= 2.0


def test_en_el_desvio_sube_igual_que_el_radar():
    radar, pulsera = armar()
    radar.set_modo("desvio", 0.0)
    assert abs(pulsera.leer(60.0) - PULSO_ALTO) <= 2.0


def test_con_el_radar_danado_no_coincide_con_el():
    radar, pulsera = armar()
    radar.set_modo("falla", 0.0)
    assert abs(pulsera.leer(5.0) - 54.0) <= 2.0
    assert radar.leer(5.0)[0] - pulsera.leer(5.0) > 50


def test_la_muestra_es_simulada():
    _, pulsera = armar()
    m = pulsera.muestra("pulso", 54.0, 0.8, t=1.0)
    assert m["fuente"] == "pulsera" and m["sim"] is True


def test_vibrar_cuenta_los_avisos():
    _, pulsera = armar()
    assert pulsera.vibrar() == 1 and pulsera.vibrar() == 2


def test_estado_para_pantalla_es_simulado_y_baja_bateria():
    radar, pulsera = armar()
    pulsera.bateria = 50.0
    assert pulsera.estado(1.0, "MS-2")["pulso"] is None   # todavía no midió
    pulsera.vibrar()
    e = pulsera.estado(pulsera.vibro_t + 1.0, "MS-2")
    assert e["sim"] is True and e["tripulante"] == "MS-2"
    assert e["vibrando"] and e["vibraciones"] == 1 and pulsera.bateria < 50.0
    assert not pulsera.estado(pulsera.vibro_t + 10.0, "MS-2")["vibrando"]
