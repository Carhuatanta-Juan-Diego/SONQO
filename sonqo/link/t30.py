"""Tarjeta T-30 (versión 1): 28 campos, 239 bits útiles, 30 bytes.

`encode` y `decode` son la implementación de referencia del manual (sección 7.7)
y reproducen el vector de prueba byte a byte. No tocar sin correr test_t30.py.
"""

import hashlib
import zlib

FIELDS = [  # nombre, bits, con signo, escala
    ("ver", 3, False, 1), ("crew", 3, False, 1), ("t_mission_s", 27, False, 1), ("seq", 8, False, 1),
    ("event", 12, False, 1), ("severity", 3, False, 1), ("confidence", 4, False, 1), ("onset_s", 8, False, 2),
    ("d_hr", 8, True, 2), ("d_rr", 6, True, 1), ("d_temp", 6, True, 0.1), ("spo2_contact", 7, False, 1),
    ("sys_bp", 8, False, 1), ("dia_bp", 7, False, 1), ("avpu", 2, False, 1),
    ("protocol", 10, False, 1), ("step", 5, False, 1), ("autonomy", 3, False, 1),
    ("drug1", 8, False, 1), ("dose1", 6, False, 1), ("drug2", 8, False, 1), ("dose2", 6, False, 1),
    ("rad_dose", 8, False, 0.01), ("need_decision", 1, False, 1), ("question", 8, False, 1),
    ("sample_id", 16, False, 1), ("bb_hash", 32, False, 1), ("crc", 16, False, 1)]

TAMANO = 30

# Tabla local de eventos (ilustrativa, no clínica).
EVENTOS = {1187: "taquiarritmia"}
EVENTO_R1 = 1187

# Datos fijos para la pantalla Tierra (sección 7.7).
JSON_EQUIVALENTE_BYTES = 587


def encode(card):
    bits, nbits = 0, 0
    for name, n, signed, sc in FIELDS[:-1]:
        v = int(round(card[name] / sc))
        if signed:
            # Agregado a la referencia: con signo también falla si no cabe
            # (la máscara sola lo envolvería en silencio).
            if not -(1 << (n - 1)) <= v < (1 << (n - 1)):
                raise ValueError(name)
            v &= (1 << n) - 1
        if not 0 <= v < (1 << n):
            raise ValueError(name)
        bits = (bits << n) | v
        nbits += n
    pbytes = (nbits + 7) // 8
    raw = (bits << (pbytes * 8 - nbits)).to_bytes(pbytes, "big")
    return raw + (zlib.crc32(raw) & 0xFFFF).to_bytes(2, "big")


def decode(raw):
    crc_ok = (zlib.crc32(raw[:-2]) & 0xFFFF) == int.from_bytes(raw[-2:], "big")
    bits, pos, out = int.from_bytes(raw[:-2], "big"), (len(raw) - 2) * 8, {}
    for name, n, signed, sc in FIELDS[:-1]:
        pos -= n
        v = (bits >> pos) & ((1 << n) - 1)
        if signed and v >= (1 << (n - 1)):
            v -= (1 << n)
        out[name] = round(v * sc, 3)
    return out, crc_ok


def vector_prueba():
    """Tarjeta del caso simulado de MS-2, día 214, 03:13 (sección 7.7)."""
    bb_hash = int(hashlib.sha256(b"caja-negra-segmento-000214-0312").hexdigest()[:8], 16)
    return {"ver": 1, "crew": 2, "t_mission_s": 214 * 86400 + 3 * 3600 + 13 * 60, "seq": 41,
            "event": 1187, "severity": 5, "confidence": 13, "onset_s": 46,
            "d_hr": 72, "d_rr": 7, "d_temp": 0.2, "spo2_contact": 94, "sys_bp": 104, "dia_bp": 66,
            "avpu": 0, "protocol": 312, "step": 4, "autonomy": 3, "drug1": 0, "dose1": 0,
            "drug2": 0, "dose2": 0, "rad_dose": 0, "need_decision": 1, "question": 17,
            "sample_id": 5821, "bb_hash": bb_hash}


VECTOR_HEX = ("28 8d 27 1e 14 a5 1d d1 72 41 c2 bc d1 08 4e 08 c0 00 00 00 "
              "02 22 2d 7a fe a6 e0 dc 1e d9")


def tiempo_envio_s(nbytes, copias, tasa_bps):
    """Segundos que tarda en salir el mensaje completo con todas sus copias."""
    return nbytes * 8 * copias / tasa_bps


def _saturar(valor, minimo, maximo):
    """Satura a propósito (no en silencio): devuelve el valor y si se saturó."""
    v = min(max(valor, minimo), maximo)
    return v, v != valor


def armar_tarjeta(evento, t, tm, seq, bb_hash_hex, sample_id, autonomia):
    """Arma la T-30 a partir de un evento del motor.

    Los desvíos que no caben en sus bits se saturan al extremo y se informan en
    `saturados` (el codificador nunca recorta: si algo no cabe, falla).
    Los campos clínicos sin dato van en 0, como dice la sección 12 del manual.
    """
    d = evento["desvio"]
    saturados = []
    campos = {
        "onset_s": (t - evento["inicio_t"], 0, 510),
        "d_hr": (d.get("pulso") or 0.0, -256, 254),
        "d_rr": (d.get("resp") or 0.0, -32, 31),
        "d_temp": (d.get("temp_piel") or 0.0, -3.2, 3.1),
    }
    valores = {}
    for nombre, (v, lo, hi) in campos.items():
        valores[nombre], sat = _saturar(v, lo, hi)
        if sat:
            saturados.append(nombre)
    card = {
        "ver": 1, "crew": int(evento["tripulante"].split("-")[1]), "t_mission_s": int(tm),
        "seq": seq % 256, "event": EVENTO_R1, "severity": int(evento["gravedad"]),
        "confidence": int(round(15 * evento["confianza"])),
        "onset_s": valores["onset_s"], "d_hr": valores["d_hr"], "d_rr": valores["d_rr"],
        "d_temp": valores["d_temp"], "spo2_contact": 0, "sys_bp": 0, "dia_bp": 0, "avpu": 0,
        "protocol": 0, "step": 0, "autonomy": autonomia, "drug1": 0, "dose1": 0, "drug2": 0,
        "dose2": 0, "rad_dose": 0, "need_decision": 1, "question": 0,
        "sample_id": sample_id & 0xFFFF, "bb_hash": int(bb_hash_hex[:8], 16),
    }
    return card, saturados
