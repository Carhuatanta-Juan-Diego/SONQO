"""Genera los CSV sintéticos del caso completo (reposo, desvío a 141 lpm, regreso).

  data/replay/caso.csv  columnas t,pulso,resp  (1 Hz): pulso del caso, reposo de 68 lpm
  data/replay/resp.csv  columnas t,mm          (30 Hz): profundidad del pecho

Uso: python scripts/make_replay.py [--semilla 2026] [--carpeta data/replay]
Todo lo que sale de aquí es simulado.
"""

import argparse
import csv
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sonqo.demo import (DURACION, PULSO_ALTO, PULSO_BASE_CSV, RESP_BASE, RESP_DESVIO,  # noqa: E402
                        fraccion_caso)

FS_PROFUNDIDAD = 30
DISTANCIA_MM = 800.0     # pecho a 80 cm de la cámara
AMPLITUD_MM = 4.0        # el pecho se mueve unos 4 mm
RUIDO_MM = 0.3
DERIVA_MM, DERIVA_PERIODO_S = 1.5, 30.0   # el periodo divide a los tres bucles


def escribir(ruta, columnas, filas):
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(columnas)
        w.writerows(filas)


def caso(rng):
    filas = []
    for t in range(int(DURACION) + 1):
        frac = fraccion_caso(t)
        pulso = PULSO_BASE_CSV + (PULSO_ALTO - PULSO_BASE_CSV) * frac + rng.uniform(-1.0, 1.0)
        resp = RESP_BASE + RESP_DESVIO * frac + rng.uniform(-0.5, 0.5)
        filas.append((t, round(pulso, 2), round(resp, 2)))
    return filas


def profundidad(rng):
    """Respiración con la frecuencia del caso; la fase se integra para no tener saltos."""
    filas, fase = [], 0.0
    n = int(DURACION * FS_PROFUNDIDAD) + 1
    for k in range(n):
        t = k / FS_PROFUNDIDAD
        rpm = RESP_BASE + RESP_DESVIO * fraccion_caso(t)
        fase += 2 * math.pi * (rpm / 60) / FS_PROFUNDIDAD
        mm = (DISTANCIA_MM + AMPLITUD_MM * math.sin(fase)
              + DERIVA_MM * math.sin(2 * math.pi * t / DERIVA_PERIODO_S)
              + rng.gauss(0, RUIDO_MM))
        filas.append((round(t, 4), round(mm, 3)))
    return filas


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--semilla", type=int, default=2026)
    p.add_argument("--carpeta", default="data/replay")
    args = p.parse_args()
    rng = random.Random(args.semilla)
    carpeta = Path(args.carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    escribir(carpeta / "caso.csv", ["t", "pulso", "resp"], caso(rng))
    escribir(carpeta / "resp.csv", ["t", "mm"], profundidad(rng))
    print(f"Listo: {carpeta / 'caso.csv'} y {carpeta / 'resp.csv'} ({DURACION:.0f} s, simulados)")


if __name__ == "__main__":
    main()
