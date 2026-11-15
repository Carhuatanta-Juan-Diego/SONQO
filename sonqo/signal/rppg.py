"""Pulso por cámara con el algoritmo POS (Wang et al., 2017, "Algorithmic Principles of Remote PPG").

Entrada: promedio [R, G, B] de la zona de piel por cuadro, con su marca de tiempo.
Cada segundo: POS sobre los últimos 10 s, pasa banda 0,7–3,0 Hz, Welch y pico.
"""

from collections import deque

import numpy as np
from scipy import signal as sps

from sonqo.signal.spectrum import calidad_desde_snr, snr_db, welch, parabolic

FS = 30.0          # frecuencia de trabajo (se re-muestrea a esta)
L_VENTANA = 48     # 1,6 s
VENTANA_S = 10.0
F_MIN, F_MAX = 0.7, 3.0
MOVIMIENTO_MAX_PX = 3.0


def pos(C, l=L_VENTANA):
    """POS con superposición y suma. C: matriz (n, 3) con columnas R, G, B."""
    C = np.asarray(C, dtype=float)
    n = len(C)
    H = np.zeros(n)
    for i in range(n - l + 1):
        ventana = C[i:i + l]
        Cn = ventana / ventana.mean(axis=0)
        s1 = Cn[:, 1] - Cn[:, 2]
        s2 = Cn[:, 1] + Cn[:, 2] - 2 * Cn[:, 0]
        de2 = s2.std()
        h = s1 + (s1.std() / de2 if de2 > 0 else 0.0) * s2
        H[i:i + l] += h - h.mean()
    return H


def pasa_banda(x, fs=FS, fmin=F_MIN, fmax=F_MAX, orden=3):
    sos = sps.butter(orden, [fmin, fmax], btype="band", fs=fs, output="sos")
    return sps.sosfiltfilt(sos, x)


def estimar(C, fs=FS):
    """Pulso (lpm), SNR (dB), señal filtrada y espectro a partir de 10 s de RGB."""
    h = pasa_banda(pos(C), fs)
    f, p = welch(h, fs)
    banda = np.where((f >= F_MIN) & (f <= F_MAX))[0]
    i = banda[np.argmax(p[banda])]
    xv, _ = parabolic(i, p)
    f_pico = float(f[0] + xv * (f[1] - f[0]))
    snr = snr_db(f, p, f_pico, F_MIN, F_MAX)
    return 60 * f_pico, snr, h, (f[banda], p[banda])


def _reducir(x, n):
    """Toma n puntos repartidos (para mandar al panel sin saturar el WebSocket)."""
    if len(x) <= n:
        return [round(float(v), 5) for v in x]
    idx = np.linspace(0, len(x) - 1, n).astype(int)
    return [round(float(x[i]), 5) for i in idx]


class EstimadorPulso:
    """Acumula cuadros y estima el pulso una vez por segundo."""

    def __init__(self):
        self.t = deque()
        self.rgb = deque()
        self.cara = deque()
        self.mov = deque()

    def reiniciar(self):
        for d in (self.t, self.rgb, self.cara, self.mov):
            d.clear()

    def agregar(self, t, rgb, hay_cara, movimiento):
        self.t.append(t)
        self.rgb.append(rgb if hay_cara else (self.rgb[-1] if self.rgb else (0.0, 0.0, 0.0)))
        self.cara.append(hay_cara)
        self.mov.append(movimiento)
        while self.t and self.t[0] < t - VENTANA_S - 1:
            for d in (self.t, self.rgb, self.cara, self.mov):
                d.popleft()

    def _uniforme(self):
        """Re-muestrea los últimos 10 s a 30 Hz exactos."""
        t = np.array(self.t)
        rgb = np.array(self.rgb, dtype=float)
        tu = np.arange(t[-1] - VENTANA_S, t[-1], 1 / FS)
        return np.column_stack([np.interp(tu, t, rgb[:, c]) for c in range(3)])

    def estimar(self, t_ahora):
        """Devuelve dict con pulso, calidad, snr, movimiento y detalle, o None si falta señal."""
        if len(self.t) < 2 or self.t[-1] - self.t[0] < VENTANA_S * 0.9:
            return None
        ultimo_s = [i for i, ti in enumerate(self.t) if ti >= t_ahora - 1.0]
        cara_ok = all(self.cara[i] for i in ultimo_s) and sum(self.cara) > 0.9 * len(self.cara)
        mov = float(np.mean([self.mov[i] for i in ultimo_s if self.mov[i] is not None] or [0.0]))
        C = self._uniforme()
        pulso, snr, h, (f, p) = estimar(C)
        verde = C[:, 1] / (C[:, 1].mean() or 1) - 1   # canal verde crudo, para mostrar
        calidad = calidad_desde_snr(snr)
        if not cara_ok or mov > MOVIMIENTO_MAX_PX or snr < 0:
            calidad = 0.0
        return {"pulso": round(pulso, 2), "calidad": round(calidad, 3), "snr_db": round(snr, 2),
                "movimiento": round(mov, 2), "cara": cara_ok,
                "detalle": {"cruda": _reducir(verde, 150), "senal": _reducir(h, 150), "f": _reducir(f, 160),
                            "p": _reducir(p / (p.max() or 1), 160), "pico_lpm": round(pulso, 2)}}
