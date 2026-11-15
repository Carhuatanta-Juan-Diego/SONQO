"""Servidor de SONQO: FastAPI, WebSocket /ws, las tres páginas y el puente a la voz.

Uso: python -m sonqo.server --config config.yaml [--host 0.0.0.0] [--port 8000]
"""

import argparse
import asyncio
import json
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from sonqo import __version__
from sonqo.bus import Bus
from sonqo.clock import Reloj
from sonqo.config import ErrorConfig, cargar

WEB = Path(__file__).resolve().parent.parent / "web"
PAGINAS = ["estado", "panel", "tierra"]
VOZ_URL = "http://127.0.0.1:8801"   # voz/servidor_voz.py (IndexTTS-2.5); se cambia en config.yaml → voz.url


def _json(tema, datos):
    return json.dumps({"tema": tema, "datos": datos}, ensure_ascii=False)


def mensaje_hola(app):
    cfg, reloj, sistema = app.state.cfg, app.state.reloj, app.state.sistema
    return {"t": reloj.t(), "tm": reloj.tm(), "tripulante": cfg["tripulante"], "modo": cfg["modo"],
            "idioma": cfg["idioma"], "version": __version__, "camara": cfg["camara"].get("fuente"),
            "caja_negra": str(sistema.caja.ruta) if sistema else None,
            "radar_modo": sistema.radar.modo if sistema else None,
            "tripulacion": sistema.fichas() if sistema else [],
            "rutina_s": sistema.rutina_s if sistema else None}


async def _enviar_bus(ws, cola):
    """Reenvía al navegador todo lo que se publica en el bus."""
    while True:
        tema, datos = await cola.get()
        await ws.send_text(_json(tema, datos))


async def _recibir(ws, sistema):
    """Acciones que manda el navegador: {"accion": "...", ...}."""
    while True:
        texto = await ws.receive_text()
        try:
            datos = json.loads(texto)
        except json.JSONDecodeError:
            continue
        error = await sistema.accion(datos) if sistema else "sistema detenido"
        if error:
            await ws.send_text(_json("error", {"mensaje": error, "accion": datos.get("accion")}))


