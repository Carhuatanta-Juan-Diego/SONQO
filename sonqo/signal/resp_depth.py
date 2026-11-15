"""Respiración por profundidad: el pecho se acerca y se aleja de la cámara.

Por cuadro: mediana de profundidad (mm) en la zona del pecho. Cada segundo:
quitar la tendencia con una media móvil de 10 s, pasa banda 0,1–0,7 Hz,
Welch de los últimos 30 s y pico: resp = 60 · f_pico.
"""

from collections import deque

import numpy as np
from scipy.ndimage import uniform_filter1d

from sonqo.signal.rppg import pasa_banda
from sonqo.signal.spectrum import calidad_desde_snr, welch_peak

FS = 30.0
VENTANA_S = 30.0
F_MIN, F_MAX = 0.1, 0.7


def zona_pecho(caja_cara, ancho, alto):
    """Rectángulo (x, y, w, h) debajo de la cara, o el centro del cuadro si no hay cara."""
    if caja_cara is None:
        return ancho // 3, alto // 3, ancho // 3, alto // 3
    x, y, w, h = caja_cara
    return x, y + h, w, min(int(1.2 * h), alto - (y + h))


def mediana_mm(profundidad_mm, caja):
    x, y, w, h = caja
    zona = profundidad_mm[y:y + h, x:x + w]
    validos = zona[zona > 0]
    return float(np.median(validos)) if validos.size else None


def estimar(mm, fs=FS):
    """Respiración (rpm) y SNR a partir de una serie de profundidad uniforme."""
    x = np.asarray(mm, dtype=float)
    # media móvil de 10 s; en los bordes repite el valor extremo (sin escalones falsos)
    tendencia = uniform_filter1d(x, size=int(10 * fs), mode="nearest")
    y = pasa_banda(x - tendencia, fs, F_MIN, F_MAX, orden=2)
    f_pico, snr = welch_peak(y, fs, F_MIN, F_MAX, nperseg=len(y), nfft=8192)
    return 60 * f_pico, snr


class EstimadorResp:
    def __init__(self):
        self.t = deque()
        self.mm = deque()

    def reiniciar(self):
        self.t.clear()
        self.mm.clear()

    def agregar(self, t, mm):
        if mm is None:
            return
        self.t.append(t)
        self.mm.append(mm)
        while self.t and self.t[0] < t - VENTANA_S - 1:
            self.t.popleft()
            self.mm.popleft()

    def estimar(self):
        if len(self.t) < 2 or self.t[-1] - self.t[0] < VENTANA_S * 0.9:
            return None
        t = np.array(self.t)
        tu = np.arange(t[-1] - VENTANA_S, t[-1], 1 / FS)
        resp, snr = estimar(np.interp(tu, t, np.array(self.mm)))
        calidad = 0.0 if snr < 0 else calidad_desde_snr(snr)
        return {"resp": round(resp, 2), "calidad": round(calidad, 3), "snr_db": round(snr, 2)}
