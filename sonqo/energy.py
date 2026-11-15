"""Energía: la cascada E0–E3, sus disparadores y el modelo de vatios.

Es el único módulo que llama a start() y stop() de las fuentes.
Los vatios son del modelo del documento de diseño, NO mediciones.

Motivos de cambio: desvio_radar, verificacion_periodica, boton, desvio_confirmado,
vuelta_al_normal, cierre_astronauta, más dos del prototipo:
calibracion (aprender el normal necesita todos los sensores) y
no_coinciden (regla R3: el motor pide una verificación).
"""

from dataclasses import dataclass

ESTADOS = ["E0", "E1", "E2", "E3"]

COMPONENTES = {
    "E0": ["radar_bajo", "termica_espera", "mcu", "hub"],
    "E1": ["radar_activo", "termica", "mcu", "hub"],
    "E2": ["radar_activo", "termica", "mcu", "hub", "camara_rgb", "profundidad", "ia"],
    "E3": ["radar_activo", "termica", "mcu", "hub", "camara_rgb", "profundidad", "ia", "hpc"],
}

FUENTES = {
    "E0": {"radar"},
    "E1": {"radar", "termica"},
    "E2": {"radar", "termica", "camara_rgb", "profundidad"},
    "E3": {"radar", "termica", "camara_rgb", "profundidad"},
}


@dataclass
class Senales:
    """Lo que la energía necesita saber cada segundo."""
    radar_desvio: bool = False     # el radar se aleja más del umbral de lo previsto
    episodio: bool = False         # hay un evento R1 abierto (desvío confirmado)
    motivo_cierre: str = "vuelta_al_normal"
    calibrando: bool = False
    pide_verificacion: bool = False


class Energia:
    def __init__(self, cfg, fuentes=None, t0=0.0):
        e = cfg["energia"]
        self.vatios_comp = e["vatios"]
        self.e1_periodo = e["e1_periodo_s"]
        self.e1_duracion = e["e1_duracion_s"]
        self.e2_periodo = e["e2_periodo_s"]
        self.e2_duracion = e["e2_duracion_s"]
        self.umbral_radar = e["umbral_radar_lpm"]
        self.referencia = e["referencia_diseno"]
        self.fuentes = fuentes or {}
        self.estado = "E0"
        self.motivo = "inicio"
        self.t0 = self.t_prev = self.t_entrada = t0
        self.t_ult_e1 = self.t_ult_e2 = t0
        self.wh = 0.0
        self.tiempo = {s: 0.0 for s in ESTADOS}
        self.mantener_e2 = False
        self._pedido = None  # (estado, motivo) pedido a mano
        self._sostenido = False  # E2 sostenido por calibración o por "Mantener E2"

    # --- vatios -----------------------------------------------------------
    def vatios(self, estado=None):
        return round(sum(self.vatios_comp[c] for c in COMPONENTES[estado or self.estado]), 3)

    def activos(self):
        return [c.replace("_bajo", "").replace("_activo", "").replace("_espera", "")
                for c in COMPONENTES[self.estado] if not c.endswith("_espera")]

    def _integrar(self, t):
        dt = max(t - self.t_prev, 0.0)
        self.wh += self.vatios() * dt / 3600
        self.tiempo[self.estado] += dt
        self.t_prev = t

    def promedio_w(self, t):
        total = t - self.t0
        return self.wh * 3600 / total if total > 0 else self.vatios()

    # --- disparadores -------------------------------------------------------
    def radar_desviado(self, pulso_radar, previsto):
        if pulso_radar is None or previsto is None:
            return False
        return abs(pulso_radar - previsto) > self.umbral_radar

    def pedir(self, estado, motivo):
        """Botón "Verificar ahora" u otra petición manual."""
        self._pedido = (estado, motivo)

    def _objetivo(self, t, s):
        """Devuelve (estado, motivo) al que hay que ir, o None si se queda."""
        if s.episodio:
            return ("E3", "desvio_confirmado") if self.estado != "E3" else None
        if self.estado == "E3":
            return self._piso(s) or ("E0", s.motivo_cierre)
        piso = self._piso(s)
        if piso:
            self._sostenido = True
            return piso if self.estado != "E2" else None
        if self._sostenido and self.estado == "E2":
            # terminó la calibración o se soltó "Mantener E2": apagar ya, no esperar
            self._sostenido = False
            return "E0", "vuelta_al_normal"
        self._sostenido = False
        if self._pedido:
            pedido, self._pedido = self._pedido, None
            return pedido
        if s.pide_verificacion and self.estado in ("E0", "E1"):
            return "E2", "no_coinciden"
        return {"E0": self._desde_e0, "E1": self._desde_e1, "E2": self._desde_e2}[self.estado](t, s)

    def _piso(self, s):
        """Estado mínimo E2 mientras se calibra o con "Mantener E2"."""
        if s.calibrando:
            return "E2", "calibracion"
        if self.mantener_e2:
            return "E2", "boton"
        return None

    def _desde_e0(self, t, s):
        if s.radar_desvio:
            return "E1", "desvio_radar"
        if t - self.t_ult_e2 >= self.e2_periodo:
            return "E2", "verificacion_periodica"
        if t - self.t_ult_e1 >= self.e1_periodo:
            return "E1", "verificacion_periodica"
        return None

    def _desde_e1(self, t, s):
        if t - self.t_entrada < self.e1_duracion:
            return None
        return ("E2", "desvio_radar") if s.radar_desvio else ("E0", "vuelta_al_normal")

    def _desde_e2(self, t, s):
        if t - self.t_entrada < self.e2_duracion:
            return None
        return "E0", "vuelta_al_normal"

    def paso(self, t, senales):
        """Avanza un segundo. Devuelve True si cambió de estado."""
        self._integrar(t)
        objetivo = self._objetivo(t, senales)
        if not objetivo or objetivo[0] == self.estado:
            return False
        self.estado, self.motivo = objetivo
        self.t_entrada = t
        if self.estado in ("E1", "E2", "E3"):
            self.t_ult_e1 = t
        if self.estado in ("E2", "E3"):
            self.t_ult_e2 = t
        return True

    # --- fuentes ------------------------------------------------------------
    async def aplicar(self):
        """Enciende lo que pide el estado y apaga de verdad todo lo demás."""
        quiere = FUENTES[self.estado]
        for nombre, fuente in self.fuentes.items():
            if nombre in quiere and not fuente.running:
                await fuente.start()
            elif nombre not in quiere and fuente.running:
                await fuente.stop()

    def mensaje(self, t):
        total = max(t - self.t0, 1e-9)
        return {
            "t": t, "estado": self.estado, "motivo": self.motivo, "vatios": self.vatios(),
            "wh": round(self.wh, 5), "promedio_w": round(self.promedio_w(t), 3),
            "activos": self.activos(), "mantener_e2": self.mantener_e2,
            "porcentaje": {s: round(100 * v / total, 1) for s, v in self.tiempo.items()},
            "vatios_estado": {s: self.vatios(s) for s in ESTADOS},
            "referencia": self.referencia,
            "fuentes": {n: f.running for n, f in self.fuentes.items()},
        }
