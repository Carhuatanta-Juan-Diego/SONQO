"""Voz de SONQO: servidor de voz en tiempo real (IndexTTS-2.5, "config E").

Copia propia para SONQO: modelo en voz/index-tts, voz de referencia en voz/voces, caché en
voz/cache_voz. No usa ningún otro proyecto.

Arranque:  voz/arrancar.sh            (API en http://127.0.0.1:8801, sin consola)
A mano:    uv run --directory voz/index-tts --no-sync python ../servidor_voz.py --http 8801

API:  POST /decir  {"texto": "...", "emocion": "neutral|preocupacion", "idioma": "es|en",
                    "reproducir": false}
        reproducir=false -> audio en streaming (PCM 16 bit mono 22050 Hz): lo usa la esfera
        reproducir=true  -> suena en los parlantes de esta máquina, responde JSON con tiempos
      GET  /salud

Trucos de latencia:
  1. Caché en disco por (idioma, emoción, texto): las frases fijas suenan en ~0 s.
  2. La primera frase se corta en su primera coma para que el primer sonido salga antes.
  3. Cada trozo sale apenas se genera, mientras se genera el siguiente.
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RAIZ)
import numpy as np  # noqa: E402
import torch  # noqa: E402
from motor import IndexTTS2, descargar_w2v, reducir_w2v_bert  # noqa: E402

SR = 22050
VOZ = os.path.join(RAIZ, "voces", "timbre_7s.wav")
CACHE = os.path.join(RAIZ, "cache_voz")

# Emoción -> parámetros extra de infer(). Decidido de oído en las pruebas de voz (2026-11-13):
# neutral sale bien del propio texto; la preocupación, mejor con clip actuado.
# SONQO usa "preocupacion" solo para avisar que un tripulante salió de su normal.
EMOCIONES = {
    "neutral": {},
    "preocupacion": {"emo_audio_prompt": os.path.join(RAIZ, "voces", "emo_preocupacion.wav"),
                     "emo_alpha": 0.8},
}
IDIOMAS = {"es": "ES", "en": "EN"}

# Frases fijas de SONQO que se generan al arrancar (si faltan) para responder en 0 s.
# Con tildes, signos y punto final: el modelo lee las letras tal cual.
FRASES_FIJAS = {
    "es": ["Listo.", "Entendido.", "Un momento.", "No entendí, ¿puedes repetirlo?",
           "Hola, soy Sonko.", "Eso solo lo decide el tripulante en Mi estado.",
           "Verificando la caja negra.", "Atención,"],
    "en": ["Done.", "Understood.", "One moment.", "Hello, I am Sonko.", "Attention,"],
}


CAR_S = 13.0          # caracteres por segundo de audio (medido: 12–13,5)
GEN_FIJO, GEN_RTF = 0.35, 0.40   # espera por trozo ≈ 0,35 s + 0,4 × s de audio
TOLERANCIA = 0.25     # silencio admisible en una coma (suena a pausa natural)


# Pausa que se deja tras cada trozo según su signo final (s). Sin signo: casi nada.
PAUSA = {",": 0.16, ";": 0.22, ":": 0.22, ".": 0.38, "?": 0.38, "!": 0.38, "…": 0.38}


NIVEL = 3000.0        # volumen (RMS de la parte hablada) al que se lleva cada trozo


def _tramos(pcm):
    """Tramos con voz, en ventanas de 10 ms: lista de (inicio, fin) separados por ≥ 0,2 s de silencio."""
    n = SR // 100
    env = np.abs(pcm[: len(pcm) // n * n].astype(np.float32)).reshape(-1, n).max(axis=1)
    activo = np.where(env > max(400.0, 0.03 * env.max()))[0] if len(env) else []
    tramos = []
    for k in activo:
        if tramos and k - tramos[-1][1] <= 20:
            tramos[-1][1] = k
        else:
            tramos.append([k, k])
    return tramos


def _sin_cola(tramos, texto):
    """El modelo a veces agrega un sonido suelto tras una pausa al final del trozo (medido en la
    caché: 'Uf,' traía 0,33 s de más; 'Hola,', 'Mmm,', 'Pues,' un chasquido). Se descarta: un
    tramo final de menos de 0,15 s, o cualquier tramo extra cuando el texto es una sola palabra
    que ya sonó completa."""
    tramos = list(tramos)
    una = " " not in texto.strip()
    while len(tramos) > 1:
        dur = tramos[-1][1] - tramos[-1][0] + 1
        antes = sum(f - i + 1 for i, f in tramos[:-1])
        if dur < 15 or (una and antes >= 60 * len(texto.strip()) / CAR_S):
            tramos.pop()
        else:
            break
    return tramos


def calidad(pcm, texto):
    """Problemas de una toma (0 = limpia): saturación, sonidos de más, duración rara."""
    tramos = _tramos(pcm)
    if not tramos:
        return 99
    voz = sum(f - i + 1 for i, f in _sin_cola(tramos, texto)) / 100
    esperado = len(texto.strip()) / CAR_S
    return (3 * (np.abs(pcm.astype(np.int32)).max() >= 32700)
            + 2 * (len(tramos) - len(_sin_cola(tramos, texto)))
            + 2 * (not 0.6 * esperado <= voz <= 1.8 * esperado + 0.15))


def recortar(pcm, texto):
    """Quita el silencio que el modelo deja al inicio y al final de cada trozo (medido: hasta
    0,35 s y 0,5 s), los sonidos sueltos del final, iguala el volumen entre trozos (cada toma
    sale a un volumen distinto: picos de 13 900 a 32 768) y pone la pausa que pide el signo
    final. Sin esto, los trozos pegados suenan como un audio mal editado."""
    n = SR // 100                                   # ventanas de 10 ms
    tramos = _sin_cola(_tramos(pcm), texto)
    if len(pcm) < 4 * n or not tramos:
        return pcm
    # 120 ms antes: una vocal inicial suave («eme ese dos») queda bajo el umbral y con 30 ms se oía «mm»
    ini = max(0, tramos[0][0] * n - SR * 120 // 1000)
    fin = min(len(pcm), (tramos[-1][1] + 1) * n + SR * 60 // 1000)
    voz = pcm[ini:fin].astype(np.float32)
    hablado = np.concatenate([pcm[i * n:(f + 1) * n] for i, f in tramos]).astype(np.float32)
    rms = float(np.sqrt(np.mean(hablado ** 2))) or 1.0
    g = min(max(NIVEL / rms, 0.4), 2.5)
    voz *= min(g, 30000.0 / max(1.0, float(np.abs(voz).max())))
    r = min(SR * 8 // 1000, len(voz) // 2)          # rampas de 8 ms: sin chasquidos
    voz[:r] *= np.linspace(0, 1, r)
    voz[-r:] *= np.linspace(1, 0, r)
    pausa = PAUSA.get(texto.strip()[-1:], 0.03)
    return np.concatenate([voz.astype(np.int16), np.zeros(int(SR * pausa), np.int16)])


def trocear(texto, min_corte=12, max_primero=30):
    """Divide en frases y, dentro de cada frase, en sus comas, juntando cláusulas
    mientras el trozo alcance a generarse antes de que termine de sonar lo anterior.
    Así el primer sonido llega pronto y no quedan silencios largos a mitad de frase."""
    frases = [f.strip() for f in re.split(r"(?<=[.!?…])\s+", texto.strip()) if f.strip()]
    trozos, t_gen, t_fin = [], 0.0, 0.0   # reloj simulado: fin de generación / de sonido

    def emitir(trozo):
        nonlocal t_gen, t_fin
        dur = len(trozo) / CAR_S
        t_gen += GEN_FIJO + GEN_RTF * dur
        t_fin = max(t_fin, t_gen) + dur
        trozos.append(trozo)

    for n, frase in enumerate(frases):
        piezas = []
        for p in re.split(r"(?<=[,;:])\s+", frase):
            if piezas and (len(p) < min_corte or (len(piezas[-1]) < 4)):
                piezas[-1] += " " + p      # cláusulas mínimas no se separan
            else:
                piezas.append(p)
        if n == 0 and len(frase) <= max_primero:
            piezas = [frase]
        actual = piezas[0]
        for p in piezas[1:]:
            junto = actual + " " + p
            listo = t_gen + GEN_FIJO + GEN_RTF * len(junto) / CAR_S
            if trozos and listo <= t_fin + TOLERANCIA:
                actual = junto             # cabe: mejor entonación sin corte
            else:
                emitir(actual)
                actual = p
        emitir(actual)
    return trozos


class Voz:
    def __init__(self):
        t = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            self.tts = IndexTTS2(cfg_path="checkpoints/config.yaml", model_dir="checkpoints", use_bf16=True)
        os.makedirs(CACHE, exist_ok=True)
        reducir_w2v_bert(self.tts)
        descargar_w2v(self.tts)
        self._w2v_en_disco()
        self.tts.diffusion_steps, self.tts.s2mel_dtype = 10, torch.bfloat16
        self.gpu = threading.Lock()
        self.ultimo_uso = 0.0              # cuándo se generó o entregó el último trozo de una frase en vivo
        self.turno = 0                     # sube con cada frase pedida: gana la más nueva
        self.pendientes = queue.Queue()    # (texto, idioma) que SONQO pidió dejar en caché
        threading.Thread(target=self._precalentar, daemon=True).start()
        self._generar("Hola, soy Sonko.", "neutral")  # calentamiento
        print(f"Modelo listo en {time.perf_counter() - t:.1f} s")

    def _w2v_en_disco(self):
        """Guarda en disco lo que w2v-bert saca de cada clip de voz (timbre, emoción). Sin esto,
        la primera frase con cada clip sube w2v-bert a la GPU (1,1 GB, el pico de 4,08 GB). El
        resultado es el mismo tensor."""
        interno, tts = self.tts.get_emb, self.tts

        def get_emb(input_features, attention_mask):
            datos = input_features.detach().float().cpu().numpy().tobytes()
            ruta = os.path.join(CACHE, f"w2v_{hashlib.sha1(datos).hexdigest()[:16]}.pt")
            if os.path.exists(ruta):
                return torch.load(ruta, map_location=tts.device)
            r = interno(input_features, attention_mask)
            torch.save(r.cpu(), ruta)
            return r

        tts.get_emb = get_emb

    @staticmethod
    def _guardar(ruta, pcm):
        """Escribe la caché de una vez: primero a un temporal y luego lo reemplaza."""
        tmp = ruta + ".tmp"
        with open(tmp, "wb") as f:
            np.save(f, pcm)
        os.replace(tmp, ruta)

    @staticmethod
    def _ruta(texto, emocion, idioma="es"):
        clave = hashlib.sha1(f"{idioma}|{emocion}|{texto.strip().lower()}".encode()).hexdigest()[:16]
        return os.path.join(CACHE, f"{clave}.npy")

    def _generar(self, texto, emocion, idioma="es"):
        with self.gpu, contextlib.redirect_stdout(io.StringIO()):
            _, wav = self.tts.infer(spk_audio_prompt=VOZ, text=texto, lang=IDIOMAS[idioma], output_path=None,
                                    **EMOCIONES[emocion])
        return np.ascontiguousarray(wav.reshape(-1), dtype=np.int16)

    def trozo(self, texto, emocion, idioma="es", guardar=True):
        """Devuelve (pcm int16, vino_de_cache)."""
        ruta = self._ruta(texto, emocion, idioma)
        if os.path.exists(ruta):
            return np.load(ruta), True
        pcm = self._generar(texto, emocion, idioma)
        if guardar:
            self._guardar(ruta, pcm)
        return pcm, False

    def precargar(self, tomas=6):
        """Deja en caché una toma limpia de cada frase fija. Las palabras sueltas ("Uf,") salen
        mal a menudo (sonido de más, saturadas): se repite la toma y se queda la mejor."""
        rehechas = 0
        for idioma, f in [(i, f) for i, fs in FRASES_FIJAS.items() for f in fs]:
            ruta = self._ruta(f, "neutral", idioma)
            mejor = np.load(ruta) if os.path.exists(ruta) else None
            nota = calidad(mejor, f) if mejor is not None else 99
            if nota == 0:
                continue
            for _ in range(tomas):
                pcm = self._generar(f, "neutral", idioma)
                if calidad(pcm, f) < nota:
                    mejor, nota = pcm, calidad(pcm, f)
                if nota == 0:
                    break
            if mejor is not None:
                self._guardar(ruta, mejor)
            rehechas += 1
            if nota:
                print(f"Caché: {f!r} quedó con defectos (nota {nota}) tras {tomas} tomas")
        if rehechas:
            print(f"Caché: rehechas {rehechas} frases fijas")

    def partes(self, texto, emocion, idioma):
        """Trozos a decir. Una frase completa que ya está en caché va entera (suena al instante);
        las demás se trocean en sus comas."""
        res = []
        for frase in [f.strip() for f in re.split(r"(?<=[.!?…])\s+", texto.strip()) if f.strip()]:
            if os.path.exists(self._ruta(frase, emocion, idioma)):
                res.append(frase)
            else:
                res.extend(trocear(frase))
        return res

    def decir(self, texto, emocion="neutral", idioma="es"):
        """Generador: produce (pcm, info) por trozo, en orden."""
        if emocion not in EMOCIONES:
            raise ValueError(f"emoción desconocida: {emocion} (opciones: {', '.join(EMOCIONES)})")
        if idioma not in IDIOMAS:
            raise ValueError(f"idioma desconocido: {idioma} (opciones: {', '.join(IDIOMAS)})")
        t0 = time.perf_counter()
        self.turno += 1
        mio = self.turno
        for i, parte in enumerate(self.partes(texto, emocion, idioma)):
            if self.turno != mio:
                return   # llegó una frase más nueva (SONQO cortó esta): no se gasta la GPU en ella
            self.ultimo_uso = time.monotonic()
            # Solo viven en caché las frases fijas y las que SONQO precalienta: una toma mala no se repite.
            pcm, cache = self.trozo(parte, emocion, idioma, guardar=False)
            pcm = recortar(pcm, parte)
            self.ultimo_uso = time.monotonic()
            yield pcm, {"trozo": i, "texto": parte, "cache": cache,
                        "listo_s": round(time.perf_counter() - t0, 3),
                        "audio_s": round(len(pcm) / SR, 2)}

    def pedir_cache(self, frases, idioma, emocion="neutral"):
        """SONQO manda las frases que más dice; se generan en segundo plano. Devuelve cuántas faltan."""
        faltan = 0
        for f in frases:
            f = str(f).strip()
            if f and len(f) <= 300 and not os.path.exists(self._ruta(f, emocion, idioma)):
                self.pendientes.put((f, idioma, emocion))
                faltan += 1
        return faltan

    def _precalentar(self, tomas=3):
        """Genera las frases pedidas solo cuando la voz lleva 1,5 s sin uso en vivo, y guarda la mejor toma.
        (Antes contaba frases abiertas: una frase cortada a la mitad lo dejaba esperando para siempre.)"""
        while True:
            f, idioma, emocion = self.pendientes.get()
            try:
                self._precalentar_una(f, idioma, emocion, tomas)
            except Exception as e:   # una frase que falla (p. ej. sin memoria en la GPU) no detiene las demás
                print(f"Caché: no se pudo generar {f!r}: {e!r}", flush=True)
            if self.pendientes.empty():
                print("Caché: frases de SONQO listas", flush=True)

    def _precalentar_una(self, f, idioma, emocion, tomas):
        ruta = self._ruta(f, emocion, idioma)
        if os.path.exists(ruta):
            return
        mejor, nota = None, 99
        for _ in range(tomas):
            while time.monotonic() - self.ultimo_uso < 1.5:
                time.sleep(0.2)
            pcm = self._generar(f, emocion, idioma)
            if calidad(pcm, f) < nota:
                mejor, nota = pcm, calidad(pcm, f)
            if nota == 0:
                break
        if mejor is not None:
            self._guardar(ruta, mejor)


class Parlante:
    """Reproduce PCM por los parlantes sin cortes, vía un proceso aplay persistente."""

    def __init__(self, mudo=False):
        self.mudo = mudo
        self.cola = queue.Queue()
        self.proc = None
        threading.Thread(target=self._bucle, daemon=True).start()

    def _bucle(self):
        while True:
            pcm = self.cola.get()
            if self.mudo:
                continue
            try:
                if self.proc is None or self.proc.poll() is not None:
                    self.proc = subprocess.Popen(
                        ["aplay", "-q", "-t", "raw", "-f", "S16_LE", "-r", str(SR), "-c", "1"],
                        stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
                self.proc.stdin.write(pcm.tobytes())
                self.proc.stdin.flush()
            except (BrokenPipeError, OSError) as e:
                print(f"[parlante] error de audio: {e}")
                self.proc = None

    def poner(self, pcm):
        self.cola.put(pcm)


def hablar(voz, parlante, texto, emocion, idioma="es"):
    """Dice el texto por los parlantes y devuelve los tiempos."""
    infos, fin = [], 0.0
    for pcm, info in voz.decir(texto, emocion, idioma):
        parlante.poner(pcm)
        # silencio antes de este trozo: lo que tardó de más respecto al fin del anterior
        info["hueco_s"] = round(max(0.0, info["listo_s"] - fin), 2) if infos else 0.0
        fin = max(fin, info["listo_s"]) + info["audio_s"]
        infos.append(info)
    return {"primer_sonido_s": infos[0]["listo_s"] if infos else None,
            "total_s": infos[-1]["listo_s"] if infos else None,
            "audio_s": round(sum(i["audio_s"] for i in infos), 2), "trozos": infos}


def servir_http(voz, parlante, puerto, host="127.0.0.1"):
    class H(BaseHTTPRequestHandler):
        timeout = 20   # si el otro lado deja de leer, la escritura se corta en vez de quedar colgada

        def log_message(self, *a):
            pass

        def _json(self, codigo, obj):
            cuerpo = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def do_GET(self):
            if self.path == "/salud":
                self._json(200, {"ok": True, "motor": "IndexTTS-2.5", "emociones": list(EMOCIONES),
                                 "idiomas": list(IDIOMAS), "sr": SR})
            else:
                self._json(404, {"error": "no existe"})

        def do_POST(self):
            if self.path == "/precargar":
                try:
                    d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                    idioma, emocion = d.get("idioma", "es"), d.get("emocion", "neutral")
                    if idioma not in IDIOMAS or emocion not in EMOCIONES or not isinstance(d.get("frases"), list):
                        raise ValueError("frases, emoción o idioma no válidos")
                except (ValueError, json.JSONDecodeError) as e:
                    return self._json(400, {"error": str(e)})
                return self._json(200, {"faltan": voz.pedir_cache(d["frases"][:400], idioma, emocion)})
            if self.path != "/decir":
                return self._json(404, {"error": "no existe"})
            try:
                d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                texto, emocion, idioma = d["texto"], d.get("emocion", "neutral"), d.get("idioma", "es")
                if emocion not in EMOCIONES or idioma not in IDIOMAS or not texto.strip():
                    raise ValueError("texto vacío, emoción o idioma desconocido")
            except (ValueError, KeyError, json.JSONDecodeError) as e:
                return self._json(400, {"error": str(e)})
            if d.get("reproducir", True):
                return self._json(200, hablar(voz, parlante, texto, emocion, idioma))
            self.send_response(200)
            self.send_header("Content-Type", f"audio/L16; rate={SR}; channels=1")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            try:
                for pcm, _ in voz.decir(texto, emocion, idioma):
                    datos = pcm.tobytes()
                    self.wfile.write(f"{len(datos):X}\r\n".encode() + datos + b"\r\n")
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
            except OSError:
                pass   # la esfera cortó (empezó otra frase) o dejó de leer: se deja de generar

    srv = ThreadingHTTPServer((host, puerto), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"Voz de SONQO en http://{host}:{puerto}  (POST /decir, GET /salud)", flush=True)
    return srv


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--http", type=int, metavar="PUERTO", help="abrir también la API HTTP (SONQO usa 8801)")
    p.add_argument("--host", default="127.0.0.1", help="interfaz de la API (solo esta máquina por defecto)")
    p.add_argument("--mudo", action="store_true", help="no reproducir (para pruebas)")
    p.add_argument("--sin-consola", action="store_true", help="solo API, sin leer del teclado")
    a = p.parse_args()

    voz = Voz()
    voz.precargar()
    parlante = Parlante(mudo=a.mudo)
    if a.http:
        servir_http(voz, parlante, a.http, a.host)
    if a.sin_consola:
        threading.Event().wait()

    print("Escribe una frase (o /preocupacion frase). Ctrl+D para salir.")
    for linea in sys.stdin:
        linea = linea.strip()
        if not linea:
            continue
        emocion = "neutral"
        m = re.match(r"/(\w+)\s+(.*)", linea)
        if m:
            emocion, linea = m.group(1), m.group(2)
        try:
            r = hablar(voz, parlante, linea, emocion)
        except ValueError as e:
            print(f"  {e}")
            continue
        partes = " | ".join(f"{t['listo_s']:.2f}s{'*' if t['cache'] else ''}"
                            + (f" (silencio {t['hueco_s']:.2f}s)" if t["hueco_s"] >= 0.05 else "")
                            for t in r["trozos"])
        print(f"  primer sonido {r['primer_sonido_s']:.2f} s · total {r['total_s']:.2f} s "
              f"para {r['audio_s']:.1f} s de audio · trozos: {partes}   (* = caché)")


if __name__ == "__main__":
    main()
