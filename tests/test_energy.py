import asyncio

from sonqo.energy import Energia, Senales
from sonqo.sources.base import Fuente


class FuenteFalsa(Fuente):
    def __init__(self, nombre):
        super().__init__(reloj=None, emitir=None)
        self.nombre = nombre
        self.abierta = False

    async def _abrir(self):
        self.abierta = True

    async def _cerrar(self):
        self.abierta = False


def _fuentes():
    return {n: FuenteFalsa(n) for n in ("radar", "termica", "camara_rgb", "profundidad")}


def test_secuencia_e0_e1_e2_e0(cfg):
    async def correr():
        fuentes = _fuentes()
        e = Energia(cfg, fuentes)
        await e.aplicar()
        estados = []
        e1, e2 = cfg["energia"]["e1_duracion_s"], cfg["energia"]["e2_duracion_s"]
        for t in range(1, 40):
            desvio = 5 <= t < 5 + e1 + 1          # el radar se desvía unos segundos
            if e.paso(t, Senales(radar_desvio=desvio)):
                await e.aplicar()
                estados.append((t, e.estado, e.motivo))
            assert fuentes["camara_rgb"].abierta == (e.estado in ("E2", "E3"))
        return estados

    estados = asyncio.run(correr())
    assert [s for _, s, _ in estados[:3]] == ["E1", "E2", "E0"]
    assert estados[0][2] == "desvio_radar"
    assert estados[1][2] == "desvio_radar"
    assert estados[2][2] == "vuelta_al_normal"
    assert estados[1][0] - estados[0][0] == cfg["energia"]["e1_duracion_s"]
    assert estados[2][0] - estados[1][0] == cfg["energia"]["e2_duracion_s"]


def test_verificacion_periodica(cfg):
    e = Energia(cfg)
    periodo = cfg["energia"]["e1_periodo_s"]
    for t in range(1, periodo + 1):
        e.paso(t, Senales())
    assert e.estado == "E1" and e.motivo == "verificacion_periodica"


def test_wh_coinciden_con_la_integral_de_los_vatios(cfg):
    e = Energia(cfg)
    esperado = 0.0
    for t in range(1, 200):
        esperado += e.vatios() * 1 / 3600     # vatios del segundo que termina
        e.paso(t, Senales(radar_desvio=60 <= t < 70, episodio=100 <= t < 130))
    assert abs(e.wh - esperado) < 1e-9


def test_camara_cerrada_en_e0_y_vatios_del_modelo(cfg):
    async def correr():
        fuentes = _fuentes()
        e = Energia(cfg, fuentes)
        await e.aplicar()
        return e, fuentes
    e, fuentes = asyncio.run(correr())
    assert e.estado == "E0"
    assert not fuentes["camara_rgb"].abierta and not fuentes["profundidad"].abierta
    assert fuentes["radar"].abierta
    assert round(e.vatios("E0"), 1) == 2.1
    assert round(e.vatios("E1"), 1) == 2.5
    assert round(e.vatios("E2"), 1) == 21.5
    assert round(e.vatios("E3"), 1) == 61.5


def test_calibracion_y_mantener_e2_sostienen_e2(cfg):
    e = Energia(cfg)
    e.paso(1, Senales(calibrando=True))
    assert (e.estado, e.motivo) == ("E2", "calibracion")
    e.mantener_e2 = True
    for t in range(2, 100):
        e.paso(t, Senales())
    assert e.estado == "E2"
    e.paso(100, Senales(episodio=True))
    assert e.estado == "E3"


def test_soltar_mantener_e2_apaga_en_el_siguiente_segundo(cfg):
    e = Energia(cfg)
    e.mantener_e2 = True
    e.paso(1, Senales())
    assert e.estado == "E2"
    e.mantener_e2 = False
    e.paso(2, Senales())
    assert (e.estado, e.motivo) == ("E0", "vuelta_al_normal")
