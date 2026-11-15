"""Caja negra: registro .jsonl encadenado con SHA-256, solo agregar.

hash = sha256(prev + json.dumps(registro_sin_hash, sort_keys=True, ensure_ascii=False))

Uso:
  python -m sonqo.blackbox verificar data/caja_negra/<archivo>.jsonl
  python -m sonqo.blackbox reproducir data/caja_negra/<archivo>.jsonl
"""

import argparse
import hashlib
import json
from collections import deque
from datetime import datetime
from pathlib import Path

GENESIS = "0" * 64
TIPOS = ["config", "vital", "gemelo", "energia", "evento", "recomendacion", "decision",
         "t30_enviada", "t30_recibida", "oximetro", "control", "rutina"]


def _texto(registro_sin_hash):
    return json.dumps(registro_sin_hash, sort_keys=True, ensure_ascii=False)


def calcular_hash(registro_sin_hash):
    texto = registro_sin_hash["prev"] + _texto(registro_sin_hash)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def nombre_archivo(carpeta="data/caja_negra", ahora=None, sufijo=None):
    ahora = ahora or datetime.now()
    nombre = ahora.strftime("%Y-%m-%d_%H%M%S") + (f"_{sufijo}" if sufijo else "")
    return Path(carpeta) / f"{nombre}.jsonl"


class CajaNegra:
    """Escribe registros encadenados. `al_registrar(registro)` avisa de cada uno."""

    def __init__(self, ruta, al_registrar=None):
        self.ruta = Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._archivo = open(self.ruta, "a", encoding="utf-8")
        self._al_registrar = al_registrar
        self.n = 0
        self.ultimo_hash = GENESIS
        self.ultimas = deque(maxlen=15)

    def registrar(self, tipo, datos, t, tm):
        if tipo not in TIPOS:
            raise ValueError(f"tipo de registro desconocido: {tipo}")
        registro = {"n": self.n, "t": t, "tm": tm, "tipo": tipo, "datos": datos,
                    "prev": self.ultimo_hash}
        registro["hash"] = calcular_hash(registro)
        self._archivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
        self._archivo.flush()
        self.n += 1
        self.ultimo_hash = registro["hash"]
        self.ultimas.append(registro)
        if self._al_registrar:
            self._al_registrar(registro)
        return registro

    def cerrar(self):
        self._archivo.close()


def leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return [json.loads(linea) for linea in f if linea.strip()]


def verificar(ruta):
    """Recalcula la cadena. Devuelve (ok, n_registros, mensaje)."""
    prev = GENESIS
    with open(ruta, encoding="utf-8") as f:
        lineas = [linea for linea in f if linea.strip()]
    for i, linea in enumerate(lineas):
        error = _revisar_linea(linea, i, prev)
        if error:
            return False, i, error
        prev = json.loads(linea)["hash"]
    return True, len(lineas), f"Cadena íntegra: {len(lineas)} registros verificados."


def _revisar_linea(linea, i, prev):
    """Devuelve un mensaje de error o None si la línea está bien."""
    donde = f"Se rompe en el registro n={i} (línea {i + 1})"
    try:
        reg = json.loads(linea)
    except json.JSONDecodeError:
        return f"{donde}: la línea no es JSON válido."
    if reg.get("n") != i:
        return f"{donde}: el número de registro es {reg.get('n')}, se esperaba {i}."
    if reg.get("prev") != prev:
        return f"{donde}: 'prev' no coincide con el hash del registro anterior."
    sin_hash = {k: v for k, v in reg.items() if k != "hash"}
    if calcular_hash(sin_hash) != reg.get("hash"):
        return f"{donde}: el contenido fue alterado (el hash no coincide)."
    return None


def _clave(tema, msg):
    return tema + " " + json.dumps(msg, sort_keys=True, ensure_ascii=False)


def reproducir(ruta):
    """Vuelve a pasar los `vital` por el gemelo y el motor, con la configuración registrada.

    Las decisiones y los controles registrados se aplican en el mismo orden.
    Devuelve un dict con `igual`, los conteos y las diferencias.
    """
    from sonqo import __version__
    from sonqo.config import resolver_modo
    from sonqo.engine import Motor, procesar_vital
    from sonqo.twin import Gemelo

    regs = leer(ruta)
    if not regs or regs[0]["tipo"] != "config":
        raise ValueError("el archivo no empieza con un registro config")
    c = regs[0]["datos"]
    cfg = resolver_modo(c["config"], c["config"]["modo"])
    gemelo = Gemelo(cfg, c["tripulante"], c.get("perfil_inicial"))
    motor = Motor(cfg, c["tripulante"])
    producidos, registrados, n_vital = [], [], 0
    for r in regs[1:]:
        tipo, d = r["tipo"], r["datos"]
        if tipo == "vital":
            n_vital += 1
            producidos += procesar_vital(gemelo, motor, d)[1]
        elif tipo == "decision":
            motor.decidir(d["evento"], d["acepta"], d["t"])
        elif tipo == "control" and d.get("accion") == "reiniciar_normal":
            gemelo.reiniciar()
        elif tipo == "control" and d.get("accion") == "cerrar_episodio":
            producidos += motor.cerrar_episodio(r["t"])
        elif tipo in ("evento", "recomendacion"):
            registrados.append((tipo, d))
    a = [_clave(*x) for x in registrados]
    b = [_clave(*x) for x in producidos]
    diferencias = [(i, x, y) for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if len(a) != len(b):
        diferencias.append((min(len(a), len(b)), f"{len(a)} registrados", f"{len(b)} reproducidos"))
    return {"igual": not diferencias, "vital": n_vital, "registrados": registrados,
            "diferencias": diferencias, "version_registro": c["version"], "version_actual": __version__}


def informe(res):
    """Texto para la terminal. Devuelve (ok, texto)."""
    lineas = [f"Reproducidos {res['vital']} segundos de vital."]
    if res["version_registro"] != res["version_actual"]:
        lineas.append(f"Aviso: el registro es de la versión {res['version_registro']} "
                      f"y esta es la {res['version_actual']}.")
    for tipo, d in res["registrados"]:
        if tipo == "evento":
            extra = f" cierra {d['cierra']}" if d.get("cierra") else ""
            lineas.append(f"  {d['id']} {d['regla']}{extra}")
        else:
            lineas.append(f"    recomendación {d['nivel']} para {d['evento']}")
    if res["igual"]:
        lineas.append("Misma decisión.")
    else:
        lineas.append("La decisión NO coincide:")
        for i, x, y in res["diferencias"][:10]:
            lineas.append(f"  #{i}\n    registrado: {x}\n    reproducido: {y}")
    return res["igual"], "\n".join(lineas)


def main():
    p = argparse.ArgumentParser(description="Caja negra de SONQO")
    p.add_argument("orden", choices=["verificar", "reproducir"])
    p.add_argument("archivo")
    args = p.parse_args()
    if args.orden == "verificar":
        ok, _, mensaje = verificar(args.archivo)
        print(mensaje)
        raise SystemExit(0 if ok else 1)
    ok, mensaje = informe(reproducir(args.archivo))
    print(mensaje)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
