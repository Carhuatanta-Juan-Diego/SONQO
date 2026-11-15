"""Motor clínico: reglas R1–R4 y niveles de autonomía N0–N2.

Reglas ilustrativas, NO clínicas. Prototipo estudiantil, no es un dispositivo médico.

- R1 pulso alto en reposo: desvío del pulso hacia arriba, dos fuentes coinciden,
  poco movimiento → N2: recomienda y espera el "Sí" del astronauta.
- R2 respiración fuera del normal → N1: solo recomienda.
- R3 sensores no coinciden → N0: nada en Mi estado; el panel avisa y se pide E2.
- R4 de vuelta al normal: 60 s dentro del normal tras un evento → se cierra.

Nada de nivel N2 se ejecuta sin el "Sí": la única forma de obtener la acción
`enviar_t30` es `decidir(..., acepta=True)`.
"""

NIVELES = ["N0", "N1", "N2", "N3", "N4"]
MOVIMIENTO_MAX_PX = 3.0
VUELTA_NORMAL_S = 60.0

ACCIONES = {
    "R1": ["recomendar_reposo", "avisar_tierra", "preparar_arca"],
    "R2": ["recomendar_reposo"],
}
PASOS = {
    "R1": ["r1_paso1", "r1_paso2", "r1_paso3"],
    "R2": ["r2_paso1"],
}


def procesar_vital(gemelo, motor, vital):
    """Un segundo de decisión: vital → gemelo → motor.

    La usan la corrida en vivo y la reproducción de la caja negra, así las dos
    siguen exactamente el mismo camino.
    """
    g = gemelo.paso(vital)
    return g, motor.paso(vital, g)


def nivel_max(niveles):
    return max(niveles, key=NIVELES.index)


