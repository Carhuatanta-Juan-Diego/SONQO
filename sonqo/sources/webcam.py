"""Cámara de color: cuadros de la webcam o de un video, y el pulso por cámara.

- `LectorCuadros` lee en un hilo aparte y entrega cuadros con su marca de tiempo.
  stop() llama a release(): con una webcam, la luz se apaga.
  Con un archivo de video (plan sin webcam), lo reproduce en bucle a su velocidad real.
- `FuenteCamara` pasa cada cuadro por la zona de piel y POS, y publica el pulso
  cada segundo. Los cuadros se procesan en memoria y nunca se guardan.

`camara.fuente` en config.yaml:
  webcam  → cv2.VideoCapture(indice), sim: false
  video   → archivo de video, sim: true, etiqueta "video · simulado"
  replay  → sin imagen: pulso del caso reproducido (plan B), fuente "reproduccion"
En `video` y `webcam`, mientras corre el desvío simulado del panel, el pulso
sale de la reproducción del caso (fuente "reproduccion", sim: true).
"""

import asyncio
import threading
import time

import cv2

from sonqo.demo import ajustar_a_base
from sonqo.signal.face import ZonaPiel
from sonqo.signal.rppg import EstimadorPulso
from sonqo.sources.base import Fuente

DESCARTE_INICIAL_S = 1.5
CALIDAD_REPRODUCCION = 0.9
VISTA_FPS = 6          # vista previa para la pantalla: pocos cuadros por segundo
VISTA_ANCHO = 360


