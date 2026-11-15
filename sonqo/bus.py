"""Bus de publicar/suscribir con asyncio.

Cada suscriptor recibe una cola propia. Si un suscriptor se atrasa (por ejemplo,
una pestaña del navegador en segundo plano), se descarta lo más viejo para no
crecer en memoria.
"""

import asyncio

TEMAS = ["muestra", "vital", "gemelo", "energia", "evento",
         "recomendacion", "decision", "t30", "caja",
         "tripulacion", "arca", "rutina",   # compañeros, historial del ARCA y mediciones de rutina
         "pulsera"]                         # estado de la pulsera de cada tripulante (simulado)
TODOS = "*"


class Bus:
    def __init__(self, tamano_cola=500):
        self._subs = {}  # tema -> lista de colas
        self._tamano = tamano_cola

    def suscribir(self, tema=TODOS):
        """Devuelve una cola que recibe (tema, mensaje) del tema pedido o de todos."""
        self._revisar(tema, permitir_todos=True)
        cola = asyncio.Queue(maxsize=self._tamano)
        self._subs.setdefault(tema, []).append(cola)
        return cola

    def desuscribir(self, cola):
        for colas in self._subs.values():
            if cola in colas:
                colas.remove(cola)

    def publicar(self, tema, mensaje):
        """Entrega el mensaje a los suscriptores del tema y a los de todos."""
        self._revisar(tema)
        for cola in self._subs.get(tema, []) + self._subs.get(TODOS, []):
            self._poner(cola, (tema, mensaje))

    @staticmethod
    def _poner(cola, item):
        if cola.full():
            cola.get_nowait()  # descarta el más viejo
        cola.put_nowait(item)

    @staticmethod
    def _revisar(tema, permitir_todos=False):
        if tema in TEMAS or (permitir_todos and tema == TODOS):
            return
        raise ValueError(f"tema desconocido: {tema}")
