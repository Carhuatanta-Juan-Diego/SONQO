"""Fusión de fuentes: una vez por segundo, un `vital` por tripulante.

- Por indicador, toma las muestras de los últimos `ventana_s` con calidad ≥ `calidad_min`.
- Valor fusionado: promedio ponderado por calidad.
- Regla de las dos fuentes (pulso): dos fuentes distintas deben coincidir dentro
  de `tolerancia_pulso_lpm`. Con una sola fuente, `coinciden.pulso` es None.
- Si una fuente activa da calidad 0 por más de 5 s, se avisa y se sigue con las otras.
"""

from collections import deque

from sonqo.twin import INDICADORES

TAPADA_S = 5.0
FUENTES_REFERENCIA = {"oximetro"}  # nunca entran a la fusión


class Fusion:
    def __init__(self, cfg, tripulante):
        f = cfg["fusion"]
        self.ventana_s = f["ventana_s"]
        self.calidad_min = f["calidad_min"]
        self.tolerancia = f["tolerancia_pulso_lpm"]
        self.tripulante = tripulante
        self.muestras = {n: deque() for n in INDICADORES}
        self.ultima_buena = {}   # fuente -> t de la última muestra con calidad suficiente
        self.ultima_vista = {}   # fuente -> t de la última muestra (cualquier calidad)
        self.sim = {}            # fuente -> bool

    def agregar(self, m):
        if m["fuente"] in FUENTES_REFERENCIA or m["tipo"] not in self.muestras:
            return
        self.muestras[m["tipo"]].append(m)
        self.ultima_vista[m["fuente"]] = m["t"]
        self.sim[m["fuente"]] = bool(m.get("sim"))
        if m["calidad"] >= self.calidad_min:
            self.ultima_buena[m["fuente"]] = m["t"]

    def _validas(self, indicador, t):
        cola = self.muestras[indicador]
        while cola and cola[0]["t"] < t - self.ventana_s:
            cola.popleft()
        return [m for m in cola if m["calidad"] >= self.calidad_min and m["t"] <= t]

    @staticmethod
    def _ponderado(muestras):
        peso = sum(m["calidad"] for m in muestras)
        return sum(m["valor"] * m["calidad"] for m in muestras) / peso

    def _por_fuente(self, validas):
        grupos = {}
        for m in validas:
            grupos.setdefault(m["fuente"], []).append(m)
        return {f: round(self._ponderado(ms), 2) for f, ms in sorted(grupos.items())}

    def _coinciden_pulso(self, por_fuente):
        if len(por_fuente) < 2:
            return None
        valores = list(por_fuente.values())
        return max(valores) - min(valores) <= self.tolerancia

    def tapadas(self, t, activas):
        """Fuentes activas que llevan más de 5 s sin una muestra de calidad suficiente."""
        res = []
        for fuente in activas:
            vista = self.ultima_vista.get(fuente)
            buena = self.ultima_buena.get(fuente, -1e9)
            if vista is not None and t - vista < TAPADA_S and t - buena > TAPADA_S:
                res.append(fuente)
        return res

    def paso(self, t, tm, activas=()):
        """Arma el `vital` del segundo t."""
        vital = {"t": t, "tm": tm, "tripulante": self.tripulante,
                 "fuentes": {}, "por_fuente": {}, "coinciden": {}, "sim": {}}
        for ind in INDICADORES:
            validas = self._validas(ind, t)
            vital[ind] = round(self._ponderado(validas), 2) if validas else None
            pf = self._por_fuente(validas)
            vital["fuentes"][ind] = list(pf)
            vital["por_fuente"][ind] = pf
            for fuente in pf:
                vital["sim"][fuente] = self.sim.get(fuente, False)
        vital["coinciden"]["pulso"] = self._coinciden_pulso(vital["por_fuente"]["pulso"])
        vital["tapadas"] = self.tapadas(t, activas)
        return vital
