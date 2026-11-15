"""Compañeros de tripulación: misma lógica que el principal, con su propia caja negra."""

import asyncio

from sonqo.blackbox import leer, nombre_archivo, reproducir, verificar
from sonqo.tripulacion import TRIPULACION, Companero


class RelojManual:
    def __init__(self):
        self.ahora = 0.0

    def t(self):
        return self.ahora

    def tm(self, t=None):
        return 1000 + (self.ahora if t is None else t)


def test_nombre_de_archivo_con_sufijo(tmp_path):
    assert nombre_archivo(tmp_path, sufijo="MS-1").name.endswith("_MS-1.jsonl")
    assert not nombre_archivo(tmp_path).name.endswith("_MS-1.jsonl")


def test_los_cuatro_tripulantes_estan_definidos():
    assert sorted(TRIPULACION) == ["MS-1", "MS-2", "MS-3", "MS-4"]
    assert "camara_rgb" not in TRIPULACION["MS-4"]["fuentes"]


def test_companero_detecta_el_desvio_y_su_caja_se_reproduce_igual(cfg, tmp_path):
    reloj = RelojManual()
    c = Companero(cfg, reloj, "MS-1", tmp_path / "cajas", tmp_path / "perfiles")
    asyncio.run(c.iniciar("test", cfg["_crudo"]))
    for f in c.fuentes:   # sin bucles: las muestras se agregan a mano, una por segundo
        asyncio.run(f.stop())
    calib = cfg["gemelo"]["calibracion_s"]
    evento = None
    for s in range(1, int(calib) + 200):
        reloj.ahora = float(s)
        if s == int(calib) + 20:
            c.set_modo("desvio", reloj.ahora)
        pulso, resp = c.radar.leer(reloj.ahora)
        c.emitir(c.radar.muestra("pulso", pulso, 0.9, t=reloj.ahora))
        c.emitir(c.radar.muestra("resp", resp, 0.9, t=reloj.ahora))
        c.emitir(c.pulsera.muestra("pulso", c.pulsera.leer(reloj.ahora), 0.8, t=reloj.ahora))
        estado, _ = c.tick(reloj.ahora)
        if estado["evento"]:
            evento = estado["evento"]
            break
    assert evento and evento["regla"] == "R1" and evento["tripulante"] == "MS-1"
    salida, acciones = c.decidir(evento["id"], True, reloj.ahora)
    assert "preparar_arca" in acciones and salida[0][1]["tripulante"] == "MS-1"
    c.caja.cerrar()
    ok, n, _ = verificar(c.caja.ruta)
    assert ok and n == len(leer(c.caja.ruta))
    assert reproducir(c.caja.ruta)["igual"]
