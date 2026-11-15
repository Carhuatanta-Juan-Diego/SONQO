import random

import pytest

from sonqo.link.t30 import FIELDS, VECTOR_HEX, decode, encode, vector_prueba


def test_vector_de_prueba_byte_a_byte():
    raw = encode(vector_prueba())
    assert len(raw) == 30
    assert raw.hex(" ") == VECTOR_HEX


def test_vector_decodifica_igual():
    card = vector_prueba()
    out, crc_ok = decode(encode(card))
    assert crc_ok
    for nombre, _, _, _ in FIELDS[:-1]:
        assert out[nombre] == pytest.approx(card[nombre])


def _tarjeta_aleatoria(rng):
    card = {}
    for nombre, n, signo, escala in FIELDS[:-1]:
        if signo:
            v = rng.randrange(-(1 << (n - 1)), 1 << (n - 1))
        else:
            v = rng.randrange(0, 1 << n)
        card[nombre] = round(v * escala, 3)
    return card


def test_ida_y_vuelta_1000_tarjetas():
    rng = random.Random(7)
    for _ in range(1000):
        card = _tarjeta_aleatoria(rng)
        raw = encode(card)
        out, crc_ok = decode(raw)
        assert crc_ok
        assert out == card
        assert encode(out) == raw


def test_un_bit_cambiado_falla_el_crc():
    raw = bytearray(encode(vector_prueba()))
    for i in range(28 * 8):
        alterado = bytearray(raw)
        alterado[i // 8] ^= 1 << (i % 8)
        _, crc_ok = decode(bytes(alterado))
        assert not crc_ok


@pytest.mark.parametrize("campo, valor", [("seq", 256), ("severity", 8), ("d_hr", 300), ("d_rr", -40),
                                           ("crew", -1)])
def test_valor_fuera_de_rango_da_error(campo, valor):
    card = vector_prueba()
    card[campo] = valor
    with pytest.raises(ValueError):
        encode(card)
