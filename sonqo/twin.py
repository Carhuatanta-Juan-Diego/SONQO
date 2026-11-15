"""Gemelo personal: el normal de cada tripulante, su predicción y su desvío.

Por indicador (pulso, resp, temp_piel):
- Calibración de `calibracion_s` segundos con datos: media μ y desviación σ.
- Banda "tu normal" = μ ± max(2σ, ancho mínimo).
- Después, actualización lenta con media exponencial, solo con muestras dentro de la banda.
- Filtro de Kalman de nivel local para predecir, e intervalo conformal con los
  últimos 300 errores de un paso.
- Fuera = fuera de la banda y fuera del intervalo. Desvío = fuera durante `desvio_min_s`.

El gemelo no aprende de los desvíos: ni la banda, ni el Kalman, ni los errores
del intervalo se actualizan con muestras fuera de la banda.
"""

import math
from collections import deque

INDICADORES = ["pulso", "resp", "temp_piel"]
N_ERRORES = 300
MIN_ERRORES = 30


class Kalman:
    """Nivel local: x_t = x_{t-1} + w (var Q por segundo), y_t = x_t + v (var R)."""

    def __init__(self, Q, R):
        self.Q, self.R = Q, R
        self.x = None
        self.P = None

    def predecir(self, dt=1.0):
        if self.x is not None:
            self.P += self.Q * dt

    def corregir(self, y):
        if self.x is None:
            self.x, self.P = float(y), self.R
            return
        k = self.P / (self.P + self.R)
        self.x += k * (y - self.x)
        self.P *= (1 - k)

    def prediccion(self, h):
        """(valor, varianza) previstos a h segundos."""
        return self.x, self.P + h * self.Q

    def estado(self):
        return {"x": self.x, "P": self.P}

    def cargar(self, d):
        self.x, self.P = d["x"], d["P"]


class Conformal:
    """Intervalo de predicción con corrección de muestra finita."""

    def __init__(self, alfa):
        self.alfa = alfa
        self.errores = deque(maxlen=N_ERRORES)

    def agregar(self, error):
        self.errores.append(abs(error))

    @property
    def aprendiendo(self):
        return len(self.errores) < MIN_ERRORES

    def q(self):
        n = len(self.errores)
        if n < MIN_ERRORES:
            return None
        i = math.ceil((n + 1) * (1 - self.alfa)) - 1
        return sorted(self.errores)[min(i, n - 1)]


def _actualizar_media(mu, var, y, alfa):
    """Media y varianza exponenciales."""
    delta = y - mu
    mu += alfa * delta
    var = (1 - alfa) * (var + alfa * delta * delta)
    return mu, var


