"""Modo demo: el caso simulado de desvío y su línea de tiempo.

El caso tiene tres tramos (los genera scripts/make_replay.py con las mismas funciones):
  reposo   0–120 s   (se repite)
  desvío   120–150 s sube a 141 lpm; 150–300 s se mantiene (se repite)
  regreso  300–330 s baja al reposo; 330–450 s reposo (se repite)

Los bucles duran un número entero de respiraciones, así no hay saltos de fase.
Cuando el panel pone el radar en `desvio`, la reproducción salta al tramo de desvío
al mismo tiempo, así radar y reproducción suben juntos (son dos fuentes simuladas).
"""

PULSO_ALTO = 141.0
PULSO_BASE_CSV = 68.0
RESP_BASE = 15.0
RESP_DESVIO = 7.0
TEMP_BASE = 36.6
TEMP_DESVIO = 0.2
RAMPA_S = 30.0

REPOSO = (0.0, 120.0)
DESVIO_INICIO, DESVIO_BUCLE = 120.0, (150.0, 300.0)
REGRESO_INICIO, REGRESO_BUCLE = 300.0, (330.0, 450.0)
DURACION = 450.0


def fraccion_caso(pos):
    """0 en reposo, 1 en el desvío pleno, rampas lineales de 30 s entre ambos."""
    if pos < DESVIO_INICIO:
        return 0.0
    if pos < DESVIO_BUCLE[0]:
        return (pos - DESVIO_INICIO) / RAMPA_S
    if pos < REGRESO_INICIO:
        return 1.0
    if pos < REGRESO_BUCLE[0]:
        return 1.0 - (pos - REGRESO_INICIO) / RAMPA_S
    return 0.0


def ajustar_a_base(pulso_csv, base):
    """El CSV está hecho con reposo de 68 lpm; se lleva al reposo de esta persona."""
    return base + (pulso_csv - PULSO_BASE_CSV) * (PULSO_ALTO - base) / (PULSO_ALTO - PULSO_BASE_CSV)


class Escenario:
    """Posición en la línea de tiempo del caso, en función del reloj monótono."""

    def __init__(self, t=0.0, velocidad=1.0):
        self.velocidad = velocidad
        self._fijar(t, 0.0, REPOSO, "reposo")

    def _fijar(self, t, pos0, bucle, fase):
        self.t0, self.pos0, self.bucle, self.fase = t, pos0, bucle, fase

    def posicion(self, t):
        p = self.pos0 + (t - self.t0) * self.velocidad
        a, b = self.bucle
        if p >= b:
            p = a + (p - a) % (b - a)
        return p

    def desvio(self, t):
        if self.fase != "desvio":
            self._fijar(t, DESVIO_INICIO, DESVIO_BUCLE, "desvio")

    def regreso(self, t):
        if self.fase == "desvio":
            self._fijar(t, REGRESO_INICIO, REGRESO_BUCLE, "regreso")

    def reposo(self, t):
        if self.fase != "reposo":
            self._fijar(t, 0.0, REPOSO, "reposo")

    def activo(self, t):
        """True mientras el caso no está en reposo (desvío o bajando)."""
        if self.fase == "desvio":
            return True
        return self.fase == "regreso" and self.posicion(t) < REGRESO_BUCLE[0]
