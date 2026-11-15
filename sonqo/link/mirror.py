"""Gemelo espejo: una copia del predictor corre en la Tierra con los mismos parámetros.

A bordo se sabe exactamente qué va a predecir la Tierra, porque la copia solo
cambia con lo que se le envía. Cada segundo, si la medición se aleja de esa
predicción más que la tolerancia clínica, se envía (indicador, t, valor) y las dos
copias se corrigen con ese valor. Lo demás no viaja.
"""

import struct

from sonqo.twin import INDICADORES, Kalman

FORMATO = ">BIh"                  # indicador (1 B), t de misión (4 B), valor × 100 (2 B)
BYTES_POR_DATO = struct.calcsize(FORMATO)


def empaquetar(indicador, tm, valor):
    return struct.pack(FORMATO, INDICADORES.index(indicador), int(tm), int(round(valor * 100)))


class Espejo:
    def __init__(self, cfg):
        k = cfg["gemelo"]["kalman"]
        self.tolerancias = cfg["enlace"]["tolerancias"]
        self.copia = {n: Kalman(k[n]["Q"], k[n]["R"]) for n in INDICADORES}
        self.bytes_enviados = 0
        self.bytes_todo = 0          # si se enviaran todas las mediciones procesadas
        self.datos_enviados = 0
        self.t0 = None
        self.t = None

    def paso(self, t, tm, vital):
        """Devuelve la lista de paquetes que habría que enviar este segundo."""
        if self.t0 is None:
            self.t0 = t
        self.t = t
        paquetes = []
        for nombre, kf in self.copia.items():
            y = vital.get(nombre)
            kf.predecir(1.0)
            if y is None:
                continue
            self.bytes_todo += BYTES_POR_DATO
            if kf.x is None or abs(y - kf.x) > self.tolerancias[nombre]:
                paquetes.append(empaquetar(nombre, tm, y))
                kf.corregir(y)
        self.datos_enviados += len(paquetes)
        self.bytes_enviados += BYTES_POR_DATO * len(paquetes)
        return paquetes

    def resumen(self):
        horas = max((self.t - self.t0) if self.t0 is not None else 0, 1.0)
        por_dia = 86400 / horas
        return {"fase": "espejo", "bytes": self.bytes_enviados, "datos": self.datos_enviados,
                "bytes_dia": round(self.bytes_enviados * por_dia),
                "bytes_dia_todo": round(self.bytes_todo * por_dia),
                "segundos": round(horas, 1), "referencia_diseno_kb_dia": 4.5}
