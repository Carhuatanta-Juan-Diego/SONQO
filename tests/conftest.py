import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
# Permite `pytest` desde la raíz sin instalar el paquete.
sys.path.insert(0, str(RAIZ))

from sonqo.config import cargar  # noqa: E402


@pytest.fixture
def cfg():
    """config.yaml del repositorio en modo demo."""
    return cargar(RAIZ / "config.yaml")


def vital(t, pulso=68.0, resp=15.0, temp=36.6, coinciden=True, movimiento=0.5, tm0=18501120):
    """Un `vital` sintético con dos fuentes de pulso."""
    pf = {"camara_rgb": pulso, "radar": pulso} if coinciden else {"camara_rgb": 68.0, "radar": pulso}
    return {"t": float(t), "tm": tm0 + int(t), "tripulante": "MS-2", "pulso": pulso, "resp": resp,
            "temp_piel": temp, "fuentes": {"pulso": list(pf)}, "por_fuente": {"pulso": pf},
            "coinciden": {"pulso": True if coinciden else False}, "sim": {}, "movimiento": movimiento}
