"""Arma y conecta los módulos de SONQO y corre el ciclo de un segundo.

fuentes → fusión → gemelo → motor → (Mi estado, panel, enlace, caja negra)
La energía decide qué fuentes están encendidas. Todo lo que entra (acciones del
panel y de Mi estado) se registra en la caja negra antes de aplicarse, para que
la corrida se pueda reproducir.
"""

import asyncio
import json
from collections import deque
from pathlib import Path

from sonqo import __version__
from sonqo.blackbox import CajaNegra, leer, nombre_archivo, reproducir, verificar
from sonqo.demo import Escenario
from sonqo.energy import Energia, Senales
from sonqo.engine import procesar_vital
from sonqo.fusion import Fusion
from sonqo.link.channel import Canal, Receptor
from sonqo.link.mirror import Espejo
from sonqo.link.t30 import armar_tarjeta, encode, vector_prueba
from sonqo.sources.depth import FuenteProfundidad
from sonqo.sources.oximeter import Oximetro
from sonqo.sources.pulsera_sim import PulseraSim
from sonqo.sources.radar_sim import RadarSim
from sonqo.sources.replay import ReproductorCSV
from sonqo.sources.thermal_sim import TermicaSim
from sonqo.sources.webcam import FuenteCamara
from sonqo.tripulacion import TRIPULACION, Companero, ficha
from sonqo.twin import Gemelo
from sonqo.engine import Motor, NIVELES

PULSO_POR_DEFECTO = 68.0
GUARDAR_PERFIL_S = 30
RESUMEN_ESPEJO_S = 5


def _copia_json(d):
    """Copia con tipos JSON puros: así lo vivo y lo reproducido son idénticos."""
    return json.loads(json.dumps(d))


def resumen_caja(reg):
    """Línea corta para la bitácora del panel."""
    datos = reg["datos"]
    if reg["tipo"] == "vital":
        datos = {k: datos.get(k) for k in ("pulso", "resp", "temp_piel")}
    elif reg["tipo"] == "config":
        datos = {"version": datos.get("version"), "modo": datos["config"]["modo"]}
    return {"n": reg["n"], "t": reg["t"], "tm": reg["tm"], "tipo": reg["tipo"],
            "hash": reg["hash"][:12], "datos": datos}


