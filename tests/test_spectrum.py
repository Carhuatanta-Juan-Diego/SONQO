import numpy as np

from sonqo.signal.spectrum import parabolic, welch_peak


def _senoidal(ruido, seed=0, fs=30.0, segundos=10, f=1.2):
    rng = np.random.default_rng(seed)
    t = np.arange(0, segundos, 1 / fs)
    return np.sin(2 * np.pi * f * t) + ruido * rng.standard_normal(len(t)), fs


def test_senoidal_de_1_2_hz_da_72_lpm():
    x, fs = _senoidal(ruido=0.5)
    f_pico, snr = welch_peak(x, fs, 0.7, 3.0)
    assert abs(60 * f_pico - 72) <= 0.5
    assert snr > 0


def test_snr_baja_cuando_sube_el_ruido():
    snrs = [welch_peak(*_senoidal(ruido=r, seed=1), 0.7, 3.0)[1] for r in (0.2, 1.0, 3.0)]
    assert snrs[0] > snrs[1] > snrs[2]


def test_parabolic_encuentra_el_vertice():
    y = np.array([0.0, 3.0, 4.0, 3.0, 0.0]) + np.array([0, 0, 0, 0.5, 0])
    x, _ = parabolic(2, y)
    assert 2.0 < x < 2.5
    assert parabolic(0, y) == (0.0, 0.0)
