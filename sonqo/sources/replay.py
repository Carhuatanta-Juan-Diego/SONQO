"""Reproduce un CSV como si fuera un sensor.

El CSV tiene una columna `t` (segundos) y una o más columnas de valores.
`valor(columna, pos)` interpola en la posición pos (s); la posición la da la
línea de tiempo del escenario (sonqo/demo.py), a velocidad real o acelerada.
"""

import csv
from pathlib import Path

import numpy as np


class ReproductorCSV:
    def __init__(self, ruta):
        self.ruta = Path(ruta)
        if not self.ruta.exists():
            raise FileNotFoundError(
                f"No existe {self.ruta}. Generarlo con: python scripts/make_replay.py")
        with open(self.ruta, encoding="utf-8") as f:
            filas = list(csv.DictReader(f))
        self.columnas = {c: np.array([float(r[c]) for r in filas]) for c in filas[0]}
        self.t = self.columnas["t"]

    def valor(self, columna, pos):
        return float(np.interp(pos, self.t, self.columnas[columna]))

    @property
    def duracion(self):
        return float(self.t[-1])
