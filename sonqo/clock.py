"""Relojes de SONQO.

- `t`: reloj monótono en segundos desde el arranque (no salta si cambia la hora del sistema).
- `tm`: tiempo de misión en segundos desde el lanzamiento. En demo arranca en el
  día 214, 03:12:00 (configurable) y avanza con el reloj monótono.
"""

import time


def hora_a_segundos(hhmmss):
    """'03:12:00' -> 11520."""
    h, m, s = (int(x) for x in hhmmss.split(":"))
    return h * 3600 + m * 60 + s


def formatear_tm(tm, con_segundos=True):
    """Segundos de misión -> 'día 214 · 03:12:05' (o sin segundos)."""
    tm = int(tm)
    dia, resto = divmod(tm, 86400)
    h, resto = divmod(resto, 3600)
    m, s = divmod(resto, 60)
    hora = f"{h:02d}:{m:02d}:{s:02d}" if con_segundos else f"{h:02d}:{m:02d}"
    return f"{dia} · {hora}"


class Reloj:
    """Reloj monótono y reloj de misión, con un mismo origen."""

    def __init__(self, dia_inicio, hora_inicio, monotono=time.monotonic):
        self._monotono = monotono
        self._t0 = monotono()
        self.tm0 = dia_inicio * 86400 + hora_a_segundos(hora_inicio)

    @classmethod
    def desde_config(cls, cfg):
        return cls(cfg["mision"]["dia_inicio"], cfg["mision"]["hora_inicio"])

    def t(self):
        """Segundos desde el arranque, con milisegundos."""
        return round(self._monotono() - self._t0, 3)

    def tm(self, t=None):
        """Tiempo de misión (s) que corresponde a `t` (o a ahora)."""
        if t is None:
            t = self.t()
        return int(self.tm0 + t)
