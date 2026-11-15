"""Cámara de profundidad: respiración por el movimiento del pecho.

`profundidad.tipo` en config.yaml:
  replay     → lee data/replay/resp.csv (columnas t,mm) a 30 Hz, sim: true
  realsense  → Intel RealSense con pyrealsense2 (opcional, no probado sin el equipo)
En ambos casos, cada cuadro da la profundidad mediana (mm) de la zona del pecho
y cada segundo se publica la respiración.
"""

import asyncio
import threading

from sonqo.signal.resp_depth import FS, EstimadorResp, mediana_mm, zona_pecho
from sonqo.sources.base import Fuente


class FuenteProfundidad(Fuente):
    nombre = "profundidad"

    def __init__(self, cfg, reloj, emitir, escenario, reproductor=None):
        super().__init__(reloj, emitir)
        self.tipo = cfg["profundidad"]["tipo"]
        self.sim = self.tipo == "replay"
        self.escenario = escenario
        self.reproductor = reproductor
        self.estimador = EstimadorResp()
        self._candado = threading.Lock()
        self._tareas = []
        self._t_ultimo = None
        self._realsense = None

    async def _abrir(self):
        self.estimador.reiniciar()
        self._t_ultimo = self.reloj.t()
        if self.tipo == "realsense":
            self._realsense = LectorRealSense(self.reloj, self._agregar)
            await asyncio.to_thread(self._realsense.abrir)
        else:
            self._tareas.append(asyncio.create_task(self._bucle_replay()))
        self._tareas.append(asyncio.create_task(self._bucle_estimar()))

    async def _cerrar(self):
        for tarea in self._tareas:
            tarea.cancel()
        self._tareas = []
        if self._realsense:
            await asyncio.to_thread(self._realsense.cerrar)
            self._realsense = None

    def _agregar(self, t, mm):
        with self._candado:
            self.estimador.agregar(t, mm)

    async def _bucle_replay(self):
        """Cada 0,1 s agrega los cuadros de 30 Hz que tocaban según la línea de tiempo."""
        while True:
            await asyncio.sleep(0.1)
            ahora = self.reloj.t()
            tk = self._t_ultimo + 1 / FS
            while tk <= ahora:
                pos = self.escenario.posicion(tk)
                self._agregar(tk, self.reproductor.valor("mm", pos))
                self._t_ultimo = tk
                tk += 1 / FS

    async def _bucle_estimar(self):
        while True:
            await asyncio.sleep(1.0)
            with self._candado:
                r = self.estimador.estimar()
            if r:
                self.emitir(self.muestra("resp", r["resp"], r["calidad"], snr_db=r["snr_db"]))


class LectorRealSense:
    """Lee profundidad de una RealSense en un hilo. Requiere `pip install pyrealsense2`."""

    def __init__(self, reloj, al_mm):
        self.reloj, self.al_mm = reloj, al_mm
        self._seguir = False
        self._hilo = None
        self._pipe = None

    def abrir(self):
        import numpy as np
        import pyrealsense2 as rs
        self._np = np
        self._pipe = rs.pipeline()
        conf = rs.config()
        conf.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
        perfil = self._pipe.start(conf)
        self._escala_mm = perfil.get_device().first_depth_sensor().get_depth_scale() * 1000
        self._seguir = True
        self._hilo = threading.Thread(target=self._correr, daemon=True)
        self._hilo.start()

    def _correr(self):
        while self._seguir:
            cuadro = self._pipe.wait_for_frames().get_depth_frame()
            if not cuadro:
                continue
            prof = self._np.asanyarray(cuadro.get_data()) * self._escala_mm
            caja = zona_pecho(None, prof.shape[1], prof.shape[0])
            self.al_mm(self.reloj.t(), mediana_mm(prof, caja))

    def cerrar(self):
        self._seguir = False
        if self._hilo:
            self._hilo.join(timeout=3)
        if self._pipe:
            self._pipe.stop()   # apaga el sensor
