import numpy as np

from sonqo.signal.rppg import EstimadorPulso, FS


def _video_sintetico(modulacion, segundos=30, f_hz=1.15, seed=3):
    """Un parche de color de 20×20: verde modulado, ruido de píxel y deriva de luz."""
    rng = np.random.default_rng(seed)
    base = np.array([150.0, 110.0, 90.0])  # R, G, B
    for n in range(int(segundos * FS)):
        t = n / FS
        deriva = 1 + 0.05 * np.sin(2 * np.pi * 0.05 * t)       # la luz cambia lento
        color = base * deriva
        color[1] *= 1 + modulacion * np.sin(2 * np.pi * f_hz * t)
        parche = color + 2.0 * rng.standard_normal((20, 20, 3))
        yield t, tuple(parche.reshape(-1, 3).mean(axis=0))


def _correr(modulacion):
    est = EstimadorPulso()
    res = None
    for t, rgb in _video_sintetico(modulacion):
        est.agregar(t, rgb, True, 0.0)
        res = est.estimar(t) if t >= 29.9 else res
    return res


def test_video_sintetico_da_69_lpm():
    res = _correr(modulacion=0.003)
    assert abs(res["pulso"] - 69) <= 3
    assert res["calidad"] >= 0.5


def test_sin_modulacion_la_calidad_es_baja():
    res = _correr(modulacion=0.0)
    assert res["calidad"] < 0.5


def test_sin_cara_la_calidad_es_cero():
    est = EstimadorPulso()
    for t, rgb in _video_sintetico(0.003, segundos=12):
        est.agregar(t, rgb, t < 11.5, 0.0)
    assert est.estimar(12.0)["calidad"] == 0.0


def test_con_movimiento_la_calidad_es_cero():
    est = EstimadorPulso()
    for t, rgb in _video_sintetico(0.003, segundos=12):
        est.agregar(t, rgb, True, 5.0)
    assert est.estimar(12.0)["calidad"] == 0.0