class LectorCuadros:
    def __init__(self, origen, ancho, alto, fps, reloj, al_cuadro):
        self.origen = origen          # índice de webcam (int) o ruta de video (str)
        self.ancho, self.alto, self.fps = ancho, alto, fps
        self.reloj = reloj
        self.al_cuadro = al_cuadro
        self.es_archivo = isinstance(origen, str)
        self._hilo = None
        self._seguir = False
        self._cap = None

    def abrir(self):
        self._seguir = True
        self._hilo = threading.Thread(target=self._correr, daemon=True)
        self._hilo.start()

    def cerrar(self):
        self._seguir = False
        if self._hilo:
            self._hilo.join(timeout=3)
        self._liberar()

    def _liberar(self):
        if self._cap is not None:
            self._cap.release()   # libera el dispositivo de verdad
            self._cap = None

    def _correr(self):
        if self.es_archivo:
            self._correr_video()
        else:
            self._correr_webcam()

    def _correr_webcam(self):
        self._cap = cv2.VideoCapture(self.origen)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.ancho)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.alto)
        self._cap.set(cv2.CAP_PROP_FPS, self.fps)
        t_inicio = self.reloj.t()
        while self._seguir:
            ok, cuadro = self._cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            t = self.reloj.t()
            if t - t_inicio >= DESCARTE_INICIAL_S:   # la exposición se está ajustando
                self.al_cuadro(t, cuadro)
        self._liberar()

    def _cuadros_video(self):
        """Genera los cuadros del archivo en bucle, a la mitad de tamaño (más rápido para la malla)."""
        self._cap = cv2.VideoCapture(self.origen)
        if not self._cap.isOpened():
            raise FileNotFoundError(f"No se pudo abrir el video {self.origen}")
        while self._seguir:
            ok, cuadro = self._cap.read()
            if not ok:
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # vuelve al inicio
                continue
            yield cv2.resize(cuadro, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
        self._liberar()

    def _correr_video(self):
        periodo = 1.0 / self.fps
        siguiente = time.monotonic()
        for cuadro in self._cuadros_video():
            self.al_cuadro(self.reloj.t(), cuadro)
            siguiente += periodo
            espera = siguiente - time.monotonic()
            if espera > 0:
                time.sleep(espera)
            else:
                siguiente = time.monotonic()  # vamos atrasados: no acumular


class FuenteCamara(Fuente):
    nombre = "camara_rgb"

    def __init__(self, cfg, reloj, emitir, escenario, caso, referencia):
        super().__init__(reloj, emitir)
        c = cfg["camara"]
        self.modo = c.get("fuente", "webcam")
        self.sim = self.modo != "webcam"
        self.escenario = escenario
        self.caso = caso                  # ReproductorCSV del caso (o None)
        self.referencia = referencia      # pulso de reposo de la persona
        origen = c["video"] if self.modo == "video" else c["indice"]
        self.lector = None
        if self.modo != "replay":
            self.lector = LectorCuadros(origen, c["ancho"], c["alto"], c["fps"], reloj, self._al_cuadro)
        self.zona = None
        self.estimador = EstimadorPulso()
        self._candado = threading.Lock()
        self._tarea = None
        self.movimiento = None
        self.ultima = None               # última muestra de pulso publicada
        self.metodo_cara = None
        self.vista_previa = c.get("vista_previa", True)
        self.vista = None                # último cuadro de vista previa (JPEG en memoria)
        self._t_vista = -1.0

    # --- ciclo de vida (lo maneja la energía) ------------------------------
    async def _abrir(self):
        self.estimador.reiniciar()
        self.movimiento = None
        if self.lector:
            if self.zona is None:
                self.zona = ZonaPiel()
                self.metodo_cara = self.zona.metodo
            self.lector.abrir()
        self._tarea = asyncio.create_task(self._bucle())

    async def _cerrar(self):
        self._tarea.cancel()
        if self.lector:
            await asyncio.to_thread(self.lector.cerrar)
        self.movimiento = None
        self.vista = None

    # --- hilo de la cámara ----------------------------------------------------
    def _al_cuadro(self, t, cuadro):
        rgb, hay_cara, mov = self.zona.procesar(cuadro)
        with self._candado:
            self.estimador.agregar(t, rgb, hay_cara, mov)
        self.movimiento = mov
        if self.vista_previa and t - self._t_vista >= 1 / VISTA_FPS:
            self._t_vista = t
            self.vista = self._dibujar_vista(cuadro)

    def _dibujar_vista(self, cuadro):
        """JPEG pequeño con la zona de piel marcada. Solo en memoria: nunca va a disco ni a la caja negra."""
        img = cuadro.copy()
        for poli in self.zona.poligonos:
            cv2.polylines(img, [poli], True, (12, 65, 194), 2, cv2.LINE_AA)   # naranja del diseño (BGR)
        escala = VISTA_ANCHO / img.shape[1]
        if escala < 1:
            img = cv2.resize(img, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)
        ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 75])
        return jpg.tobytes() if ok else None

    def _estimar(self, t):
        with self._candado:
            return self.estimador.estimar(t)

    # --- una vez por segundo -----------------------------------------------
    def usa_reproduccion(self, t):
        return self.modo == "replay" or self.escenario.activo(t)

    async def _bucle(self):
        while True:
            await asyncio.sleep(1.0)
            t = self.reloj.t()
            if self.usa_reproduccion(t):
                m = self._muestra_reproduccion(t)
            else:
                m = await self._muestra_pos(t)
            if m:
                self.ultima = m
                self.emitir(m)

    def _muestra_reproduccion(self, t):
        if self.caso is None:
            return None
        pos = self.escenario.posicion(t)
        valor = ajustar_a_base(self.caso.valor("pulso", pos), self.referencia())
        return self.muestra("pulso", valor, CALIDAD_REPRODUCCION, fuente="reproduccion",
                            sim=True, t=t)

    async def _muestra_pos(self, t):
        r = await asyncio.to_thread(self._estimar, t)
        if r is None:
            return None
        return self.muestra("pulso", r["pulso"], r["calidad"], t=t, snr_db=r["snr_db"],
                            movimiento=r["movimiento"], cara=r["cara"], detalle=r["detalle"],
                            origen=self.modo)
