import random

from conftest import vital
from sonqo.engine import Motor, procesar_vital
from sonqo.twin import Gemelo


def _sistema(cfg, rng):
    """Gemelo calibrado en 68 lpm y un motor nuevo."""
    g = Gemelo(cfg, "MS-2")
    m = Motor(cfg, "MS-2")
    for t in range(150):
        procesar_vital(g, m, vital(t, rng.gauss(68, 1.5), rng.gauss(15, 0.5), rng.gauss(36.6, 0.03)))
    return g, m, 150


def _correr(g, m, t0, segundos, pulso_fn, coinciden=True, rng=None, decidir=None):
    rng = rng or random.Random(0)
    salida = []
    for t in range(t0, t0 + segundos):
        v = vital(t, pulso_fn(t - t0), rng.gauss(15, 0.5), rng.gauss(36.6, 0.03), coinciden=coinciden)
        _, msgs = procesar_vital(g, m, v)
        salida += [(t, tema, msg) for tema, msg in msgs]
        if decidir:
            decidir(t, m)
    return salida


def _sube(k):
    return 68 + 73 * min(1, k / 30)


def test_r1_recomienda_n2_con_dos_fuentes_que_coinciden(cfg):
    g, m, t = _sistema(cfg, random.Random(1))
    salida = _correr(g, m, t, 60, _sube)
    recs = [msg for _, tema, msg in salida if tema == "recomendacion"]
    assert len(recs) == 1 and recs[0]["nivel"] == "N2"
    ev = [msg for _, tema, msg in salida if tema == "evento"][0]
    assert ev["regla"] == "R1" and ev["gravedad"] in (3, 5)


def test_r3_sin_coincidencia_no_hay_recomendacion(cfg):
    g, m, t = _sistema(cfg, random.Random(2))
    salida = _correr(g, m, t, 60, _sube, coinciden=False)
    assert not [1 for _, tema, _ in salida if tema == "recomendacion"]
    eventos = [msg for _, tema, msg in salida if tema == "evento"]
    assert eventos and eventos[0]["regla"] == "R3" and eventos[0]["nivel"] == "N0"


def test_sin_el_si_no_se_envia_ninguna_t30(cfg):
    g, m, t = _sistema(cfg, random.Random(3))
    acciones = []

    def decir_no(t, motor):
        if motor.recomendacion and motor.decision is None:
            acciones.extend(motor.decidir(motor.evento["id"], False, t)[1])
    _correr(g, m, t, 200, _sube, decidir=decir_no)
    assert acciones == []
    # cuando vuelve a preguntar y responde "Sí", recién ahí sale el aviso
    _correr(g, m, t + 200, cfg["motor"]["repreguntar_s"] + 1, lambda k: 141.0)
    assert m.decision is None
    _, acc = m.decidir(m.evento["id"], True, t + 300)
    assert "avisar_tierra" in acc


def test_ahora_no_vuelve_a_preguntar_tras_repreguntar_s(cfg):
    g, m, t = _sistema(cfg, random.Random(4))
    rechazos = []

    def decir_no_una_vez(t, motor):
        if motor.recomendacion and motor.decision is None and not rechazos:
            motor.decidir(motor.evento["id"], False, t)
            rechazos.append(t)
    salida = _correr(g, m, t, 150, _sube, decidir=decir_no_una_vez)
    repreguntas = [tt for tt, tema, msg in salida if tema == "recomendacion" and msg.get("repregunta")]
    assert repreguntas
    assert repreguntas[0] - rechazos[0] == cfg["motor"]["repreguntar_s"]


def test_r4_cierra_tras_60_s_en_el_normal(cfg):
    g, m, t = _sistema(cfg, random.Random(5))
    _correr(g, m, t, 60, _sube)
    assert m.episodio
    salida = _correr(g, m, t + 60, 90, lambda k: 68.0)
    cierres = [msg for _, tema, msg in salida if tema == "evento" and msg.get("cierra")]
    assert cierres and cierres[0]["regla"] == "R4" and not m.episodio


def test_r2_respiracion_es_n1(cfg):
    g, m, t = _sistema(cfg, random.Random(6))
    salida = []
    for k in range(40):
        v = vital(t + k, 68.0, 15 + 10 * min(1, k / 10), 36.6)
        salida += procesar_vital(g, m, v)[1]
    recs = [msg for tema, msg in salida if tema == "recomendacion"]
    assert recs and recs[0]["regla"] == "R2" and recs[0]["nivel"] == "N1"