class GemeloIndicador:
    def __init__(self, nombre, cfg_gemelo):
        self.nombre = nombre
        self.calib_total = cfg_gemelo["calibracion_s"]
        self.vida_media_s = cfg_gemelo["vida_media_s"]
        self.min_franja = cfg_gemelo["min_muestras_franja"]
        self.ancho_min = cfg_gemelo["ancho_min"][nombre]
        self.desvio_min_s = cfg_gemelo["desvio_min_s"]
        k = cfg_gemelo["kalman"][nombre]
        self._Q, self._R, self._alfa = k["Q"], k["R"], cfg_gemelo["alfa_conformal"]
        self.reiniciar()

    def reiniciar(self):
        self.kalman = Kalman(self._Q, self._R)
        self.conformal = Conformal(self._alfa)
        self.calib = []          # valores de la calibración
        self.mu = self.var = None
        self.franjas = [{"n": 0, "mu": None, "var": None} for _ in range(24)]
        self.t_prev = None
        self.inicio_fuera = None
        self.historial = deque()  # (t, fuera) de los últimos desvio_min_s

    @property
    def calibrado(self):
        return self.mu is not None

    # --- banda "tu normal" ---------------------------------------------
    def _normal(self, hora):
        f = self.franjas[hora]
        if f["n"] >= self.min_franja:
            return f["mu"], f["var"]
        return self.mu, self.var

    def banda(self, hora):
        mu, var = self._normal(hora)
        medio = max(2 * math.sqrt(var), self.ancho_min)
        return [mu - medio, mu + medio]

    def _aprender(self, y, hora, dt):
        alfa = 1 - 0.5 ** (dt / self.vida_media_s)
        self.mu, self.var = _actualizar_media(self.mu, self.var, y, alfa)
        f = self.franjas[hora]
        if f["mu"] is None:
            f["mu"], f["var"] = y, self.var
        else:
            f["mu"], f["var"] = _actualizar_media(f["mu"], f["var"], y, alfa)
        f["n"] += 1

    def _terminar_calibracion(self):
        n = len(self.calib)
        self.mu = sum(self.calib) / n
        self.var = sum((v - self.mu) ** 2 for v in self.calib) / max(n - 1, 1)
        self.calib = []

    # --- un paso por segundo -------------------------------------------
    def paso(self, t, tm, y, coinciden=None):
        """Procesa una medición (o None si no hay). Devuelve el mensaje `gemelo`."""
        dt = 1.0 if self.t_prev is None else max(t - self.t_prev, 1e-3)
        self.t_prev = t
        self.kalman.predecir(dt)
        if y is None:
            return None
        if not self.calibrado:
            return self._paso_calibrando(t, y)
        return self._paso_normal(t, tm, y, coinciden)

    def _paso_calibrando(self, t, y):
        previsto = self.kalman.x
        if previsto is not None:
            self.conformal.agregar(y - previsto)
        self.kalman.corregir(y)
        self.calib.append(float(y))
        segundos = len(self.calib)
        if segundos >= self.calib_total:
            self._terminar_calibracion()
        return self._mensaje(t, y, previsto, None, None, False, False, segundos)

    def _paso_normal(self, t, tm, y, coinciden):
        hora = (int(tm) % 86400) // 3600
        lo, hi = self.banda(hora)
        previsto = self.kalman.x
        q = self.conformal.q()
        intervalo = None if q is None else [previsto - q, previsto + q]
        en_banda = lo <= y <= hi
        en_intervalo = intervalo is not None and intervalo[0] <= y <= intervalo[1]
        fuera = (not en_banda) and not en_intervalo
        if en_banda:
            self.conformal.agregar(y - previsto)
            self.kalman.corregir(y)
            self._aprender(y, hora, 1.0)
        desvio = self._seguir_desvio(t, fuera)
        msg = self._mensaje(t, y, previsto, intervalo, [lo, hi], fuera, desvio, self.calib_total)
        msg["direccion"] = ("arriba" if y > hi else "abajo") if fuera else None
        msg["confianza"] = self._confianza(t, coinciden)
        return msg

    def _seguir_desvio(self, t, fuera):
        self.historial.append((t, fuera))
        while self.historial and self.historial[0][0] <= t - self.desvio_min_s:
            self.historial.popleft()
        if not fuera:
            self.inicio_fuera = None
            return False
        if self.inicio_fuera is None:
            self.inicio_fuera = t
        return t - self.inicio_fuera >= self.desvio_min_s

    def _confianza(self, t, coinciden):
        """Heurística: fracción del tiempo fuera × (1 si dos fuentes coinciden, 0,5 si no)."""
        if not self.historial:
            return 0.0
        frac = sum(1 for _, f in self.historial if f) / len(self.historial)
        return round(frac * (1.0 if coinciden is True else 0.5), 3)

    def _mensaje(self, t, y, previsto, intervalo, normal, fuera, desvio, calib_seg):
        pred60 = None
        if self.kalman.x is not None:
            x, p = self.kalman.prediccion(60)
            pred60 = [round(x, 3), round(math.sqrt(p), 3)]
        r = (lambda v: None if v is None else round(v, 3))
        return {
            "t": t, "indicador": self.nombre, "medido": r(y), "previsto": r(previsto),
            "intervalo": None if intervalo is None else [r(v) for v in intervalo],
            "normal": None if normal is None else [r(v) for v in normal],
            "fuera": fuera, "aprendiendo": self.conformal.aprendiendo or not self.calibrado,
            "desvio": desvio, "direccion": None, "confianza": 0.0,
            "calibracion": [min(calib_seg, self.calib_total), self.calib_total],
            "prediccion_60": pred60,
        }

    # --- perfil en disco -----------------------------------------------
    def perfil(self):
        if not self.calibrado:
            return None
        return {"mu": self.mu, "var": self.var, "franjas": self.franjas,
                "kalman": self.kalman.estado(), "errores": list(self.conformal.errores)}

    def cargar_perfil(self, p):
        self.mu, self.var = p["mu"], p["var"]
        self.franjas = p["franjas"]
        self.kalman.cargar(p["kalman"])
        self.conformal.errores.extend(p.get("errores", []))


class Gemelo:
    """Gemelo de un tripulante: un GemeloIndicador por indicador."""

    def __init__(self, cfg, tripulante, perfil=None):
        self.tripulante = tripulante
        self.indicadores = {n: GemeloIndicador(n, cfg["gemelo"]) for n in INDICADORES}
        if perfil:
            self.cargar_perfil(perfil)

    @property
    def calibrado(self):
        return all(g.calibrado for g in self.indicadores.values())

    def progreso_calibracion(self):
        """(segundos, total) del indicador más atrasado."""
        g = min(self.indicadores.values(),
                key=lambda g: g.calib_total if g.calibrado else len(g.calib))
        return (g.calib_total if g.calibrado else len(g.calib)), g.calib_total

    def paso(self, vital):
        """Pasa un `vital` por los tres indicadores. Devuelve {indicador: mensaje}."""
        coinciden = vital.get("coinciden", {}).get("pulso")
        salida = {}
        for nombre, g in self.indicadores.items():
            msg = g.paso(vital["t"], vital["tm"], vital.get(nombre),
                         coinciden if nombre == "pulso" else True)
            if msg:
                msg["tripulante"] = self.tripulante
                salida[nombre] = msg
        return salida

    def prevision(self, indicador):
        return self.indicadores[indicador].kalman.x

    def reiniciar(self):
        for g in self.indicadores.values():
            g.reiniciar()

    def perfil(self):
        if not self.calibrado:
            return None
        return {"tripulante": self.tripulante,
                "indicadores": {n: g.perfil() for n, g in self.indicadores.items()}}

    def cargar_perfil(self, p):
        for n, datos in p["indicadores"].items():
            self.indicadores[n].cargar_perfil(datos)
