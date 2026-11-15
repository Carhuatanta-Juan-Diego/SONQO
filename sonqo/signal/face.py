"""Zona de piel: frente y mejillas.

Con MediaPipe Face Mesh se usan tres polígonos de la malla. Si MediaPipe no está,
plan B: detector Haar de OpenCV y un rectángulo en la frente (ancho 50 % de la cara,
alto 15 %, desde el 8 % superior).

Por cuadro entrega el promedio de R, G, B dentro de la zona y el movimiento
(desplazamiento medio de los puntos entre cuadros, en píxeles).
Los cuadros se procesan en memoria y no se guardan.
"""

import cv2
import numpy as np

FRENTE = [67, 109, 10, 338, 297, 299, 9, 69]
MEJILLA_IZQ = [117, 118, 101, 36, 205, 187, 123]
MEJILLA_DER = [346, 347, 330, 266, 425, 411, 352]
POLIGONOS = [FRENTE, MEJILLA_IZQ, MEJILLA_DER]

try:
    import mediapipe as mp
except ImportError:  # plan B
    mp = None


class ZonaPiel:
    def __init__(self, usar_mediapipe=True):
        self.metodo = "mediapipe" if (usar_mediapipe and mp is not None) else "haar"
        if self.metodo == "mediapipe":
            self._malla = mp.solutions.face_mesh.FaceMesh(
                max_num_faces=1, refine_landmarks=False,
                min_detection_confidence=0.5, min_tracking_confidence=0.5)
        else:
            ruta = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            self._haar = cv2.CascadeClassifier(ruta)
        self._puntos_prev = None
        self.ultima_caja = None  # (x, y, ancho, alto) de la cara, para la zona del pecho
        self.poligonos = []      # zona de piel del último cuadro (para la vista previa)

    def procesar(self, cuadro_bgr):
        """Devuelve (rgb, hay_cara, movimiento_px)."""
        puntos, mascara = (self._mediapipe if self.metodo == "mediapipe" else self._haar_zona)(cuadro_bgr)
        if mascara is None:
            self._puntos_prev = None
            self.poligonos = []
            return None, False, None
        b, g, r, _ = cv2.mean(cuadro_bgr, mascara)
        mov = 0.0
        if self._puntos_prev is not None and len(self._puntos_prev) == len(puntos):
            mov = float(np.mean(np.linalg.norm(puntos - self._puntos_prev, axis=1)))
        self._puntos_prev = puntos
        return (r, g, b), True, mov

    def _mediapipe(self, cuadro):
        res = self._malla.process(cv2.cvtColor(cuadro, cv2.COLOR_BGR2RGB))
        if not res.multi_face_landmarks:
            return None, None
        alto, ancho = cuadro.shape[:2]
        lm = res.multi_face_landmarks[0].landmark
        todos = np.array([[p.x * ancho, p.y * alto] for p in lm], dtype=np.float32)
        mascara = np.zeros((alto, ancho), np.uint8)
        self.poligonos = [todos[poli].astype(np.int32) for poli in POLIGONOS]
        for poli in self.poligonos:
            cv2.fillPoly(mascara, [poli], 255)
        x0, y0 = todos.min(axis=0)
        x1, y1 = todos.max(axis=0)
        self.ultima_caja = (int(x0), int(y0), int(x1 - x0), int(y1 - y0))
        return todos[sum(POLIGONOS, [])], mascara

    def _haar_zona(self, cuadro):
        gris = cv2.cvtColor(cuadro, cv2.COLOR_BGR2GRAY)
        caras = self._haar.detectMultiScale(gris, scaleFactor=1.2, minNeighbors=5, minSize=(80, 80))
        if len(caras) == 0:
            return None, None
        x, y, w, h = max(caras, key=lambda c: c[2] * c[3])
        self.ultima_caja = (int(x), int(y), int(w), int(h))
        mascara = np.zeros(gris.shape, np.uint8)
        fx, fy = int(x + 0.25 * w), int(y + 0.08 * h)
        x1, y1 = fx + int(0.5 * w), fy + int(0.15 * h)
        cv2.rectangle(mascara, (fx, fy), (x1, y1), 255, -1)
        self.poligonos = [np.array([[fx, fy], [x1, fy], [x1, y1], [fx, y1]], dtype=np.int32)]
        centro = np.array([[x + w / 2, y + h / 2]], dtype=np.float32)
        return centro, mascara

    def cerrar(self):
        if self.metodo == "mediapipe":
            self._malla.close()