class Sistema:
    def __init__(self, cfg, bus, reloj, carpeta_caja="data/caja_negra", carpeta_perfiles="data/perfiles"):
        self.cfg, self.bus, self.reloj = cfg, bus, reloj
        self.tripulante = cfg["tripulante"]
        self.ultimos = {}
        self.carpeta_caja = Path(carpeta_caja)
        # historial del ARCA y mediciones de rutina de corridas anteriores (antes de abrir los archivos nuevos)
        self.arca, rutinas = self._leer_historial()
        self.rutinas = deque(rutinas, maxlen=60)
        self.caja = CajaNegra(nombre_archivo(carpeta_caja), al_registrar=self._al_registrar)
        self.ruta_perfil = Path(carpeta_perfiles) / f"{self.tripulante}.json"
        self.perfil_inicial = self._leer_perfil()
        self.gemelo = Gemelo(cfg, self.tripulante, self.perfil_inicial)
        self.fusion = Fusion(cfg, self.tripulante)
        self.motor = Motor(cfg, self.tripulante)
        self.espejo = Espejo(cfg)
        self.oximetro = Oximetro()
        self._crear_fuentes()
        trip_cfg = cfg.get("tripulacion", {})
        self.rutina_s = int(trip_cfg.get("rutina_s", 60))
        self.companeros = ([Companero(cfg, reloj, x, carpeta_caja, carpeta_perfiles)
                            for x in TRIPULACION if x != self.tripulante]
                           if trip_cfg.get("companeros") else [])
        e = cfg["enlace"]
        self.canal = Canal(e["retraso_s"], e["copias"], e["perdida"], e["tasa_bps"])
        self.receptor = Receptor()
        self.seq = 0
        self._enviados = {}
        self._estado_gemelo = {}
        self._motivo_cierre = "vuelta_al_normal"
        self._tarea = None

    # --- armado -------------------------------------------------------------
    def _crear_fuentes(self):
        cfg, t0 = self.cfg, self.reloj.t()
        self.escenario = Escenario(t0, cfg["reproduccion"]["velocidad"])
        caso = self._reproductor(cfg["reproduccion"]["caso"])
        resp = self._reproductor(cfg["profundidad"]["archivo"]) if cfg["profundidad"]["tipo"] == "replay" else None
        self.radar = RadarSim(self.reloj, self.emitir, cfg["radar_sim"]["modo"], self.referencia_pulso)
        self.termica = TermicaSim(self.reloj, self.emitir, self.radar)
        # pulsera opcional: batería propia, fuera de la cascada de energía del módulo
        self.pulsera = (PulseraSim(self.reloj, self.emitir, self.radar, self.referencia_pulso,
                                   bateria=TRIPULACION[self.tripulante]["bateria"])
                        if cfg.get("pulsera", {}).get("activa") else None)
        self.camara = FuenteCamara(cfg, self.reloj, self.emitir, self.escenario, caso, self.referencia_pulso)
        self.profundidad = FuenteProfundidad(cfg, self.reloj, self.emitir, self.escenario, resp)
        fuentes = {"radar": self.radar, "termica": self.termica,
                   "camara_rgb": self.camara, "profundidad": self.profundidad}
        self.energia = Energia(cfg, fuentes, t0=t0)

    @staticmethod
    def _reproductor(ruta):
        return ReproductorCSV(ruta) if Path(ruta).exists() else None

    def _leer_perfil(self):
        if self.ruta_perfil.exists():
            return json.loads(self.ruta_perfil.read_text(encoding="utf-8"))
        return None

    def _guardar_perfil(self):
        perfil = self.gemelo.perfil()
        if perfil:
            self.ruta_perfil.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.ruta_perfil.with_suffix(".tmp")
            tmp.write_text(json.dumps(perfil), encoding="utf-8")
            tmp.replace(self.ruta_perfil)

    def referencia_pulso(self):
        """Pulso de reposo que sigue el radar simulado: oxímetro, o el del video, o 68."""
        if self.oximetro.ultimo is not None:
            return self.oximetro.ultimo
        if self.cfg["camara"].get("fuente") == "video":
            return float(self.cfg["camara"]["pulso_referencia_video"])
        return PULSO_POR_DEFECTO

    # --- publicar y registrar ---------------------------------------------------
    def publicar(self, tema, datos):
        clave = datos.get("indicador") or datos.get("fase") or datos.get("fuente") or datos.get("tripulante")
        self.ultimos[(tema, clave)] = datos
        self.bus.publicar(tema, datos)

    def registrar(self, tipo, datos, t=None):
        t = self.reloj.t() if t is None else t
        return self.caja.registrar(tipo, datos, t, self.reloj.tm(t))

    def _al_registrar(self, reg):
        self.bus.publicar("caja", resumen_caja(reg))

    def emitir(self, muestra):
        self.fusion.agregar(muestra)
        self.publicar("muestra", muestra)

    # --- arranque y parada ---------------------------------------------------------
    async def iniciar(self):
        self.registrar("config", {"version": __version__, "config": self.cfg["_crudo"],
                                  "tripulante": self.tripulante, "perfil_inicial": self.perfil_inicial})
        await self.energia.aplicar()
        if self.pulsera:
            await self.pulsera.start()
        for c in self.companeros:
            await c.iniciar(__version__, self.cfg["_crudo"])
        self._tarea = asyncio.create_task(self._bucle())

    async def detener(self):
        if self._tarea:
            self._tarea.cancel()
        for fuente in self.energia.fuentes.values():
            await fuente.stop()
        if self.pulsera:
            await self.pulsera.stop()
        for c in self.companeros:
            await c.detener()
        self._guardar_perfil()
        self.caja.cerrar()

    async def _bucle(self):
        siguiente = self.reloj.t() + 1.0
        while True:
            await asyncio.sleep(max(siguiente - self.reloj.t(), 0))
            siguiente += 1.0
            try:
                await self.tick(round(self.reloj.t(), 3))
            except Exception as e:  # que un error de un segundo no tumbe la demo
                print(f"[sonqo] error en el ciclo: {e!r}")

    # --- el segundo ------------------------------------------------------------------
    def _fuentes_activas(self, t):
        nombres = [n for n, f in self.energia.fuentes.items() if f.running and n != "camara_rgb"]
        if self.camara.running:
            nombres.append("reproduccion" if self.camara.usa_reproduccion(t) else "camara_rgb")
        if self.pulsera and self.pulsera.running:
            nombres.append("pulsera")
        return nombres

    async def tick(self, t):
        tm = self.reloj.tm(t)
        vital = self.fusion.paso(t, tm, self._fuentes_activas(t))
        usa_pos = self.camara.running and not self.camara.usa_reproduccion(t)
        vital["movimiento"] = self.camara.movimiento if usa_pos else None
        vital = _copia_json(vital)
        self.registrar("vital", vital, t)
        self.publicar("vital", vital)
        gemelo, salida = procesar_vital(self.gemelo, self.motor, vital)
        self._publicar_gemelo(t, gemelo)
        for tema, msg in salida:
            self.registrar(tema, msg, t)
            self.publicar(tema, msg)
            if msg.get("cierra"):
                self._motivo_cierre = msg["motivo"]
                self._cerrar_arca(self.tripulante, msg["cierra"], t)
            if tema == "recomendacion" and self.pulsera:
                self._vibrar_pulsera(t, msg)
        self._tick_companeros(t)
        self._publicar_pulseras(t)
        if t >= self.rutina_s and int(t) % self.rutina_s == 0:
            self._rutina(t, vital, gemelo)
        await self._paso_energia(t)
        self.espejo.paso(t, tm, vital)
        if int(t) % RESUMEN_ESPEJO_S == 0:
            self.publicar("t30", self.espejo.resumen())
        if int(t) % GUARDAR_PERFIL_S == 0:
            self._guardar_perfil()

    def _tick_companeros(self, t):
        for c in self.companeros:
            estado, salida = c.tick(t)
            self.publicar("tripulacion", estado)
            for tema, msg in salida:
                if tema == "recomendacion":
                    c.vibrar(t, msg)
                if tema == "evento" and msg.get("cierra"):
                    self._cerrar_arca(c.tripulante, msg["cierra"], t)

    def _publicar_pulseras(self, t):
        """Una vez por segundo, la pulsera de cada tripulante (pulso, batería, vibración)."""
        if self.pulsera:
            self.publicar("pulsera", self.pulsera.estado(t, self.tripulante))
        for c in self.companeros:
            self.publicar("pulsera", c.pulsera.estado(t, c.tripulante))

    # --- mediciones de rutina ------------------------------------------------------------
    def _rutina(self, t, vital, gemelo):
        """Una foto de cada tripulante cada `rutina_s` segundos, guardada en su caja negra."""
        filas = [(self._fila_rutina(self.tripulante, t, vital, gemelo), self.registrar)]
        for c in self.companeros:
            if c.ultimo:
                filas.append((self._fila_rutina(c.tripulante, t, c.ultimo["vital"], c.ultimo["gemelo"]), c.registrar))
        for fila, registrar in filas:
            registrar("rutina", fila, t)
            self.rutinas.append(fila)
            self.publicar("rutina", fila)

    def _fila_rutina(self, tripulante, t, vital, gemelo):
        g = gemelo.get("pulso") or {}
        calib = g.get("calibracion")
        return {"tripulante": tripulante, "t": t, "tm": self.reloj.tm(t),
                "pulso": vital.get("pulso"), "resp": vital.get("resp"), "temp_piel": vital.get("temp_piel"),
                "fuera": [n for n, m in gemelo.items() if m.get("fuera")],
                "calibrando": bool(calib and calib[0] < calib[1]),
                "fuentes": vital.get("fuentes", {}).get("pulso", [])}

    # --- historial del ARCA -------------------------------------------------------------
    def _leer_historial(self):
        """Usos del ARCA y mediciones de rutina guardados en las cajas negras de corridas anteriores."""
        arca, rutinas = [], []
        for ruta in sorted(self.carpeta_caja.glob("*.jsonl")):
            try:
                regs = leer(ruta)
            except (OSError, ValueError):
                continue
            trip = regs[0]["datos"].get("tripulante") if regs and regs[0]["tipo"] == "config" else None
            abiertos = {}
            for r in regs:
                d = r["datos"]
                if r["tipo"] == "decision" and d.get("acepta") and "preparar_arca" in (d.get("acciones") or []):
                    uso = {"tripulante": d.get("tripulante") or trip, "evento": d["evento"], "tm": r["tm"],
                           "fin_tm": None, "archivo": ruta.name, "actual": False}
                    abiertos[d["evento"]] = uso
                    arca.append(uso)
                elif r["tipo"] == "evento" and d.get("cierra") in abiertos:
                    abiertos[d["cierra"]]["fin_tm"] = r["tm"]
                elif r["tipo"] == "rutina":
                    rutinas.append(d)
        return arca[-50:], rutinas[-60:]

    def _abrir_arca(self, tripulante, evento, t):
        self.arca.append({"tripulante": tripulante, "evento": evento, "tm": self.reloj.tm(t), "fin_tm": None,
                          "archivo": None, "actual": True})
        self.arca = self.arca[-50:]
        self._publicar_arca()

    def _cerrar_arca(self, tripulante, evento, t):
        for uso in self.arca:
            if uso["actual"] and uso["tripulante"] == tripulante and uso["evento"] == evento and uso["fin_tm"] is None:
                uso["fin_tm"] = self.reloj.tm(t)
                self._publicar_arca()

    def _publicar_arca(self):
        self.publicar("arca", {"historial": list(self.arca)})

    def _vibrar_pulsera(self, t, rec):
        """Avisa al tripulante con una vibración: SONQO le recomienda algo en Mi estado."""
        n = self.pulsera.vibrar()
        self._control(t, accion="pulsera_vibra", evento=rec["evento"], nivel=rec["nivel"], n=n)

    def _publicar_gemelo(self, t, gemelo):
        for nombre, msg in gemelo.items():
            self.publicar("gemelo", msg)
            clave = (msg["fuera"], msg["desvio"], msg["normal"] is not None)
            if self._estado_gemelo.get(nombre) != clave:
                self._estado_gemelo[nombre] = clave
                self.registrar("gemelo", msg, t)

    async def _paso_energia(self, t):
        senales = Senales(
            radar_desvio=self.energia.radar_desviado(self.radar.ultimo_pulso, self.gemelo.prevision("pulso"))
            if self.gemelo.calibrado else False,
            episodio=self.motor.episodio, motivo_cierre=self._motivo_cierre,
            calibrando=not self.gemelo.calibrado,
            pide_verificacion=self.motor.tomar_pedido_verificacion())
        cambio = self.energia.paso(t, senales)
        if cambio:
            await self.energia.aplicar()
        msg = self.energia.mensaje(t)
        msg["calibracion"] = list(self.gemelo.progreso_calibracion())
        if cambio:
            self.registrar("energia", msg, t)
        self.publicar("energia", msg)

    # --- acciones del panel y de Mi estado -------------------------------------------
    async def accion(self, datos):
        """Aplica una acción que llega por WebSocket. Devuelve un error legible o None."""
        nombre = datos.get("accion")
        manejador = getattr(self, f"_accion_{nombre}", None)
        if manejador is None:
            return f"acción desconocida: {nombre}"
        try:
            await manejador(datos, self.reloj.t())
        except ValueError as e:
            return str(e)
        return None

    def _companero(self, d):
        """El compañero al que va dirigida una acción, o None si es para el tripulante principal."""
        trip = d.get("tripulante")
        if not trip or trip == self.tripulante:
            return None
        for c in self.companeros:
            if c.tripulante == trip:
                return c
        raise ValueError(f"tripulante desconocido: {trip}")

    def _control(self, t, **datos):
        self.registrar("control", datos, t)

    async def _accion_oximetro(self, d, t):
        camara = self.camara.ultima if self.camara.ultima and self.camara.ultima["fuente"] == "camara_rgb" else None
        m = self.oximetro.registrar(d["valor"], t, self.reloj.tm(t), camara)
        self.registrar("oximetro", m, t)
        self.publicar("muestra", m)

    async def _accion_verificar_ahora(self, d, t):
        self._control(t, accion="verificar_ahora")
        self.energia.pedir("E2", "boton")

    async def _accion_mantener_e2(self, d, t):
        valor = bool(d.get("valor"))
        self._control(t, accion="mantener_e2", valor=valor)
        self.energia.mantener_e2 = valor

    async def _accion_radar_modo(self, d, t):
        modo = d.get("modo")
        c = self._companero(d)
        if c:
            c.set_modo(modo, t)
            return
        self._control(t, accion="radar_modo", modo=modo)
        self.radar.set_modo(modo, t)
        {"desvio": self.escenario.desvio, "normal": self.escenario.regreso,
         "falla": self.escenario.reposo}[modo](t)

    async def _accion_reiniciar_normal(self, d, t):
        self._control(t, accion="reiniciar_normal")
        self.gemelo.reiniciar()
        self._estado_gemelo = {}
        if self.ruta_perfil.exists():
            self.ruta_perfil.unlink()

    async def _accion_cerrar_episodio(self, d, t):
        c = self._companero(d)
        if c:
            for _, msg in c.cerrar_episodio(t):
                self._cerrar_arca(c.tripulante, msg["cierra"], t)
            return
        self._control(t, accion="cerrar_episodio")
        for tema, msg in self.motor.cerrar_episodio(t):
            self.registrar(tema, msg, t)
            self.publicar(tema, msg)
            self._motivo_cierre = msg["motivo"]
            self._cerrar_arca(self.tripulante, msg["cierra"], t)

    async def _accion_decision(self, d, t):
        c = self._companero(d)
        if c:
            await self._decision_companero(c, d, t)
            return
        msgs, acciones = self.motor.decidir(d.get("evento"), bool(d.get("acepta")), t)
        if msgs and self.motor.decision:
            self.motor.decision["acciones"] = acciones   # para las pantallas que se conecten después
        for tema, msg in msgs:
            self.registrar(tema, dict(msg, acciones=acciones), t)
            self.publicar(tema, dict(msg, acciones=acciones))
        if msgs and "preparar_arca" in acciones:
            self._abrir_arca(self.tripulante, d.get("evento"), t)
        if "avisar_tierra" in acciones:   # nivel N2: solo llega aquí con el "Sí"
            await self.enviar_t30(t)

    async def _decision_companero(self, c, d, t):
        """Decisión que un compañero tomó en su Mi estado (nivel N2: solo con su «sí»)."""
        salida, acciones = c.decidir(d.get("evento"), bool(d.get("acepta")), t)
        if c.ultimo:
            self.publicar("tripulacion", dict(c.ultimo, decision=c.motor.decision))
        if salida and "preparar_arca" in acciones:
            self._abrir_arca(c.tripulante, d.get("evento"), t)
        if "avisar_tierra" in acciones:
            await self.enviar_t30(t, quien=c)

    async def _accion_verificar_caja(self, d, t):
        """Verifica la cadena y reproduce las decisiones de una caja negra (por defecto, la de esta corrida)."""
        ruta = self.caja.ruta
        if d.get("archivo"):
            ruta = self.carpeta_caja / Path(str(d["archivo"])).name   # solo archivos de la carpeta de cajas
            if not ruta.exists():
                raise ValueError(f"no existe la caja negra {ruta.name}")
        ok, n, mensaje = await asyncio.to_thread(verificar, ruta)
        res = await asyncio.to_thread(reproducir, ruta)
        eventos = [m["id"] + " " + m["regla"] for tipo, m in res["registrados"]
                   if tipo == "evento" and not m.get("cierra") and not m.get("actualizado")]
        self.bus.publicar("caja", {"verificacion": {
            "integra": ok, "registros": n, "mensaje": mensaje, "misma_decision": res["igual"],
            "vital": res["vital"], "eventos": eventos, "archivo": str(ruta), "nombre": ruta.name,
            "tripulante": self._tripulante_de(ruta), "principal": ruta == self.caja.ruta, "t": t}})

    @staticmethod
    def _tripulante_de(ruta):
        with open(ruta, encoding="utf-8") as f:
            primera = f.readline()
        try:
            return json.loads(primera)["datos"].get("tripulante")
        except (ValueError, KeyError, TypeError):
            return None

    def listar_cajas(self):
        """Cajas negras de la carpeta, de la más nueva a la más vieja."""
        actuales = {self.caja.ruta.name} | {c.caja.ruta.name for c in self.companeros}
        res = []
        for ruta in sorted(self.carpeta_caja.glob("*.jsonl"), reverse=True):
            with open(ruta, encoding="utf-8") as f:
                n = sum(1 for linea in f if linea.strip())
            res.append({"archivo": ruta.name, "tripulante": self._tripulante_de(ruta), "registros": n,
                        "bytes": ruta.stat().st_size, "actual": ruta.name in actuales})
        return res

    async def _accion_t30_prueba(self, d, t):
        self._control(t, accion="t30_prueba")
        await self.enviar_t30(t, prueba=True)

    # --- enlace con la Tierra -------------------------------------------------------
    async def enviar_t30(self, t, prueba=False, quien=None):
        saturados = []
        motor = quien.motor if quien else self.motor
        caja = quien.caja if quien else self.caja
        if prueba:
            card, evento_id = vector_prueba(), None
        else:
            ev = motor.evento
            evento_id = ev["id"]
            card, saturados = armar_tarjeta(
                ev, t, self.reloj.tm(t), self.seq, caja.ultimo_hash, 0 if quien else self.espejo.datos_enviados,
                autonomia=NIVELES.index(motor.recomendacion["nivel"]))
        raw = encode(card)
        self.seq += 1
        envio, plan = await self.canal.enviar(raw, self._al_llegar)
        self._enviados[envio] = (t, raw)
        info = {"fase": "enviada", "envio": envio, "evento": evento_id, "prueba": prueba,
                "hex": raw.hex(" "), "bytes": len(raw), "campos": card, "saturados": saturados,
                "copias": self.canal.copias, "copias_que_llegan": len(plan),
                "llega_en_s": round(plan[0][0], 2) if plan else None,
                "retraso_s": self.canal.retraso_s, "tasa_bps": self.canal.tasa_bps, "t": t,
                "tripulante": quien.tripulante if quien else (None if prueba else self.tripulante)}
        self.registrar("t30_enviada", info, t)
        if quien:
            quien.registrar("t30_enviada", info, t)
        self.publicar("t30", info)

    def _al_llegar(self, envio, raw, copia):
        r = self.receptor.recibir(envio, raw)
        if r is None:
            return
        campos, crc_ok = r
        t = self.reloj.t()
        t_envio, enviado = self._enviados.get(envio, (t, b""))
        info = {"fase": "recibida", "envio": envio, "hex": raw.hex(" "), "crc_ok": crc_ok,
                "identica": raw == enviado, "campos": campos, "copia": copia,
                "retraso_s": round(t - t_envio, 2), "t": t}
        self.registrar("t30_recibida", info, t)
        self.publicar("t30", info)

    # --- para las pantallas que se conectan -------------------------------------------
    def instantanea(self):
        res = [(tema, datos) for (tema, _), datos in self.ultimos.items()
               if tema in ("vital", "gemelo", "energia", "t30", "muestra", "pulsera")]
        res += self.motor.instantanea()
        res += [("caja", resumen_caja(r)) for r in self.caja.ultimas]
        res += [("tripulacion", c.ultimo) for c in self.companeros if c.ultimo]
        res += [("arca", {"historial": list(self.arca)})]
        res += [("rutina", f) for f in self.rutinas]
        return res

    def fichas(self):
        """Quién está a bordo y con qué sensores lo ve SONQO."""
        return [ficha(x) for x in TRIPULACION if x == self.tripulante or self.companeros]
