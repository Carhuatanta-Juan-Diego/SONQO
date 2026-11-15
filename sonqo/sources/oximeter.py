"""Oxímetro de dedo ingresado a mano desde el panel.

Solo es referencia para medir el error de la cámara: nunca entra a la fusión.
"""

from sonqo.sources.base import crear_muestra

MIN_LPM, MAX_LPM = 30, 220
VENTANA_CAMARA_S = 3.0


class Oximetro:
    def __init__(self):
        self.ultimo = None

    def registrar(self, valor, t, tm, camara=None):
        """Crea la muestra del oxímetro y su diferencia con la cámara (si hay una lectura reciente).

        `camara` es la última muestra de pulso de la cámara, o None.
        """
        valor = float(valor)
        if not MIN_LPM <= valor <= MAX_LPM:
            raise ValueError(f"el oxímetro debe estar entre {MIN_LPM} y {MAX_LPM} lpm")
        self.ultimo = valor
        extra = {}
        if camara and t - camara["t"] <= VENTANA_CAMARA_S and camara["calidad"] > 0:
            extra = {"camara": camara["valor"], "dif": round(camara["valor"] - valor, 2),
                     "camara_sim": camara["sim"]}
        return crear_muestra(t, tm, "oximetro", "pulso", valor, 1.0, False, **extra)
