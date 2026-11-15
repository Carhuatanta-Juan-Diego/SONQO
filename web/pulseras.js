// Las pulseras de la tripulación, en vivo, en la fila del inicio: llegan una vez por segundo por el tema «pulsera»
// (pulso en la muñeca, batería y vibración; todo simulado en el sandbox). Cada una orbita la
// esfera de SONQO y, con cada latido, le manda una onda. La forma de onda es ilustrativa: la
// pulsera envía el pulso, no la curva; se dibuja a ese ritmo.
(() => {
  const S = SONQO;
  const $ = (id) => document.getElementById(id);
  const A = () => window.SONQO_APP;
  const MUESTRAS = 240, PASO_S = 1 / 60;   // 4 s de onda, una muestra cada 1/60 s (sin importar los cuadros)
  const p = {};                     // tripulante -> {msg, fase, onda[], latio, tarjeta, etiqueta}
  let orden = [], antes = null, acumulado = 0;

  // pulso de muñeca (PPG): subida rápida, bajada lenta y la muesca dícrota
  function ppg(f) {
    return Math.exp(-(((f - 0.12) / 0.07) ** 2)) + 0.38 * Math.exp(-(((f - 0.42) / 0.1) ** 2));
  }

  function nivelDe(t) {
    const app = A();
    return app ? app.resumenDe(app.datosDe(t)).nivel : "sin";
  }

  function activa(x) {
    const ahora = S.tAhora();
    return Boolean(x.msg && x.msg.activa && x.msg.pulso !== null && ahora !== null && ahora - x.msg.t < 4);
  }

  // ======================= la fila de tripulantes =======================
  // Una columna por tripulante: su estado, el pulso de su pulsera en grande, la onda, dónde está y la batería.
  function crearTarjetas() {
    const app = A();
    if (!app) return;
    orden = app.tripulantes();
    const fila = $("ini-fila"), capa = $("ia-sats");
    fila.replaceChildren();
    capa.replaceChildren();
    orden.forEach((t) => {
      const x = (p[t] ||= { msg: null, fase: Math.random(), onda: new Array(MUESTRAS).fill(0), latio: null });
      const b = document.createElement("button");
      b.className = "ini-col";
      b.innerHTML = `
        <span class="ini-cab"><b></b><span class="ini-est"><i class="punto"></i><span></span></span></span>
        <span class="ini-pulso"><b>—</b><small></small></span>
        <canvas class="ini-onda" aria-hidden="true"></canvas>
        <span class="ini-meta"></span>
        <span class="ini-pie"><span class="ini-bat"></span><span class="ini-vibra"></span></span>`;
      b.querySelector(".ini-cab b").textContent = t;
      b.onclick = () => A() && A().ir("astronauta", t);
      fila.appendChild(b);
      const e = document.createElement("div");
      e.className = "sat-etq";
      e.innerHTML = "<b></b> <span></span>";
      e.firstChild.textContent = t;
      capa.appendChild(e);
      x.tarjeta = b; x.etiqueta = e;
    });
    textos();
  }

  function textos() {
    orden.forEach((t) => {
      const x = p[t];
      if (!x || !x.tarjeta) return;
      x.tarjeta.querySelector(".ini-pulso small").textContent = S.t("u_pulso");
      x.tarjeta.querySelector(".ini-vibra").textContent = S.t("pul_vibra");
      escribirTarjeta(t);
    });
  }

  // «Laboratorio · 15 rpm · 36,6 °C»: lo que falta no se muestra
  function meta(t) {
    const app = A(), v = (app && app.datosDe(t).vital) || {};
    const partes = [app ? app.ubic(t) : ""];
    if (v.resp !== null && v.resp !== undefined) partes.push(`${S.num(v.resp, 0)} ${S.t("u_resp")}`);
    if (v.temp_piel !== null && v.temp_piel !== undefined) partes.push(`${S.num(v.temp_piel, 1)} ${S.t("u_temp_piel")}`);
    return partes.filter(Boolean).join(" · ");
  }

  function escribirTarjeta(t) {
    const x = p[t], b = x && x.tarjeta, m = x && x.msg;
    if (!b) return;
    const on = activa(x), nivel = nivelDe(t), app = A();
    const vital = app && app.datosDe(t).vital;
    const pulso = on ? m.pulso : vital && vital.pulso;   // la pulsera; si no hay, lo fusionado
    b.className = `ini-col ${nivel}${m && m.vibrando ? " vibra" : ""}`;
    b.querySelector(".punto").className = `punto ${nivel}`;
    S.escribir(b.querySelector(".ini-est span"), S.t(`ini_est_${nivel}`));
    S.escribir(b.querySelector(".ini-pulso b"), pulso === null || pulso === undefined ? "—" : S.num(pulso, 0));
    S.escribir(b.querySelector(".ini-meta"), meta(t));
    const bat = m ? m.bateria : null;
    S.escribir(b.querySelector(".ini-bat"), bat === null ? "" : S.t("ini_bat", { b: S.num(bat, 0) }));
    b.querySelector(".ini-bat").classList.toggle("baja", bat !== null && bat < 20);
    b.title = on ? S.t("pul_titulo_t", { t, n: m.vibraciones }) : S.t("pul_sin");
    x.etiqueta.lastChild.textContent = on ? S.num(m.pulso, 0) : "—";
    x.etiqueta.className = `sat-etq ${nivel}${on ? "" : " apagada"}`;
  }

  // la onda: una línea fina, sin rejilla ni brillo
  function dibujarOnda(x, color) {
    const cv = x.tarjeta.querySelector(".ini-onda");
    const dpr = window.devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
    if (!w) return;
    if (cv.width !== Math.round(w * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
    const ctx = cv.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.beginPath();
    x.onda.forEach((v, i) => {
      const px = (i / (MUESTRAS - 1)) * w, py = h - 3 - v * (h - 8);
      if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
    });
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.4;
    ctx.stroke();
  }

  const COLOR = { fuera: "#d92d20", aprende: "#c4651a", dentro: "#6889f7", sin: "#9ca3af" };

  // ======================= cada cuadro =======================
  // Dos etiquetas encimadas en la órbita: se ve solo la de la pulsera que pasa por delante.
  function ocultarEncimadas(pos) {
    orden.forEach((t, i) => {
      const a = pos[i], x = p[t];
      if (!a || !x || !x.etiqueta || a.detras) return;
      const tapada = pos.some((b, j) => j !== i && b && !b.detras && b.frente > a.frente
        && Math.abs(b.x - a.x) < 72 && Math.abs(b.y - a.y) < 16);
      if (tapada) x.etiqueta.classList.add("detras");
    });
  }

  function paso(ms) {
    const dt = antes === null ? 0 : Math.min(0.25, (ms - antes) / 1000);
    antes = ms;
    acumulado += dt;
    const pasos = Math.floor(acumulado / PASO_S);
    acumulado -= pasos * PASO_S;
    const esfera = window.SONQO_ESFERA && window.SONQO_ESFERA.actual;
    const visible = $("ini-fila") && $("ini-fila").offsetParent !== null;
    orden.forEach((t, i) => {
      const x = p[t];
      if (!x) return;
      const on = activa(x), nivel = nivelDe(t);
      for (let k = 0; k < pasos; k++) {
        if (on) {
          x.fase += PASO_S * x.msg.pulso / 60;
          if (x.fase >= 1) { x.fase -= 1; x.latio = ms / 1000; }
        }
        x.onda.push(on ? ppg(x.fase) : 0);
      }
      if (x.onda.length > MUESTRAS) x.onda.splice(0, x.onda.length - MUESTRAS);
      if (esfera) esfera.st.pulseras[i] = { activa: on, nivel, latio: x.latio };
      if (visible && x.tarjeta) dibujarOnda(x, COLOR[nivel] || COLOR.dentro);
      // la etiqueta sigue a su pulsera en la órbita
      const pos = esfera && esfera.st.etiquetas[i];
      if (visible && pos && x.etiqueta) {
        const ancho = x.etiqueta.parentElement.clientWidth;   // que no se salga por la derecha
        x.etiqueta.style.transform = `translate(${Math.min(pos.x, ancho - 84).toFixed(1)}px, ${pos.y.toFixed(1)}px)`;
        x.etiqueta.classList.toggle("detras", pos.detras);
      }
    });
    if (visible && esfera) ocultarEncimadas(esfera.st.etiquetas);
    requestAnimationFrame(paso);
  }

  S.on("hola", () => setTimeout(crearTarjetas, 0));
  S.on("idioma", textos);
  S.on("pulsera", (m) => {
    (p[m.tripulante] ||= { msg: null, fase: Math.random(), onda: new Array(MUESTRAS).fill(0), latio: null }).msg = m;
    escribirTarjeta(m.tripulante);
  });
  setInterval(() => orden.forEach(escribirTarjeta), 1000);   // estado del gemelo y señal perdida
  requestAnimationFrame(paso);
})();
