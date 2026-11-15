"""Compañeros de tripulación: la misma lógica que el tripulante principal, con sensores simulados.

Cada compañero tiene su fusión, su gemelo, su motor de reglas y su propia caja negra.
No tienen cámara: miden con radar, cámara térmica y pulsera simulados, según dónde estén.
Todo lo que producen lleva sim: true.
"""

import json
from pathlib import Path

from sonqo.blackbox import CajaNegra, nombre_archivo
from sonqo.engine import Motor, procesar_vital
from sonqo.fusion import Fusion
from sonqo.sources.pulsera_sim import PulseraSim
from sonqo.sources.radar_sim import RadarSim
from sonqo.sources.thermal_sim import TermicaSim
from sonqo.twin import Gemelo

# Dónde está cada tripulante y con qué sensores lo ve SONQO (sandbox).
TRIPULACION = {
    "MS-1": {"ubicacion": "laboratorio", "pulso": 62.0, "fuentes": ["radar", "termica", "pulsera"], "bateria": 84.0},
    "MS-2": {"ubicacion": "modulo_trabajo", "pulso": None, "fuentes": ["camara_rgb", "radar", "termica", "profundidad", "pulsera"], "bateria": 91.0},
    "MS-3": {"ubicacion": "cabina", "pulso": 58.0, "fuentes": ["radar", "termica", "pulsera"], "bateria": 67.0},
    "MS-4": {"ubicacion": "camarote", "pulso": 50.0, "fuentes": ["radar", "pulsera"], "bateria": 73.0},
}


def ficha(tripulante):
    """Datos fijos de un tripulante para las pantallas."""
    d = TRIPULACION[tripulante]
    return {"tripulante": tripulante, "ubicacion": d["ubicacion"], "fuentes": list(d["fuentes"])}


class Companero:
    def __init__(self, cfg, reloj, tripulante, carpeta_caja="data/caja_negra", carpeta_perfiles="data/perfiles"):
        datos = TRIPULACION[tripulante]
        self.cfg, self.reloj, self.tripulante = cfg, reloj, tripulante
        self.ubicacion, self.nombres_fuentes = datos["ubicacion"], datos["fuentes"]
        self.caja = CajaNegra(nombre_archivo(carpeta_caja, sufijo=tripulante))
        self.ruta_perfil = Path(carpeta_perfiles) / f"{tripulante}.json"
        self.perfil_inicial = (json.loads(self.ruta_perfil.read_text(encoding="utf-8"))
                               if self.ruta_perfil.exists() else None)
        self.gemelo = Gemelo(cfg, tripulante, self.perfil_inicial)
        self.fusion = Fusion(cfg, tripulante)
        self.motor = Motor(cfg, tripulante)
        base = datos["pulso"]
        self.radar = RadarSim(reloj, self.emitir, "normal", lambda: base)
        self.fuentes = [self.radar]
        if "termica" in self.nombres_fuentes:
            self.fuentes.append(TermicaSim(reloj, self.emitir, self.radar))
        self.pulsera = PulseraSim(reloj, self.emitir, self.radar, lambda: base, bateria=datos["bateria"])
        self.fuentes.append(self.pulsera)
        self.estado_gemelo = {}
        self.ultimo = None

    # --- caja negra y sensores ----------------------------------------------------
    def registrar(self, tipo, datos, t):
        return self.caja.registrar(tipo, datos, t, self.reloj.tm(t))

    def emitir(self, muestra):
        self.fusion.agregar(muestra)

    async def iniciar(self, version, crudo):
        self.registrar("config", {"version": version, "config": crudo, "tripulante": self.tripulante,
                                  "perfil_inicial": self.perfil_inicial}, self.reloj.t())
        for f in self.fuentes:
            await f.start()

    async def detener(self):
        for f in self.fuentes:
            await f.stop()
        self.guardar_perfil()
        self.caja.cerrar()

    def guardar_perfil(self):
        perfil = self.gemelo.perfil()
        if perfil:
            self.ruta_perfil.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.ruta_perfil.with_suffix(".tmp")
            tmp.write_text(json.dumps(perfil), encoding="utf-8")
            tmp.replace(self.ruta_perfil)

    # --- el segundo -----------------------------------------------------------------
    def tick(self, t):
        """Procesa un segundo. Devuelve (estado para las pantallas, salida del motor)."""
        tm = self.reloj.tm(t)
        vital = self.fusion.paso(t, tm, [f.nombre for f in self.fuentes if f.running])
        vital["movimiento"] = None
        vital = json.loads(json.dumps(vital))
        self.registrar("vital", vital, t)
        gemelo, salida = procesar_vital(self.gemelo, self.motor, vital)
        for nombre, msg in gemelo.items():
            clave = (msg["fuera"], msg["desvio"], msg["normal"] is not None)
            if self.estado_gemelo.get(nombre) != clave:
                self.estado_gemelo[nombre] = clave
                self.registrar("gemelo", msg, t)
        for tema, msg in salida:
            self.registrar(tema, msg, t)
        self.ultimo = self.estado(t, tm, vital, gemelo)
        return self.ultimo, salida

    def estado(self, t, tm, vital, gemelo):
        m = self.motor
        return {"tripulante": self.tripulante, "t": t, "tm": tm, "ubicacion": self.ubicacion,
                "fuentes": self.nombres_fuentes, "vital": vital, "gemelo": gemelo,
                "evento": m.evento, "recomendacion": m.recomendacion, "decision": m.decision,
                "radar_modo": self.radar.modo, "caja": str(self.caja.ruta), "registros": self.caja.n,
                "sim": True}

    # --- acciones -------------------------------------------------------------------
    def set_modo(self, modo, t):
        self.radar.set_modo(modo, t)   # valida el modo antes de registrarlo
        self.registrar("control", {"accion": "radar_modo", "modo": modo}, t)

    def decidir(self, evento, acepta, t):
        msgs, acciones = self.motor.decidir(evento, acepta, t)
        if msgs and self.motor.decision:
            self.motor.decision["acciones"] = acciones
        salida = [(tema, dict(msg, acciones=acciones, tripulante=self.tripulante)) for tema, msg in msgs]
        for tema, msg in salida:
            self.registrar(tema, msg, t)
        return salida, acciones

    def cerrar_episodio(self, t):
        self.registrar("control", {"accion": "cerrar_episodio"}, t)
        salida = self.motor.cerrar_episodio(t)
        for tema, msg in salida:
            self.registrar(tema, msg, t)
        return salida

    def vibrar(self, t, rec):
        n = self.pulsera.vibrar()
        self.registrar("control", {"accion": "pulsera_vibra", "evento": rec["evento"], "nivel": rec["nivel"], "n": n}, t)
