import random

from sonqo.twin import Gemelo, GemeloIndicador

TM0 = 18501120


def _calibrar(g, rng, n=120, mu=68.0, sd=2.0):
    t = 0
    for t in range(n):
        g.paso(t, TM0 + t, rng.gauss(mu, sd))
    return t + 1


def test_banda_contiene_68_y_no_100(cfg):
    g = GemeloIndicador("pulso", cfg["gemelo"])
    _calibrar(g, random.Random(1))
    assert g.calibrado
    lo, hi = g.banda(3)
    assert lo < 68 < hi
    assert not lo < 100 < hi


def test_no_aprende_de_muestras_fuera_de_la_banda(cfg):
    g = GemeloIndicador("pulso", cfg["gemelo"])
    t = _calibrar(g, random.Random(2))
    mu, var, x = g.mu, g.var, g.kalman.x
    for k in range(60):
        g.paso(t + k, TM0 + t + k, 130.0)
    assert (g.mu, g.var, g.kalman.x) == (mu, var, x)


def test_desvio_tras_desvio_min_s_y_no_antes(cfg):
    g = GemeloIndicador("pulso", cfg["gemelo"])
    rng = random.Random(3)
    t = _calibrar(g, rng)
    for k in range(60):                       # sigue en reposo un minuto
        g.paso(t, TM0 + t, rng.gauss(68, 2))
        t += 1
    inicio_fuera = desvio_en = None
    for k in range(60):                       # sube a 141 en 30 s y se queda
        y = 68 + 73 * min(1, k / 30)
        msg = g.paso(t, TM0 + t, y)
        if msg["fuera"] and inicio_fuera is None:
            inicio_fuera = t
        if msg["desvio"] and desvio_en is None:
            desvio_en = t
        t += 1
    minimo = cfg["gemelo"]["desvio_min_s"]
    assert inicio_fuera is not None and desvio_en is not None
    assert desvio_en - inicio_fuera == minimo


def test_cobertura_conformal_entre_85_y_95(cfg):
    g = GemeloIndicador("pulso", cfg["gemelo"])
    rng = random.Random(4)
    t = _calibrar(g, rng)
    dentro = total = 0
    for k in range(3000):
        y = rng.gauss(68, 2)
        q = g.conformal.q()
        previsto = g.kalman.x
        g.paso(t, TM0 + t, y)
        t += 1
        if q is not None:
            total += 1
            dentro += abs(y - previsto) <= q
    assert 0.85 <= dentro / total <= 0.95


def test_perfil_se_guarda_y_se_carga(cfg):
    g = Gemelo(cfg, "MS-2")
    rng = random.Random(5)
    for t in range(120):
        g.paso({"t": t, "tm": TM0 + t, "pulso": rng.gauss(68, 2), "resp": rng.gauss(15, 1),
                "temp_piel": rng.gauss(36.6, 0.05), "coinciden": {"pulso": True}})
    assert g.calibrado
    otro = Gemelo(cfg, "MS-2", g.perfil())
    assert otro.calibrado
    assert otro.indicadores["pulso"].banda(3) == g.indicadores["pulso"].banda(3)
