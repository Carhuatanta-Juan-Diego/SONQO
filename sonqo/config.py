"""Carga y valida config.yaml.

Los valores escritos como {demo: x, real: y} se resuelven según `modo`,
así el resto del código solo ve un número.
"""

import copy
import re

import yaml

SECCIONES = ["mision", "camara", "profundidad", "radar_sim", "energia",
             "gemelo", "fusion", "motor", "enlace"]
TRIPULANTES = ["MS-1", "MS-2", "MS-3", "MS-4"]


class ErrorConfig(ValueError):
    """La configuración no es válida."""


def _es_por_modo(valor):
    """True si el valor es un diccionario {demo: ..., real: ...}."""
    return isinstance(valor, dict) and set(valor) == {"demo", "real"}


def resolver_modo(valor, modo):
    """Reemplaza recursivamente cada {demo, real} por el valor del modo."""
    if _es_por_modo(valor):
        return valor[modo]
    if isinstance(valor, dict):
        return {k: resolver_modo(v, modo) for k, v in valor.items()}
    return valor


def validar(crudo):
    """Revisa lo mínimo para que el sistema arranque; lanza ErrorConfig si falla."""
    if not isinstance(crudo, dict):
        raise ErrorConfig("config.yaml vacío o mal formado")
    if crudo.get("modo") not in ("demo", "real"):
        raise ErrorConfig("modo debe ser 'demo' o 'real'")
    if crudo.get("idioma") not in ("es", "en"):
        raise ErrorConfig("idioma debe ser 'es' o 'en'")
    if crudo.get("tripulante") not in TRIPULANTES:
        raise ErrorConfig("tripulante debe ser uno de " + ", ".join(TRIPULANTES))
    faltan = [s for s in SECCIONES if s not in crudo]
    if faltan:
        raise ErrorConfig("faltan secciones: " + ", ".join(faltan))
    if crudo["camara"].get("fuente", "webcam") not in ("webcam", "video", "replay"):
        raise ErrorConfig("camara.fuente debe ser webcam, video o replay")
    if crudo["profundidad"].get("tipo") not in ("replay", "realsense"):
        raise ErrorConfig("profundidad.tipo debe ser replay o realsense")
    if crudo["radar_sim"].get("modo") not in ("normal", "desvio", "falla"):
        raise ErrorConfig("radar_sim.modo debe ser normal, desvio o falla")
    hora = str(crudo["mision"].get("hora_inicio", ""))
    if not re.fullmatch(r"\d{2}:\d{2}:\d{2}", hora):
        raise ErrorConfig("mision.hora_inicio debe tener el formato HH:MM:SS")
    if not isinstance(crudo["mision"].get("dia_inicio"), int):
        raise ErrorConfig("mision.dia_inicio debe ser un entero")


def cargar(ruta="config.yaml"):
    """Lee el archivo, lo valida y devuelve la configuración resuelta.

    La copia original (sin resolver) queda en cfg["_crudo"] para la caja negra.
    """
    with open(ruta, encoding="utf-8") as f:
        crudo = yaml.safe_load(f)
    validar(crudo)
    cfg = resolver_modo(copy.deepcopy(crudo), crudo["modo"])
    cfg["_crudo"] = crudo
    cfg["_ruta"] = str(ruta)
    return cfg
