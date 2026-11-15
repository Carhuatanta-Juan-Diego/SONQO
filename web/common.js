// Código común de las tres páginas: idioma, reloj de misión, WebSocket y gráficos.
// Sin dependencias externas.

const SONQO = (() => {
  const params = new URLSearchParams(location.search);
  const langForzado = params.get("lang");
  let lang = langForzado || "es";
  let textos = {};
  const manejadores = {};  // tema -> lista de funciones
  let ws = null;

  // Reloj: el servidor manda t y tm al conectar y el navegador los hace avanzar.
  let base = null;  // {t, tm, perf}
  const info = {};

  // --- idioma -----------------------------------------------------------------
  async function cargarIdioma(nuevo) {
    lang = nuevo === "en" ? "en" : "es";
    const r = await fetch(`/web/i18n/${lang}.json`);
    textos = await r.json();
    document.documentElement.lang = lang;
    traducir(document);
    (manejadores["idioma"] || []).forEach((fn) => fn(lang));
  }

  function traducir(raiz) {
    raiz.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  }

  function t(clave, vars) {
    let s = textos[clave] ?? clave;
    if (vars) for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, v);
    return s;
  }

  function num(v, dec = 0) {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    return Number(v).toLocaleString(lang === "es" ? "es-ES" : "en-US",
      { minimumFractionDigits: dec, maximumFractionDigits: dec, useGrouping: Math.abs(v) >= 10000 });
  }

  // --- reloj ------------------------------------------------------------------
  function tAhora() {
    return base ? base.t + (performance.now() - base.perf) / 1000 : null;
  }

  function tmAhora() {
    return base ? base.tm + (performance.now() - base.perf) / 1000 : null;
  }

  function tmDeT(tSrv) {
    return base ? base.tm + (tSrv - base.t) : null;
  }

  function formatearTm(tm, conSegundos = true, conDia = true) {
    tm = Math.floor(tm);
    const dia = Math.floor(tm / 86400);
    let resto = tm % 86400;
    const h = String(Math.floor(resto / 3600)).padStart(2, "0");
    resto %= 3600;
    const m = String(Math.floor(resto / 60)).padStart(2, "0");
    const s = String(resto % 60).padStart(2, "0");
    const hora = conSegundos ? `${h}:${m}:${s}` : `${h}:${m}`;
    return conDia ? `${t("dia")} ${dia} · ${hora}` : hora;
  }

  // Escribe en el DOM solo si el texto cambió (en Mi estado, como tinta electrónica).
  function escribir(el, texto) {
    if (el && el.textContent !== texto) el.textContent = texto;
  }

  function iniciarReloj(el, conSegundos) {
    setInterval(() => {
      const tm = tmAhora();
      if (tm !== null) escribir(el, formatearTm(tm, conSegundos));
    }, 1000);
  }

  // --- fuentes ------------------------------------------------------------------
  function etiquetaFuente(fuente, sim) {
    let nombre = t(`fuente_${fuente}`);
    if (fuente === "camara_rgb" && info.camara === "video") nombre = t("fuente_camara_video");
    return sim ? `${nombre} · ${t("simulado")}` : nombre;
  }

  // --- WebSocket ------------------------------------------------------------------
  function on(tema, fn) {
    (manejadores[tema] ||= []).push(fn);
  }

  function despachar(tema, datos) {
    (manejadores[tema] || []).forEach((fn) => fn(datos));
  }

  function marcarConexion(conectado) {
    const el = document.querySelector("[data-conexion]");
    if (!el) return;
    el.dataset.conexion = conectado ? "si" : "no";
    el.dataset.i18n = conectado ? "conectado" : "desconectado";
    escribir(el, t(el.dataset.i18n));
  }

  function conectar() {
    ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
    ws.onopen = () => marcarConexion(true);
    ws.onclose = () => {
      marcarConexion(false);
      setTimeout(conectar, 2000);  // reintenta si el servidor se reinicia
    };
    ws.onmessage = (ev) => {
      const { tema, datos } = JSON.parse(ev.data);
      if (tema === "hola") alSaludo(datos);
      despachar(tema, datos);
    };
  }

  function enviar(accion, datos = {}) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ accion, ...datos }));
  }

  async function alSaludo(datos) {
    base = { t: datos.t, tm: datos.tm, perf: performance.now() };
    Object.assign(info, datos);
    document.querySelectorAll("[data-tripulante]").forEach((el) => escribir(el, datos.tripulante));
    if (!langForzado && datos.idioma !== lang) await cargarIdioma(datos.idioma);
  }

  // Logo: cuadro negro con triángulo blanco, como en el video.
  const LOGO = '<svg viewBox="0 0 14 14" aria-hidden="true"><path d="M7 2 L12.5 12 L1.5 12 Z" fill="#fff"/></svg>';

  function pintarLogos() {
    document.querySelectorAll(".logo").forEach((el) => { el.innerHTML = LOGO; });
  }

  async function iniciar({ conSegundos = true } = {}) {
    if (params.get("embed")) document.body.classList.add("embebido");
    pintarLogos();
    await cargarIdioma(lang);
    marcarConexion(false);
    const reloj = document.getElementById("reloj");
    if (reloj) iniciarReloj(reloj, conSegundos);
    conectar();
  }

  // --- gráficos en <canvas> ---------------------------------------------------------
  function color(nombre) {
    return getComputedStyle(document.body).getPropertyValue(nombre).trim();
  }

  // Ajusta el canvas a su tamaño en pantalla y devuelve {ctx, w, h}.
  function lienzo(canvas) {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== Math.round(w * dpr)) canvas.width = Math.round(w * dpr);
    if (canvas.height !== Math.round(h * dpr)) canvas.height = Math.round(h * dpr);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.font = "11px system-ui, sans-serif";
    return { ctx, w, h };
  }

  // Escala lineal de [a, b] a [c, d].
  function escala(a, b, c, d) {
    return (v) => c + ((v - a) / ((b - a) || 1)) * (d - c);
  }

  function trazo(ctx, xs, ys, fx, fy, col, ancho = 1.5) {
    ctx.strokeStyle = col;
    ctx.lineWidth = ancho;
    ctx.beginPath();
    let empezado = false;
    for (let i = 0; i < xs.length; i++) {
      if (ys[i] === null || ys[i] === undefined) { empezado = false; continue; }
      const x = fx(xs[i]), y = fy(ys[i]);
      if (!empezado) { ctx.moveTo(x, y); empezado = true; } else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }

  // Área entre dos curvas (bandas).
  function area(ctx, xs, lo, hi, fx, fy, col) {
    ctx.fillStyle = col;
    let i = 0;
    while (i < xs.length) {
      while (i < xs.length && (lo[i] === null || lo[i] === undefined)) i++;
      const ini = i;
      while (i < xs.length && lo[i] !== null && lo[i] !== undefined) i++;
      if (i - ini < 1) continue;
      ctx.beginPath();
      for (let k = ini; k < i; k++) ctx.lineTo(fx(xs[k]), fy(hi[k]));
      for (let k = i - 1; k >= ini; k--) ctx.lineTo(fx(xs[k]), fy(lo[k]));
      ctx.closePath();
      ctx.fill();
    }
  }

  return {
    iniciar, on, t, num, escribir, formatearTm, tAhora, tmAhora, tmDeT, enviar, traducir,
    etiquetaFuente, info, color, lienzo, escala, trazo, area,
    get lang() { return lang; },
  };
})();