def crear_app(cfg, con_sistema=True):
    @asynccontextmanager
    async def ciclo(app):
        app.state.sistema = None
        if con_sistema:
            from sonqo.sistema import Sistema   # importa OpenCV y MediaPipe
            app.state.sistema = Sistema(cfg, app.state.bus, app.state.reloj)
            await app.state.sistema.iniciar()
            print(f"  caja negra: {app.state.sistema.caja.ruta}")
        yield
        if app.state.sistema:
            await app.state.sistema.detener()

    app = FastAPI(title="SONQO", docs_url=None, redoc_url=None, lifespan=ciclo)
    app.state.cfg = cfg
    app.state.bus = Bus()
    app.state.reloj = Reloj.desde_config(cfg)
    app.mount("/web", StaticFiles(directory=WEB), name="web")

    @app.get("/")
    def raiz():
        return RedirectResponse("/panel")

    for nombre in PAGINAS:
        app.add_api_route(f"/{nombre}", _servir_pagina(nombre), methods=["GET"])

    @app.get("/api/cajas")
    def cajas():
        """Lista de cajas negras guardadas (todas las corridas y todos los tripulantes)."""
        s = app.state.sistema
        return s.listar_cajas() if s else []

    @app.get("/camara.jpg")
    def vista_camara():
        """Último cuadro de la cámara con la zona de piel marcada (solo si está encendida)."""
        s = app.state.sistema
        jpg = s.camara.vista if (s and s.camara.running) else None
        if not jpg:
            return Response(status_code=204)
        return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    # --- la voz de la esfera: puente al servidor de voz local (voz/arrancar.sh) ---------
    voz_cfg = cfg.get("voz") or {}
    voz_url = str(voz_cfg.get("url", VOZ_URL)).rstrip("/")
    voz_activa = bool(voz_cfg.get("activa", True))

    @app.get("/api/voz")
    async def voz_salud():
        """¿Está arriba la voz neuronal? Si no, la esfera usa la voz del navegador."""
        if not voz_activa:
            return {"ok": False, "motivo": "apagada en config.yaml"}
        try:
            return await asyncio.to_thread(_voz_salud, voz_url)
        except (OSError, ValueError) as e:
            return {"ok": False, "motivo": str(e)}

    @app.post("/api/voz/decir")
    async def voz_decir(request: Request):
        """Reenvía el texto a la voz y devuelve el audio en streaming (PCM 16 bit mono 22050 Hz)."""
        if not voz_activa:
            return JSONResponse({"error": "voz apagada"}, status_code=503)
        d = await _cuerpo_json(request)
        if d is None:
            return JSONResponse({"error": "se esperaba un objeto JSON"}, status_code=400)
        # con las cifras pasadas a palabras, un resumen de 4 tripulantes fuera pasa de 600 caracteres
        cuerpo = {"texto": str(d.get("texto", ""))[:2000], "emocion": d.get("emocion", "neutral"),
                  "idioma": d.get("idioma", "es"), "reproducir": False}
        try:
            resp = await asyncio.to_thread(_voz_abrir, voz_url, cuerpo)
        except (OSError, ValueError) as e:
            return JSONResponse({"error": f"voz no disponible: {e}"}, status_code=503)
        return StreamingResponse(_voz_trozos(resp), media_type=resp.headers.get("Content-Type", "audio/L16"),
                                 headers={"Cache-Control": "no-store"})

    @app.post("/api/voz/precargar")
    async def voz_precargar(request: Request):
        """Pide a la voz que deje en caché las frases que SONQO dice más (suenan al instante)."""
        if not voz_activa:
            return JSONResponse({"error": "voz apagada"}, status_code=503)
        d = await _cuerpo_json(request)
        if d is None:
            return JSONResponse({"error": "se esperaba un objeto JSON"}, status_code=400)
        try:
            return await asyncio.to_thread(_voz_post_json, voz_url, "/precargar", d)
        except (OSError, ValueError) as e:
            return JSONResponse({"error": f"voz no disponible: {e}"}, status_code=503)

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        sistema = app.state.sistema
        cola = app.state.bus.suscribir()
        await ws.send_text(_json("hola", mensaje_hola(app)))
        for tema, datos in (sistema.instantanea() if sistema else []):
            await ws.send_text(_json(tema, datos))
        tareas = [asyncio.create_task(_enviar_bus(ws, cola)),
                  asyncio.create_task(_recibir(ws, sistema))]
        try:
            await asyncio.wait(tareas, return_when=asyncio.FIRST_COMPLETED)
        except WebSocketDisconnect:
            pass
        finally:
            for tarea in tareas:
                tarea.cancel()
            app.state.bus.desuscribir(cola)

    return app


async def _cuerpo_json(request):
    """El cuerpo como diccionario, o None si no es un objeto JSON."""
    try:
        d = await request.json()
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


def _voz_salud(url):
    with urllib.request.urlopen(f"{url}/salud", timeout=0.8) as r:
        return json.loads(r.read())


def _voz_post_json(url, ruta, cuerpo):
    req = urllib.request.Request(f"{url}{ruta}", data=json.dumps(cuerpo).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def _voz_abrir(url, cuerpo):
    req = urllib.request.Request(f"{url}/decir", data=json.dumps(cuerpo).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    return urllib.request.urlopen(req, timeout=30)


async def _voz_trozos(resp):
    """Pasa el audio tal como llega. Si el navegador corta, se cierra la conexión con la voz
    (asíncrono a propósito: así la cancelación llega aquí y la voz no queda escribiendo a nadie)."""
    try:
        while True:
            datos = await asyncio.to_thread(resp.read1, 16384)
            if not datos:
                break
            yield datos
    finally:
        # Cerrar espera a que termine la lectura en curso (comparten un candado): si se hiciera
        # aquí, congelaría el servidor entero hasta que la voz mande su próximo trozo.
        asyncio.get_running_loop().run_in_executor(None, resp.close)


def _servir_pagina(nombre):
    def pagina():
        return FileResponse(WEB / f"{nombre}.html")
    pagina.__name__ = f"pagina_{nombre}"
    return pagina


def main():
    p = argparse.ArgumentParser(description="Servidor del prototipo SONQO")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args()
    try:
        cfg = cargar(args.config)
    except (ErrorConfig, OSError) as e:
        raise SystemExit(f"No se pudo cargar {args.config}: {e}")
    print(f"SONQO {__version__} · modo {cfg['modo']} · {cfg['tripulante']} · cámara: {cfg['camara'].get('fuente')}")
    for nombre in PAGINAS:
        print(f"  http://localhost:{args.port}/{nombre}")
    uvicorn.run(crear_app(cfg), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