class Motor:
    def __init__(self, cfg, tripulante):
        m = cfg["motor"]
        self.techos = m["techos"]
        self.repreguntar_s = m["repreguntar_s"]
        self.tripulante = tripulante
        self.contador = 0
        self.evento = None            # evento abierto (R1 o R2)
        self.recomendacion = None
        self.decision = None          # última decisión sobre el evento abierto
        self.t_rechazo = None
        self.t_dentro_desde = None
        self.r3_activo = False
        self.silencio = False         # tras cerrar a mano, no reabrir hasta volver al normal
        self._pedir_verificacion = False

    # --- utilidades -----------------------------------------------------
    def _nuevo_id(self):
        self.contador += 1
        return f"EV-{self.contador:04d}"

    def nivel_de(self, regla):
        return nivel_max([self.techos[a] for a in ACCIONES[regla]])

    def tomar_pedido_verificacion(self):
        """Devuelve True una sola vez por cada R3 (para pedir E2 sin quedarse ahí)."""
        pedido, self._pedir_verificacion = self._pedir_verificacion, False
        return pedido

    @property
    def episodio(self):
        """True si hay un evento R1 abierto (el estado E3 depende de esto)."""
        return self.evento is not None and self.evento["regla"] == "R1"

    # --- paso por segundo ------------------------------------------------
    def paso(self, vital, gemelo):
        """Recibe el vital y los mensajes del gemelo. Devuelve [(tema, mensaje)]."""
        t = vital["t"]
        alguno_fuera = any(g["fuera"] for g in gemelo.values())
        if not alguno_fuera:
            self.silencio = False
        if self.evento:
            return self._seguir_evento(t, vital, gemelo, alguno_fuera)
        if self.silencio:
            return []
        return self._buscar_evento(t, vital, gemelo)

    def _buscar_evento(self, t, vital, gemelo):
        pulso, resp = gemelo.get("pulso"), gemelo.get("resp")
        coinciden = vital["coinciden"].get("pulso")
        if pulso and pulso["desvio"] and pulso["direccion"] == "arriba":
            if coinciden is True and self._quieto(vital):
                self.r3_activo = False
                return self._abrir("R1", t, vital, gemelo)
            if coinciden is False:
                return self._r3(t, vital, gemelo)
            self._pedir_verificacion = True  # una sola fuente: verificar con E2
            return []
        self.r3_activo = False
        if resp and resp["desvio"]:
            return self._abrir("R2", t, vital, gemelo)
        return []

    @staticmethod
    def _quieto(vital):
        mov = vital.get("movimiento")
        return mov is None or mov <= MOVIMIENTO_MAX_PX

    def _r3(self, t, vital, gemelo):
        if self.r3_activo:
            return []
        self.r3_activo = True
        self._pedir_verificacion = True
        evento = {"tipo": "evento", "id": self._nuevo_id(), "regla": "R3", "nivel": "N0",
                  "tripulante": self.tripulante, "inicio_t": t,
                  "por_fuente": vital["por_fuente"]["pulso"]}
        return [("evento", evento)]

    def _desvios(self, gemelo):
        res = {}
        for nombre, g in gemelo.items():
            if g["normal"] and g["medido"] is not None:
                centro = (g["normal"][0] + g["normal"][1]) / 2
                res[nombre] = round(g["medido"] - centro, 2)
        return res

    @staticmethod
    def _gravedad(vital):
        return 5 if (vital.get("pulso") or 0) >= 120 else 3

    def _abrir(self, regla, t, vital, gemelo):
        ind = "pulso" if regla == "R1" else "resp"
        self.evento = {"tipo": "evento", "id": self._nuevo_id(), "regla": regla,
                       "tripulante": self.tripulante, "inicio_t": t,
                       "gravedad": self._gravedad(vital) if regla == "R1" else 2,
                       "confianza": gemelo[ind]["confianza"], "desvio": self._desvios(gemelo)}
        self.recomendacion = {"tipo": "recomendacion", "evento": self.evento["id"],
                              "nivel": self.nivel_de(regla), "regla": regla,
                              "pasos": PASOS[regla], "t": t}
        self.decision = None
        self.t_rechazo = None
        self.t_dentro_desde = None
        return [("evento", dict(self.evento)), ("recomendacion", dict(self.recomendacion))]

    def _seguir_evento(self, t, vital, gemelo, alguno_fuera):
        salida = []
        ind = "pulso" if self.evento["regla"] == "R1" else "resp"
        if self.evento["regla"] == "R1":
            salida += self._actualizar_r1(vital, gemelo)
        if alguno_fuera:
            self.t_dentro_desde = None
        elif self.t_dentro_desde is None:
            self.t_dentro_desde = t
        if self.t_dentro_desde is not None and t - self.t_dentro_desde >= VUELTA_NORMAL_S:
            return salida + self._cerrar(t, "R4")
        if self._toca_repreguntar(t, gemelo.get(ind)):
            self.t_rechazo = None
            self.decision = None
            self.recomendacion = dict(self.recomendacion, t=t, repregunta=True)
            salida.append(("recomendacion", dict(self.recomendacion)))
        return salida

    def _actualizar_r1(self, vital, gemelo):
        """Sube la gravedad y renueva los desvíos mientras el evento sigue abierto."""
        if "pulso" not in gemelo:
            return []
        nueva = max(self.evento["gravedad"], self._gravedad(vital))
        self.evento["desvio"] = self._desvios(gemelo) or self.evento["desvio"]
        self.evento["confianza"] = max(self.evento["confianza"], gemelo["pulso"]["confianza"])
        if nueva != self.evento["gravedad"]:
            self.evento["gravedad"] = nueva
            return [("evento", dict(self.evento, actualizado=True))]
        return []

    def _toca_repreguntar(self, t, g):
        if self.t_rechazo is None or g is None or not g["fuera"]:
            return False
        return t - self.t_rechazo >= self.repreguntar_s

    def _cerrar(self, t, regla, motivo="vuelta_al_normal"):
        cierre = {"tipo": "evento", "id": self._nuevo_id(), "regla": regla, "nivel": "N0",
                  "tripulante": self.tripulante, "cierra": self.evento["id"], "t": t,
                  "motivo": motivo}
        self.evento = self.recomendacion = self.decision = None
        self.t_rechazo = self.t_dentro_desde = None
        return [("evento", cierre)]

    # --- decisiones del astronauta ----------------------------------------
    def decidir(self, evento_id, acepta, t):
        """Devuelve (mensajes, acciones). Las acciones N2 solo salen con acepta=True."""
        if not self.evento or self.evento["id"] != evento_id or not self.recomendacion:
            return [], []
        if self.decision is not None:
            return [], []  # ya respondió a esta pregunta
        self.decision = {"tipo": "decision", "evento": evento_id, "acepta": bool(acepta), "t": t}
        acciones = []
        if acepta and self.recomendacion["nivel"] == "N2":
            acciones = [a for a in ACCIONES[self.evento["regla"]] if self.techos[a] == "N2"]
        if not acepta:
            self.t_rechazo = t
        return [("decision", dict(self.decision))], acciones

    def cerrar_episodio(self, t):
        """El astronauta cierra el episodio a mano."""
        if not self.evento:
            return []
        self.silencio = True
        return self._cerrar(t, "R4", motivo="cierre_astronauta")

    def instantanea(self):
        """Estado actual para una pantalla que se conecta a mitad de la corrida."""
        res = []
        if self.evento:
            res.append(("evento", dict(self.evento)))
        if self.recomendacion:
            res.append(("recomendacion", dict(self.recomendacion)))
        if self.decision:
            res.append(("decision", dict(self.decision)))
        return res
