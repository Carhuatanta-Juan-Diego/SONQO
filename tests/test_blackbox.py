import json
import random

from conftest import vital
from sonqo import __version__
from sonqo.blackbox import CajaNegra, reproducir, verificar
from sonqo.engine import Motor, procesar_vital
from sonqo.twin import Gemelo


def _escribir(ruta, n=20):
    caja = CajaNegra(ruta)
    for i in range(n):
        caja.registrar("vital", {"pulso": 68 + i, "nota": "ñandú"}, float(i), 18501120 + i)
    caja.cerrar()


def test_la_cadena_verifica(tmp_path):
    ruta = tmp_path / "caja.jsonl"
    _escribir(ruta)
    ok, n, _ = verificar(ruta)
    assert ok and n == 20


def test_alterar_un_registro_rompe_en_ese_registro(tmp_path):
    ruta = tmp_path / "caja.jsonl"
    _escribir(ruta)
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    reg = json.loads(lineas[7])
    reg["datos"]["pulso"] = 999
    lineas[7] = json.dumps(reg, ensure_ascii=False)
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    ok, n, mensaje = verificar(ruta)
    assert not ok and n == 7 and "n=7" in mensaje


def test_borrar_un_registro_rompe_la_cadena(tmp_path):
    ruta = tmp_path / "caja.jsonl"
    _escribir(ruta)
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    del lineas[3]
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    ok, n, _ = verificar(ruta)
    assert not ok and n == 3


def _corrida_sintetica(cfg, ruta):
    """Graba una corrida como lo hace el sistema: calibra, desvío, "Ahora no", "Sí", vuelta."""
    rng = random.Random(9)
    caja = CajaNegra(ruta)
    caja.registrar("config", {"version": __version__, "config": cfg["_crudo"], "tripulante": "MS-2",
                              "perfil_inicial": None}, 0.0, 18501120)
    g, m = Gemelo(cfg, "MS-2"), Motor(cfg, "MS-2")
    for t in range(400):
        pulso = 68 + 73 * min(1, max(0, t - 150) / 30) if 150 <= t < 300 else 68.0
        v = json.loads(json.dumps(vital(t, pulso + rng.uniform(-1, 1), rng.gauss(15, 0.4),
                                        rng.gauss(36.6, 0.03))))
        caja.registrar("vital", v, float(t), v["tm"])
        for tema, msg in procesar_vital(g, m, v)[1]:
            caja.registrar(tema, msg, float(t), v["tm"])
        if m.recomendacion and m.decision is None:
            acepta = t > 200
            msgs, acc = m.decidir(m.evento["id"], acepta, float(t))
            for tema, msg in msgs:
                caja.registrar(tema, dict(msg, acciones=acc), float(t), v["tm"])
    caja.cerrar()


def test_reproducir_da_la_misma_decision(cfg, tmp_path):
    ruta = tmp_path / "corrida.jsonl"
    _corrida_sintetica(cfg, ruta)
    assert verificar(ruta)[0]
    res = reproducir(ruta)
    reglas = [d.get("regla") for tipo, d in res["registrados"] if tipo == "evento"]
    assert "R1" in reglas and "R4" in reglas
    assert res["igual"], res["diferencias"]


def test_reproducir_detecta_una_decision_distinta(cfg, tmp_path):
    ruta = tmp_path / "corrida.jsonl"
    _corrida_sintetica(cfg, ruta)
    # alguien cambia la configuración registrada: el gemelo aprende otra cosa
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    reg = json.loads(lineas[0])
    reg["datos"]["config"]["gemelo"]["desvio_min_s"]["demo"] = 40
    lineas[0] = json.dumps(reg, ensure_ascii=False)
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    assert not reproducir(ruta)["igual"]
