"""Espectro: Welch, pico con interpolación parabólica y SNR."""

import numpy as np
from scipy import signal as sps

ANCHO_PICO_HZ = 0.1


def parabolic(i, y):
    """Vértice de la parábola por (i-1, i, i+1). Devuelve (x_vértice, y_vértice)."""
    if i <= 0 or i >= len(y) - 1:
        return float(i), float(y[i])
    a, b, c = y[i - 1], y[i], y[i + 1]
    den = a - 2 * b + c
    if den == 0:
        return float(i), float(b)
    d = 0.5 * (a - c) / den
    return i + d, b - 0.25 * (a - c) * d


def welch(x, fs, nperseg=256, nfft=4096):
    x = np.asarray(x, dtype=float)
    return sps.welch(x - x.mean(), fs=fs, nperseg=min(nperseg, len(x)), nfft=nfft)


def snr_db(f, p, f_pico, fmin, fmax, ancho=ANCHO_PICO_HZ):
    """Potencia en ±ancho del pico y de su primer armónico, sobre el resto de la banda."""
    banda = (f >= fmin) & (f <= fmax)
    senal = banda & ((np.abs(f - f_pico) <= ancho) | (np.abs(f - 2 * f_pico) <= ancho))
    ruido = banda & ~senal
    ps, pr = p[senal].sum(), p[ruido].sum()
    if ps <= 0 or pr <= 0:
        return -np.inf if ps <= 0 else np.inf
    return float(10 * np.log10(ps / pr))


def welch_peak(x, fs, fmin, fmax, nperseg=256, nfft=4096):
    """Frecuencia del pico dentro de [fmin, fmax] y su SNR en dB."""
    f, p = welch(x, fs, nperseg, nfft)
    banda = np.where((f >= fmin) & (f <= fmax))[0]
    i = banda[np.argmax(p[banda])]
    xv, _ = parabolic(i, p)
    f_pico = float(f[0] + xv * (f[1] - f[0]))
    return f_pico, snr_db(f, p, f_pico, fmin, fmax)


def calidad_desde_snr(snr):
    """calidad = clip((SNR + 5) / 10, 0, 1)."""
    return float(np.clip((snr + 5) / 10, 0, 1))
