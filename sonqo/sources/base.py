"""Clase base de las fuentes. Solo el gestor de energía llama a start() y stop()."""

UNIDADES = {"pulso": "lpm", "resp": "rpm", "temp_piel": "°C"}


def crear_muestra(t, tm, fuente, tipo, valor, calidad, sim, **extra):
    """Mensaje `muestra` según el contrato de la sección 6."""
    m = {"t": round(t, 3), "tm": tm, "fuente": fuente, "tipo": tipo, "valor": round(float(valor), 2),
         "unidad": UNIDADES[tipo], "calidad": round(float(calidad), 3), "sim": bool(sim)}
    m.update(extra)
    return m


class Fuente:
    nombre = "fuente"
    sim = False

    def __init__(self, reloj, emitir):
        self.reloj = reloj
        self.emitir = emitir      # función que recibe una muestra
        self._running = False

    @property
    def running(self):
        return self._running

    async def start(self):
        if self._running:
            return
        await self._abrir()
        self._running = True

    async def stop(self):
        if not self._running:
            return
        self._running = False
        await self._cerrar()

    async def _abrir(self):
        pass

    async def _cerrar(self):
        pass

    def muestra(self, tipo, valor, calidad, fuente=None, sim=None, t=None, **extra):
        t = self.reloj.t() if t is None else t
        return crear_muestra(t, self.reloj.tm(t), fuente or self.nombre, tipo, valor, calidad,
                             self.sim if sim is None else sim, **extra)
