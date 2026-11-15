"""Error del pulso por cámara frente al oxímetro, leído de la caja negra.

Cada vez que se registra el oxímetro en el panel, la caja negra guarda la lectura
de la cámara de ese momento y su diferencia. Este script las junta.

Uso: python scripts/error_report.py data/caja_negra/<archivo>.jsonl [--ventana 60]
  --ventana N   además, el error medio de los últimos N segundos con datos (como el panel)
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sonqo.blackbox import leer  # noqa: E402
from sonqo.clock import formatear_tm  # noqa: E402

CRITERIO_LPM = 5.0


def comparaciones(registros):
    return [r for r in registros if r["tipo"] == "oximetro" and "dif" in r["datos"]]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("archivo")
    p.add_argument("--ventana", type=float, default=60.0)
    args = p.parse_args()
    regs = leer(args.archivo)
    comps = comparaciones(regs)
    sin_camara = sum(1 for r in regs if r["tipo"] == "oximetro" and "dif" not in r["datos"])
    if not comps:
        print("No hay lecturas del oxímetro con una lectura de cámara al lado.")
        raise SystemExit(1)
    print(f"{'hora de misión':>18}  {'oxímetro':>8}  {'cámara':>7}  {'dif':>6}")
    for r in comps:
        d = r["datos"]
        sim = " (simulado)" if d.get("camara_sim") else ""
        print(f"{formatear_tm(r['tm']):>18}  {d['valor']:8.0f}  {d['camara']:7.1f}  {d['dif']:+6.1f}{sim}")
    difs = [abs(r["datos"]["dif"]) for r in comps]
    total = sum(difs) / len(difs)
    t_fin = comps[-1]["t"]
    ultimos = [abs(r["datos"]["dif"]) for r in comps if r["t"] >= t_fin - args.ventana]
    print(f"\nError medio absoluto (todo): {total:.1f} lpm en {len(difs)} lecturas")
    print(f"Error medio absoluto (últimos {args.ventana:.0f} s): {sum(ultimos) / len(ultimos):.1f} lpm "
          f"en {len(ultimos)} lecturas")
    print(f"Criterio del manual: {CRITERIO_LPM:.0f} lpm o menos → "
          f"{'CUMPLE' if total <= CRITERIO_LPM else 'NO CUMPLE'}")
    if sin_camara:
        print(f"({sin_camara} lecturas del oxímetro sin cámara encendida al lado: no cuentan)")
    if any(r["datos"].get("camara_sim") for r in comps):
        print("Aviso: la cámara era un video o una reproducción (simulado). No vale como validación.")


if __name__ == "__main__":
    main()
