// SONQO en modo sandbox: el software con sus secciones, datos en vivo, un simulador y un recorrido guiado opcional.
(() => {
  const S = SONQO;
  const $ = (id) => document.getElementById(id);
  const CAPS = ["sonqo", "tripulacion", "astronauta", "arca", "caja", "rutina", "tierra",
    "datos", "senales", "energia", "gemelo", "estado", "nasa"];
  const SISTEMA = ["datos", "senales", "energia", "gemelo", "estado"];   // detalle técnico del tripulante principal
  const INDS = ["pulso", "resp", "temp_piel"];
  const DEC = { pulso: 0, resp: 0, temp_piel: 1 };
  const SENSORES = [
    { id: "camara_rgb", tipos: ["pulso"], w: "0,5 W" },
    { id: "radar", tipos: ["pulso", "resp"], w: "0,36 W" },
    { id: "termica", tipos: ["resp", "temp_piel"], w: "0,14 W" },
    { id: "profundidad", tipos: ["resp"], w: "3,5 W" },
    { id: "pulsera", tipos: ["pulso"], w: "", propia: true },   // en la muñeca, batería propia
  ];
  const MODULO = SENSORES.filter((x) => !x.propia);

  const st = {
    cap: "sonqo", tsel: null, simTrip: null, fichas: [], crew: {}, hc: {}, rutinas: [], rutinaS: 60, rfiltro: null,
    arcaHist: [], cajas: [], cajaVerif: {}, muestras: {}, camara: null, oxi: [], energia: null, vatios: [], vital: null,
    gem: { pulso: [], resp: [], temp_piel: [] }, ind: "pulso", evento: null, decision: null, rec: null,
    cerrado: false, recibida: null, caja: [], verif: null, paso: 0, hecho: [], marcas: {}, accionado: [],
    arca: null, radar: "normal", vistaUrl: null, bitacora: [], previo: {}, enviada: null, cajaN: 0,
    guia: new URLSearchParams(location.search).has("guia"),
  };

  // ======================= guía: qué hacer ahora =======================
  // Cada paso: dónde verlo en detalle (cap), su botón, qué hace, cuándo está listo
  // y el resultado que se le muestra al usuario, con los números reales.
  const PASOS = [
    { id: "calibrar", cap: "gemelo", listo: () => calibrado() },
    { id: "camara", cap: "senales", btn: "g_btn_camara",
      hacer: () => S.enviar("mantener_e2", { valor: true }),
      // cuenta solo si el usuario la encendió (durante la calibración ya está encendida)
      listo: () => { const m = camaraFresca(); return Boolean(st.accionado[1] && st.energia.mantener_e2 && m && m.fuente === "camara_rgb" && m.calidad >= 0.5); } },
    { id: "energia", cap: "energia", btn: "g_btn_apagar",
      hacer: () => S.enviar("mantener_e2", { valor: false }),
      listo: () => st.energia && st.energia.estado === "E0" && !st.energia.mantener_e2 },
    { id: "desvio", cap: "gemelo", btn: "g_btn_subir",
      hacer: () => { radar("desvio"); st.marcas.desvio = true; },
      listo: () => st.evento && st.evento.regla === "R1" },
    { id: "decidir", cap: "estado", btn: "g_btn_si",
      hacer: () => st.evento && S.enviar("decision", { evento: st.evento.id, acepta: true }),
      listo: () => st.decision && st.decision.acepta },
    { id: "tierra", cap: "tierra",
      listo: () => st.recibida && st.decision && st.recibida.t >= st.decision.t },
    { id: "caja", cap: "caja", btn: "g_btn_verificar",
      hacer: () => S.enviar("verificar_caja"),
      listo: () => Boolean(st.verif) },
    { id: "fin", cap: "estado", btn: "g_btn_bajar",
      hacer: () => { radar("normal"); st.marcas.bajar = true; },
      listo: () => st.cerrado && st.marcas.bajar },
  ];

  function calibrado() {
    const g = st.gem.pulso[st.gem.pulso.length - 1];
    return Boolean(g && g.calibracion[0] >= g.calibracion[1] && st.energia && st.energia.calibracion
      && st.energia.calibracion[0] >= st.energia.calibracion[1]);
  }

  // la última lectura de la cámara solo vale si es reciente (al encenderse junta 10 s de imagen)
  function camaraFresca() {
    const m = st.camara, ahora = S.tAhora();
    return m && ahora !== null && ahora - m.t < 3 && camaraEncendida() ? m : null;
  }

  function camaraEncendida() {
    return Boolean(st.energia && st.energia.fuentes && st.energia.fuentes.camara_rgb);
  }

  function ultimo(ind) { const h = st.gem[ind]; return h[h.length - 1]; }

  // la pulsera cuenta como activa si mandó pulso en los últimos 3 s
  function pulseraActiva() {
    const m = (st.muestras.pulsera || {}).pulso;
    return Boolean(m && (S.tAhora() ?? 0) - m.t < 3);
  }

  function escribirPulsera(id, pf) {
    const el = $(id);
    if (!el) return;
    el.parentElement.hidden = !pulseraActiva() && pf.pulsera === undefined;
    S.escribir(el, pf.pulsera === undefined ? "—" : `${S.num(pf.pulsera, 0)} ${S.t("u_pulso")}`);
  }

  // números que la guía pone en sus mensajes
  function valoresGuia() {
    const g = ultimo("pulso"), v = st.vital, pf = v ? v.por_fuente.pulso : {};
    const mc = camaraFresca(), cam = pf.camara_rgb ?? pf.reproduccion ?? (mc && mc.calidad > 0 ? mc.valor : undefined);
    return {
      p: g ? S.num(g.medido, 0) : "—",
      lo: g && g.normal ? S.num(g.normal[0], 0) : "—", hi: g && g.normal ? S.num(g.normal[1], 0) : "—",
      cam: cam === undefined ? "—" : S.num(cam, 0), radar: pf.radar === undefined ? "—" : S.num(pf.radar, 0),
      w: st.energia ? S.num(st.energia.vatios, 1) : "—",
      s: st.recibida ? S.num(st.recibida.retraso_s, 1) : "—",
      n: st.verif ? st.verif.registros : "—",
      seg: st.energia && st.energia.calibracion ? st.energia.calibracion[0] : 0,
      total: st.energia && st.energia.calibracion ? st.energia.calibracion[1] : 0,
    };
  }

  function irAPaso(i) {
    st.paso = Math.max(0, Math.min(PASOS.length - 1, i));
    dibujarGuia();
  }

  function revisarGuia() {
    const p = PASOS[st.paso];
    if (!st.hecho[st.paso] && p.listo()) st.hecho[st.paso] = true;
    dibujarGuia();
  }

  function dibujarGuia() {
    const p = PASOS[st.paso], hecho = st.hecho[st.paso], vals = valoresGuia();
    const final = st.paso === PASOS.length - 1;
    S.escribir($("g-num"), `${st.paso + 1}/${PASOS.length}`);
    S.escribir($("g-titulo"), S.t(`g_${p.id}_titulo`));
    S.escribir($("g-hacer"), hecho ? S.t(final ? "g_fin_completo" : "g_listo_sigue") : S.t(`g_${p.id}_hacer`, vals));
    // resultado: confirmación verde con números, o «en curso» mientras se espera
    const res = $("g-resultado");
    let tipo = null, txt = "";
    if (hecho) { tipo = "ok"; txt = S.t(`g_${p.id}_ok`, vals); }
    else if (st.accionado[st.paso] || ["calibrar", "tierra"].includes(p.id)) {
      tipo = "curso"; txt = S.t(`g_${p.id}_curso`, vals);
    }
    res.hidden = !tipo;
    if (tipo) {
      res.className = `resultado ${tipo}`;
      S.escribir(res.querySelector(".ico"), tipo === "ok" ? "✓" : "…");
      S.escribir(res.querySelector(".txt"), txt);
    }
    const b = $("g-accion");
    b.classList.toggle("llama", !hecho && Boolean(p.btn) && !st.accionado[st.paso]);
    if (hecho) {
      S.escribir(b, final ? S.t("g_reiniciar") : S.t("g_siguiente"));
      b.onclick = final ? reiniciarDemo : () => irAPaso(st.paso + 1);
      b.disabled = false;
    } else if (p.btn) {
      S.escribir(b, S.t(p.btn));
      b.onclick = () => { st.accionado[st.paso] = true; anotar("tu", S.t(`b_tu_${p.id}`)); p.hacer(); dibujarGuia(); };
      b.disabled = (p.id === "decidir" && !st.evento) || (st.accionado[st.paso] && p.id !== "decidir");
    } else {
      S.escribir(b, S.t("g_esperando"));
      b.onclick = null;
      b.disabled = true;
    }
    const ver = $("g-ver");
    S.escribir(ver, S.t("g_ver", { cap: S.t(`cap_${p.cap}`) }));
    ver.onclick = () => mostrarCap(p.cap);
    $("g-atras").disabled = st.paso === 0;
    $("g-puntos").replaceChildren(...PASOS.map((_, i) => {
      const el = document.createElement("i");
      el.className = i === st.paso ? "actual" : st.hecho[i] ? "hecho" : "";
      return el;
    }));
  }

  function reiniciarDemo() {
    S.enviar("cerrar_episodio");
    S.enviar("radar_modo", { modo: "normal" });
    tripulantes().filter((t) => t !== principal()).forEach((t) => {   // también los compañeros
      S.enviar("cerrar_episodio", { tripulante: t });
      S.enviar("radar_modo", { modo: "normal", tripulante: t });
    });
    S.enviar("mantener_e2", { valor: false });
    st.hecho = []; st.accionado = []; st.marcas = {}; st.verif = null; st.decision = null; st.recibida = null;
    st.cerrado = false; st.arca = null; st.radar = "normal";
    [$("arca-video"), $("i-arca-video")].forEach((v) => { v.pause(); v.currentTime = 0; });
    dibujarVerif(); dibujarArca(); marcarRadar();
    anotar("tu", S.t("b_reinicio"));
    irAPaso(calibrado() ? 1 : 0);
    revisarGuia();
  }

  // ======================= bitácora: lo que va pasando =======================
  // tipo: tu (acción del usuario) · ok · rojo · naranja · info
  function anotar(tipo, texto) {
    const tm = S.tmAhora ? S.tmAhora() : null;
    st.bitacora.unshift({ tipo, texto, tm });
    if (st.bitacora.length > 40) st.bitacora.pop();
    dibujarBitacora();
  }

  function dibujarBitacora() {
    $("bitacora").replaceChildren(...st.bitacora.slice(0, 14).map((b, i) => {
      const d = document.createElement("div");
      d.className = `fila ${b.tipo}` + (i === 0 ? " nueva" : "");
      d.innerHTML = "<span class='h'></span><span class='i'></span><span class='t'></span>";
      d.children[0].textContent = b.tm !== null ? S.formatearTm(b.tm, true, false) : "";
      d.children[1].textContent = { tu: "▶", ok: "✓", rojo: "!", naranja: "!", info: "·" }[b.tipo] || "·";
      d.children[2].textContent = b.texto;
      return d;
    }));
  }

  // ======================= avisos emergentes =======================
  function avisar(titulo, texto, color = "") {
    if (st.cap === "tripulacion" || st.cap === "sonqo") return;   // ahí ya se ve en el registro o lo dice SONQO
    const d = document.createElement("div");
    d.className = `toast ${color}`;
    d.innerHTML = "<b></b><span class='gris'></span>";
    d.querySelector("b").textContent = titulo;
    d.querySelector("span").textContent = texto;
    $("avisos").prepend(d);
    setTimeout(() => d.remove(), 7000);
  }

  // ======================= simulador =======================
  function marcarRadar() {
    // el simulador actúa sobre el tripulante elegido; mientras aprende su normal no se puede provocar un desvío
    const t = st.simTrip || principal(), esPrincipal = t === principal();
    const d = esPrincipal ? null : datosDe(t);
    const aprendiendo = esPrincipal ? !calibrado() : resumenDe(d).nivel !== "dentro" && resumenDe(d).nivel !== "fuera";
    const modo = esPrincipal ? st.radar : d.radar;
    document.querySelectorAll("#sim-trip .pildora").forEach((b) => b.classList.toggle("activa", b.dataset.trip === t));
    document.querySelectorAll("[data-radar]").forEach((b) => {
      b.setAttribute("aria-pressed", String(b.dataset.radar === modo));
      b.disabled = aprendiendo && b.dataset.radar !== "normal";
      b.title = b.disabled ? S.t("esc_espera") : "";
    });
    const nota = $("esc-espera");
    if (nota) nota.hidden = !aprendiendo;
  }

  function radar(modo, t) {
    t = t || principal();
    if (t === principal()) { st.radar = modo; S.enviar("radar_modo", { modo }); }
    else S.enviar("radar_modo", { modo, tripulante: t });
    marcarRadar();
  }

  // ======================= tripulación: un modelo común para los cuatro =======================
  const principal = () => S.info.tripulante || "MS-2";
  const tripulantes = () => (st.fichas.length ? st.fichas.map((f) => f.tripulante) : [principal()]);
  const ficha = (t) => st.fichas.find((f) => f.tripulante === t) || { tripulante: t, ubicacion: "modulo_trabajo", fuentes: [] };
  const ubic = (t) => S.t(`ub_${ficha(t).ubicacion}`);

  // Estado de un tripulante con la misma forma para el principal (temas sueltos) y los compañeros (tema «tripulacion»).
  function datosDe(t) {
    if (t === principal()) {
      const ev = st.evento;
      return { tripulante: t, ubicacion: ficha(t).ubicacion, fuentes: ficha(t).fuentes, vital: st.vital,
        gemelo: { pulso: ultimo("pulso"), resp: ultimo("resp"), temp_piel: ultimo("temp_piel") },
        evento: ev, rec: ev && st.rec && st.rec.evento === ev.id ? st.rec : null,
        decision: ev && st.decision && st.decision.evento === ev.id ? st.decision : null,
        radar: st.radar, hist: st.gem, principal: true };
    }
    const c = st.crew[t] || {};
    return { tripulante: t, ubicacion: ficha(t).ubicacion, fuentes: ficha(t).fuentes, vital: c.vital || null,
      gemelo: c.gemelo || {}, evento: c.evento || null, rec: c.evento ? c.recomendacion : null,
      decision: c.evento ? c.decision : null, radar: c.radar_modo || "normal",
      hist: st.hc[t] || { pulso: [], resp: [], temp_piel: [] }, principal: false };
  }

  // aprende | fuera | dentro | sin (sin datos todavía), y si espera una decisión N2
  function resumenDe(d) {
    const g = d.gemelo.pulso;
    const calib = Boolean(g && g.calibracion && g.calibracion[0] < g.calibracion[1]);
    const fuera = INDS.some((i) => d.gemelo[i] && d.gemelo[i].fuera);
    const nivel = !g ? "sin" : calib ? "aprende" : d.evento || fuera ? "fuera" : "dentro";
    const pendiente = Boolean(d.rec && d.rec.nivel === "N2" && !d.decision);
    return { nivel, calib, pendiente, cal: g && g.calibracion };
  }

  function arcaActivo(t) {
    return st.arcaHist.find((u) => u.actual && u.fin_tm === null && (!t || u.tripulante === t)) || null;
  }

  // ======================= menú =======================
  // Menú superior: el inicio (la tripulación y SONQO) y lo operativo. Lo técnico va en el submenú de la ficha.
  const MENU = ["sonqo", "arca", "caja", "rutina", "tierra", "nasa"];

  function enlace(c, t) {
    const b = document.createElement("button");
    b.className = "enlace-menu";
    b.dataset.c = c;
    if (t) b.dataset.t = t;
    b.onclick = () => mostrarCap(c, t || (c === "astronauta" ? st.tsel : undefined));
    return b;
  }

  function crearMenu() {
    $("menu").replaceChildren(...MENU.map((c) => enlace(c)));
    nombrarMenu();
  }

  // Submenú de la ficha: «← Tripulación», el nombre y, solo para el tripulante principal, su detalle técnico.
  // Se rearma solo si cambió lo que muestra: rearmarlo en cada refresco borraba el foco y a veces un clic.
  function crearSubmenu() {
    const nav = $("submenu"), enFicha = st.cap === "astronauta" || SISTEMA.includes(st.cap);
    nav.hidden = !enFicha;
    if (!enFicha) return;
    const t = SISTEMA.includes(st.cap) ? principal() : (st.tsel || principal());   // lo técnico es del tripulante principal
    const clave = `${t}|${tripulantes().length}`;
    if (nav.dataset.clave === clave) return;
    nav.dataset.clave = clave;
    const volver = enlace("sonqo");
    volver.classList.add("volver");
    const caps = t === principal() ? ["astronauta", ...SISTEMA] : ["astronauta"];
    nav.replaceChildren(volver, ...caps.map((c) => enlace(c, c === "astronauta" ? t : undefined)));
  }

  function nombrarMenu() {
    crearSubmenu();
    document.querySelectorAll("#menu .enlace-menu, #submenu .enlace-menu").forEach((b) => {
      const c = b.dataset.c;
      const activa = c === st.cap && !b.classList.contains("volver");
      b.classList.toggle("activa", activa);
      if (activa) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
      if (b.classList.contains("volver")) S.escribir(b, S.t("nav_volver"));
      else if (c === "astronauta") S.escribir(b, S.t("nav_ficha", { t: b.dataset.t || principal() }));
      else S.escribir(b, S.t(c === "sonqo" ? "nav_tripulacion" : `cap_${c}`));
    });
    const pend = tripulantes().some((t) => resumenDe(datosDe(t)).pendiente);   // alguien espera decidir: marca el inicio
    const ini = document.querySelector('#menu [data-c="sonqo"]');
    if (ini) ini.classList.toggle("alerta", pend);
  }

  function mostrarCap(c, t) {
    if (c === "tripulacion") c = "sonqo";   // la tripulación vive en el inicio
    st.cap = c;
    if (c === "astronauta") st.tsel = t || st.tsel || principal();
    document.querySelectorAll("[data-cap]").forEach((x) => { x.hidden = x.dataset.cap !== c; });
    if (c === "estado") marco("marco-estado", "/estado");
    if (c === "tierra") marco("marco-tierra", "/tierra");
    if (c === "caja") cargarCajas();
    if (c !== "arca") $("arca-video").pause();
    if (c !== "astronauta") $("i-arca-video").pause();
    document.dispatchEvent(new CustomEvent("sonqo-seccion", { detail: { cap: c } }));
    if (c === "sonqo" && st.guia) requestAnimationFrame(mostrarGuia);
    else window.scrollTo(0, 0);
    dibujarTodo();
  }

  // ======================= vista de la cámara (solo memoria, nunca se guarda) =======================
  async function refrescarVista() {
    const enFicha = st.cap === "astronauta" && st.tsel === principal();
    if (st.cap !== "senales" && !enFicha) return;
    const pre = enFicha ? "i" : "";
    const img = $(pre + "vista-img");
    let ok = false;
    if (camaraEncendida()) {
      try {
        const r = await fetch(`/camara.jpg?t=${Date.now()}`, { cache: "no-store" });
        if (r.status === 200) {
          const url = URL.createObjectURL(await r.blob());
          img.src = url;
          if (st.vistaUrl) URL.revokeObjectURL(st.vistaUrl);
          st.vistaUrl = url;
          ok = true;
        }
      } catch (e) { /* el servidor se reinicia: se reintenta */ }
    }
    img.hidden = !ok;
    $(pre + "vista-vivo").hidden = !ok;
    $(pre + "vista-vacio").hidden = ok;
    S.escribir($(pre + "vista-vacio"), S.t(camaraEncendida() ? "vista_cargando" : "vista_apagada"));
    document.querySelectorAll("[data-encender]").forEach((b) => { b.hidden = camaraEncendida(); });
    const nota = S.info.camara === "video" ? "s_video" : S.info.camara === "replay" ? "vista_replay" : "vista_webcam";
    S.escribir($(pre + "vista-nota"), S.t(nota));
  }

  // ======================= ARCA (simulado) =======================
  const hora = (tm) => (tm === null || tm === undefined ? "—" : S.formatearTm(tm, true, false));
  const diaHora = (tm) => (tm === null || tm === undefined ? "—" : S.formatearTm(tm, false, true));

  function dibujarArca() {
    const a = arcaActivo(), pill = $("arca-estado");
    pill.className = "estado-pill " + (a ? "aprende" : "");
    S.escribir(pill, a ? S.t("arca_para", { t: a.tripulante }) : S.t("arca_reposo"));
    S.escribir($("arca-detalle"), a ? S.t("arca_autorizado", { t: a.tripulante, hora: hora(a.tm), e: a.evento }) : S.t("arca_sin"));
    const filas = st.arcaHist.slice().reverse();
    $("arca-hist-vacio").hidden = filas.length > 0;
    S.escribir($("arca-hist-vacio"), S.t("ah_vacio"));
    $("arca-hist").replaceChildren(...(filas.length ? [filaTabla(["ah_h_trip", "ah_h_evento", "ah_h_inicio", "ah_h_fin", "ah_h_origen"].map((k) => S.t(k)), true)] : []),
      ...filas.map((u) => filaTabla([u.tripulante, u.evento, diaHora(u.tm),
        u.fin_tm !== null ? diaHora(u.fin_tm) : u.actual ? S.t("ah_en_curso") : S.t("ah_interrumpido"),
        u.actual ? S.t("ah_esta_corrida") : u.archivo])));
  }

  function filaTabla(celdas, cabecera) {
    const tr = document.createElement("tr");
    celdas.forEach((c) => {
      const td = document.createElement(cabecera ? "th" : "td");
      if (c instanceof Node) td.appendChild(c); else td.textContent = c;
      tr.appendChild(td);
    });
    return tr;
  }

  // ======================= tripulación =======================
  function dibujarTripulacion() {
    dibujarSistema();
    $("t-grilla").replaceChildren(...tripulantes().map((t) => {
      const d = datosDe(t), r = resumenDe(d);
      const b = document.createElement("button");
      b.className = `ficha-trip ${r.nivel}`;
      b.innerHTML = `<div class="ft-cab"><b></b><span class="estado-pill"></span></div><p class="nota ft-ub"></p>
        <div class="ft-vals"></div><canvas class="ft-linea"></canvas><p class="chico ft-pie"></p>`;
      b.querySelector("b").textContent = t;
      const pill = b.querySelector(".estado-pill");
      pill.className = "estado-pill " + ({ fuera: "fuera", dentro: "dentro", aprende: "aprende" }[r.nivel] || "");
      pill.textContent = S.t(`est_${r.nivel}`);
      b.querySelector(".ft-ub").textContent = `${ubic(t)} · ${fuentesTxt(d)}`;
      b.querySelector(".ft-vals").replaceChildren(...INDS.map((i) => {
        const g = d.gemelo[i], v = d.vital && d.vital[i];
        const x = document.createElement("div");
        x.innerHTML = "<b></b><span></span>";
        x.firstChild.textContent = v === null || v === undefined ? "—" : `${S.num(v, DEC[i])} ${S.t("u_" + i)}`;
        x.firstChild.className = g && !r.calib ? (g.fuera ? "rojo" : "verde") : "";
        x.lastChild.textContent = S.t("ind_" + i);
        return x;
      }));
      const pie = b.querySelector(".ft-pie");
      pie.className = "chico ft-pie " + (r.pendiente ? "rojo" : "gris");
      pie.textContent = r.pendiente ? S.t("ft_espera", { n: d.rec.nivel }) : d.decision && d.decision.acepta ? S.t("ft_autorizo")
        : r.calib ? S.t("calib_progreso", { s: r.cal[0], total: r.cal[1] }) : S.t("ft_vigilando");
      b.onclick = () => mostrarCap("astronauta", t);
      requestAnimationFrame(() => linea(b.querySelector(".ft-linea"), d.hist.pulso, r.nivel === "fuera"));
      return b;
    }));
  }

  function fuentesTxt(d) {
    return (d.fuentes || []).map((f) => S.t(`fuente_${f}`)).join(" · ");
  }

  // línea pequeña del pulso de los últimos minutos, con la banda normal
  function linea(cv, h, rojo) {
    const c = S.lienzo(cv);
    const pts = (h || []).filter((g) => g.medido !== null && g.medido !== undefined);
    if (pts.length < 2) return;
    const xs = pts.map((g) => g.t), ys = pts.map((g) => g.medido);
    const lo = pts.map((g) => g.normal && g.normal[0]), hi = pts.map((g) => g.normal && g.normal[1]);
    const vals = [...ys, ...lo, ...hi].filter((v) => v !== null && v !== undefined);
    const a = Math.min(...vals) - 3, z = Math.max(...vals) + 3;
    const fx = S.escala(xs[0], xs[xs.length - 1], 2, c.w - 2), fy = S.escala(a, z, c.h - 3, 3);
    S.area(c.ctx, xs, lo, hi, fx, fy, "rgba(26,127,55,0.15)");
    S.trazo(c.ctx, xs, ys, fx, fy, rojo ? "#d92d20" : "#161619", 1.5);
  }

  // indicadores del sistema (Tripulación)
  function dibujarSistema() {
    const ts = tripulantes(), res = ts.map((t) => [t, resumenDe(datosDe(t))]);
    const dentro = res.filter(([, r]) => r.nivel === "dentro").length;
    const pend = res.filter(([, r]) => r.pendiente).map(([t]) => t);
    const fuera = res.filter(([, r]) => r.nivel === "fuera").map(([t]) => t);
    const aprende = res.filter(([, r]) => r.nivel === "aprende").length;
    const ahora = S.tAhora() ?? 0;
    let enlace, enlaceSub, enlaceColor = "";
    if (st.enviada && (!st.recibida || st.recibida.t < st.enviada.t)) {
      enlace = S.t("k_t30_camino"); enlaceSub = S.t("k_t30_camino_s", { c: st.enviada.copias }); enlaceColor = "naranja";
    } else if (st.recibida) {
      enlace = S.t("k_t30_recibida"); enlaceColor = st.recibida.crc_ok ? "verde" : "rojo";
      enlaceSub = S.t("k_t30_recibida_s", { s: S.num(st.recibida.retraso_s, 1), hace: S.num(Math.max(0, ahora - st.recibida.t), 0) });
    } else { enlace = S.t("k_t30_nada"); enlaceSub = S.t("k_t30_nada_s"); }
    const a = arcaActivo();
    const tiles = [
      [S.t("k_trip"), S.t("k_trip_v", { n: dentro, total: ts.length }),
        fuera.length ? S.t("k_trip_fuera", { l: fuera.join(", ") }) : aprende ? S.t("k_trip_aprende", { n: aprende }) : S.t("k_trip_ok"),
        "tripulacion", fuera.length ? "rojo" : dentro === ts.length ? "verde" : ""],
      [S.t("k_alertas"), String(pend.length), pend.length ? S.t("k_alertas_s", { l: pend.join(", ") }) : S.t("k_alertas_no"),
        pend.length ? "astronauta" : "tripulacion", pend.length ? "rojo" : ""],
      [S.t("k_enlace"), enlace, enlaceSub, "tierra", enlaceColor],
      [S.t("k_arca"), a ? S.t("k_arca_prep", { t: a.tripulante }) : S.t("arca_reposo"), S.t("k_arca_usos", { n: st.arcaHist.length }), "arca", a ? "naranja" : ""],
    ];
    $("i-sistema").replaceChildren(...tiles.map(([tt, val, sub, cap, color]) => {
      const b = document.createElement("button");
      b.className = "kpi";
      b.innerHTML = "<span class='t'></span><b></b><span class='s'></span>";
      b.children[0].textContent = tt;
      b.children[1].textContent = val;
      b.children[1].className = color;
      b.children[2].textContent = sub;
      b.onclick = () => mostrarCap(cap, cap === "astronauta" ? pend[0] : undefined);
      return b;
    }));
    S.escribir($("i-mision"), S.tmAhora() ? S.t("i_actualizado", { h: S.formatearTm(S.tmAhora(), true, false) }) : "");
  }

  // ======================= un astronauta =======================
  function dibujarAstronauta() {
    const t = st.tsel || principal(), d = datosDe(t), r = resumenDe(d);
    const url = d.principal ? "/estado" : `/estado?t=${encodeURIComponent(t)}`;
    S.escribir($("a-nombre"), t);
    S.escribir($("a-ubicacion"), ubic(t));
    S.escribir($("a-fuentes"), S.t("a_fuentes", { l: fuentesTxt(d) }));
    S.escribir($("a-quien"), S.t("a_quien", { t, u: ubic(t) }));
    $("a-mi-estado").href = url + (S.lang === "en" ? (url.includes("?") ? "&" : "?") + "lang=en" : "");
    $("i-rec-ir").href = $("a-mi-estado").href;
    $("a-tecnico").hidden = !d.principal;
    $("a-camara").hidden = !d.principal;
    $("a-sin-camara").hidden = d.principal;
    // estado general
    const pill = $("i-estado");
    pill.className = "estado-pill " + ({ fuera: "fuera", dentro: "dentro", aprende: "aprende" }[r.nivel] || "");
    S.escribir(pill, r.nivel === "sin" ? "—" : r.nivel === "aprende" ? S.t("i_aprende") : S.t(r.nivel === "fuera" ? "i_fuera" : "i_dentro", { t }));
    S.escribir($("i-frase"), r.nivel === "sin" ? "" : r.calib ? S.t("i_aprende_f", { s: r.cal[0], total: r.cal[1] })
      : S.t(r.nivel === "fuera" ? "i_fuera_f" : "i_dentro_f"));
    $("i-calib").hidden = !r.calib;
    if (r.calib) $("i-calib").firstChild.style.width = `${(100 * r.cal[0]) / r.cal[1]}%`;
    $("i-inds").replaceChildren(...INDS.map((ind) => {
      const g = d.gemelo[ind], v = d.vital && d.vital[ind];
      const x = document.createElement("div");
      x.className = "mini-ind";
      x.innerHTML = "<span class='n'></span><b></b><span class='r'></span>";
      x.children[0].textContent = S.t("ind_" + ind);
      x.children[1].textContent = v === null || v === undefined ? "—" : `${S.num(v, DEC[ind])} ${S.t("u_" + ind)}`;
      x.children[1].className = g && !r.calib ? (g.fuera ? "rojo" : "verde") : "";
      x.children[2].textContent = g && g.normal ? S.t("i_normal", { lo: S.num(g.normal[0], DEC[ind]), hi: S.num(g.normal[1], DEC[ind]) }) : "";
      return x;
    }));
    // recomendación
    $("i-rec").hidden = !d.rec;
    if (d.rec) {
      S.escribir($("i-rec-nivel"), d.rec.nivel);
      $("i-rec-pasos").replaceChildren(...d.rec.pasos.map((k) => Object.assign(document.createElement("li"), { textContent: S.t(k) })));
      const el = $("i-rec-estado"), dec = d.decision;
      el.className = "chico " + (dec ? (dec.acepta ? "verde" : "gris") : "rojo");
      S.escribir(el, S.t(dec ? (dec.acepta ? "i_rec_si" : "i_rec_no") : "i_rec_espera", { t }));
    }
    // fuentes (principal: cámara; compañeros: sus sensores)
    const pf = d.vital ? d.vital.por_fuente.pulso : {};
    if (d.principal) {
      const mc = camaraFresca(), cam = pf.camara_rgb ?? pf.reproduccion ?? (mc && mc.calidad > 0 ? mc.valor : undefined);
      S.escribir($("i-cam"), cam === undefined ? "—" : `${S.num(cam, 0)} ${S.t("u_pulso")}`);
      S.escribir($("i-radar"), pf.radar === undefined ? "—" : `${S.num(pf.radar, 0)} ${S.t("u_pulso")}`);
      escribirPulsera("i-pulsera", pf);
    } else {
      $("a-por-fuente").replaceChildren(...Object.entries(pf).map(([f, v]) => {
        const x = document.createElement("div");
        x.innerHTML = "<span></span><b></b>";
        x.firstChild.textContent = S.etiquetaFuente(f, true);
        x.lastChild.textContent = `${S.num(v, 0)} ${S.t("u_pulso")}`;
        return x;
      }));
    }
    const co = d.vital ? d.vital.coinciden.pulso : null, ins = $("i-coinciden");
    S.escribir(ins, S.t(co === true ? "p_coinciden" : co === false ? "p_no_coinciden" : "p_una_fuente"));
    ins.className = "insignia " + (co === true ? "verde" : co === false ? "rojo" : "gris");
    S.escribir($("a-coinciden"), S.t(co === true ? "a_coinciden_si" : co === false ? "a_coinciden_no" : "p_una_fuente"));
    // ARCA de este tripulante
    const a = arcaActivo(t), card = $("i-arca");
    if (a && card.hidden) {
      const v = $("i-arca-video");
      v.play().catch(() => { v.muted = true; v.play().catch(() => {}); });
    }
    card.hidden = !a;
    if (a) S.escribir($("i-arca-txt"), S.t("arca_autorizado", { t, hora: hora(a.tm), e: a.evento }));
    dibujarGraficos(d);
    dibujarRutinaDe(t);
  }

  function dibujarGraficos(d) {
    const cont = $("a-graficos");
    if (cont.children.length !== INDS.length) {
      cont.replaceChildren(...INDS.map((i) => {
        const x = document.createElement("div");
        x.className = "graf";
        x.innerHTML = "<p class='nota'></p><canvas></canvas>";
        x.dataset.ind = i;
        return x;
      }));
    }
    cont.querySelectorAll(".graf").forEach((x) => {
      const i = x.dataset.ind, g = d.gemelo[i];
      S.escribir(x.querySelector(".nota"), `${S.t("ind_" + i).toUpperCase()} · ${S.t("u_" + i)}`);
      linea(x.querySelector("canvas"), d.hist[i], Boolean(g && g.fuera));
    });
  }

  // ======================= mediciones de rutina =======================
  function filaRutina(f, conTrip) {
    const estado = f.calibrando ? S.t("est_aprende") : f.fuera.length
      ? S.t("r_fuera", { l: f.fuera.map((i) => S.t("ind_" + i).toLowerCase()).join(", ") }) : S.t("est_dentro");
    const celdas = [hora(f.tm)];
    if (conTrip) celdas.push(f.tripulante);
    celdas.push(S.num(f.pulso, 0), S.num(f.resp, 0), S.num(f.temp_piel, 1), estado,
      (f.fuentes || []).map((x) => S.t(`fuente_${x}`)).join(" · "));
    const tr = filaTabla(celdas);
    tr.className = f.fuera.length && !f.calibrando ? "rojo" : "";
    return tr;
  }

  function cabRutina(conTrip) {
    const k = ["r_h_hora", ...(conTrip ? ["r_h_trip"] : []), "r_h_pulso", "r_h_resp", "r_h_temp", "r_h_estado", "r_h_fuentes"];
    return filaTabla(k.map((x) => S.t(x)), true);
  }

  function dibujarRutina() {
    S.escribir($("r-bajada"), S.t("r_bajada", { n: st.rutinaS }));
    $("r-filtro").replaceChildren(...[null, ...tripulantes()].map((t) => {
      const b = document.createElement("button");
      b.className = "pildora" + (st.rfiltro === t ? " activa" : "");
      b.textContent = t || S.t("r_todos");
      b.onclick = () => { st.rfiltro = t; dibujarRutina(); };
      return b;
    }));
    const filas = st.rutinas.filter((f) => !st.rfiltro || f.tripulante === st.rfiltro).slice().reverse().slice(0, 80);
    $("r-vacio").hidden = filas.length > 0;
    S.escribir($("r-vacio"), S.t("r_vacio", { n: st.rutinaS }));
    $("r-tabla").replaceChildren(...(filas.length ? [cabRutina(true)] : []), ...filas.map((f) => filaRutina(f, true)));
  }

  function dibujarRutinaDe(t) {
    const filas = st.rutinas.filter((f) => f.tripulante === t).slice(-5).reverse();
    const tabla = document.createElement("table");
    tabla.replaceChildren(...(filas.length ? [cabRutina(false)] : []), ...filas.map((f) => filaRutina(f, false)));
    $("a-rutina").replaceChildren(filas.length ? tabla : Object.assign(document.createElement("p"), { className: "gris chico", textContent: S.t("r_vacio", { n: st.rutinaS }) }));
  }

  // ======================= todas las cajas negras =======================
  async function cargarCajas() {
    try {
      const r = await fetch("/api/cajas", { cache: "no-store" });
      st.cajas = await r.json();
    } catch (e) { /* el servidor se reinicia */ }
    dibujarCajas();
  }

  function dibujarCajas() {
    const kb = (b) => `${S.num(b / 1024, 0)} KB`;
    const filas = st.cajas.map((c) => {
      const v = st.cajaVerif[c.archivo];
      const btn = document.createElement("button");
      btn.className = "boton chico";
      btn.textContent = S.t("cn_verificar");
      btn.onclick = () => { st.cajaVerif[c.archivo] = { pendiente: true }; dibujarCajas(); S.enviar("verificar_caja", { archivo: c.archivo }); };
      const res = document.createElement("span");
      if (v && v.pendiente) { res.className = "gris chico"; res.textContent = S.t("cn_verificando"); }
      else if (v) {
        const ok = v.integra && v.misma_decision;
        res.className = "insignia " + (ok ? "verde" : "rojo");
        res.textContent = !v.integra ? S.t("cn_alterada") : v.misma_decision ? S.t("cn_ok", { n: v.registros }) : S.t("cn_distinta");
        res.title = v.mensaje || "";
      }
      const accion = document.createElement("span");
      accion.className = "fila-botones";
      accion.append(btn, res);
      return filaTabla([c.archivo, c.tripulante || "—", S.num(c.registros, 0), kb(c.bytes), c.actual ? S.t("cn_actual") : S.t("cn_anterior"), accion]);
    });
    $("cn-tabla").replaceChildren(filaTabla(["cn_h_archivo", "cn_h_trip", "cn_h_registros", "cn_h_tamano", "cn_h_corrida", ""].map((k) => (k ? S.t(k) : "")), true), ...filas);
  }

  // la guía vive debajo de la fila de tripulantes: se baja hasta ella, sin quedar tapada por la barra fija
  function mostrarGuia() {
    const barra = document.querySelector(".barra");
    const y = $("guia").getBoundingClientRect().top + window.scrollY - (barra ? barra.offsetHeight : 0) - 12;
    window.scrollTo(0, Math.max(0, y));
  }

  function verGuia(si) {
    st.guia = si;
    $("guia").hidden = !si;
    $("c-tour").setAttribute("aria-pressed", String(si));
    if (si) { $("simulador").hidden = true; mostrarCap("tripulacion"); }
  }

  // aviso rojo bajo la barra: algún tripulante tiene una recomendación N2 sin responder
  function dibujarAtencion() {
    const pend = tripulantes().filter((t) => resumenDe(datosDe(t)).pendiente);
    const ver = pend.length && !(st.cap === "astronauta" && pend.includes(st.tsel)) && st.cap !== "estado";
    $("atencion").hidden = !ver;
    if (pend.length) {
      S.escribir($("atencion-txt"), S.t(pend.length > 1 ? "i_atencion_varios" : "i_atencion", { t: pend.join(", ") }));
      $("atencion-ir").onclick = () => mostrarCap("astronauta", pend[0]);
    }
  }

  // Mi estado y Tierra se muestran tal cual las ve cada quien, dentro de la presentación.
  function marco(id, ruta) {
    const cont = $(id);
    if (cont.firstChild) return;
    const f = document.createElement("iframe");
    f.className = "marco";
    f.src = `${ruta}?embed=1${S.lang === "en" ? "&lang=en" : ""}`;
    cont.appendChild(f);
    // la altura sigue al contenido (misma página de origen), sin barra de desplazamiento interna
    const ajustar = () => {
      const doc = f.contentDocument;
      if (doc && doc.body) f.style.height = `${doc.body.scrollHeight + 4}px`;
    };
    f.onload = ajustar;
    setInterval(ajustar, 1000);
  }

  // ======================= 1 · datos =======================
  function dibujarDatos() {
    const enc = (st.energia && st.energia.fuentes) || {};
    $("sensores").replaceChildren(...SENSORES.map((s) => {
      const d = document.createElement("div");
      const on = s.propia ? pulseraActiva() : Boolean(enc[s.id]);
      d.className = "tarjeta sensor" + (on ? "" : " apagado");
      d.innerHTML = `<span class="estado insignia"></span><p class="nota" style="margin:0"></p><h3></h3>
        <p class="sub" style="margin:0"></p><div class="valores"></div><p class="nota" style="margin:10px 0 0"></p>`;
      const ins = d.querySelector(".estado");
      ins.textContent = on ? S.t("encendido") : S.t(s.id === "termica" ? "en_espera" : "apagado");
      ins.className = "estado insignia " + (on ? "verde" : "gris");
      d.querySelector(".nota").textContent = s.propia ? S.t("sensor_pulsera_n") : S.t("sensor_n", { n: SENSORES.indexOf(s) + 1 });
      d.querySelector("h3").textContent = S.t(`sensor_${s.id}`);
      d.querySelector(".sub").textContent = S.t(`sensor_${s.id}_mide`);
      d.querySelector(".valores").replaceChildren(...s.tipos.map((tipo) => {
        const fuente = s.id === "camara_rgb" && st.camara ? st.camara.fuente : s.id;
        let m = (st.muestras[fuente] || {})[tipo];
        if (m && (S.tAhora() ?? 0) - m.t > 3) m = null;   // lectura vieja: no mostrar
        const x = document.createElement("div");
        x.innerHTML = "<b></b><small></small><span></span>";
        x.querySelector("b").textContent = on && m && m.calidad > 0 ? S.num(m.valor, DEC[tipo]) : "—";
        x.querySelector("small").textContent = S.t(`u_${tipo}`);
        x.querySelector("span").textContent = S.t(`ind_${tipo}`).toLowerCase();
        return x;
      }));
      const sim = s.id === "camara_rgb" ? (S.info.camara !== "webcam") : true;
      d.lastElementChild.textContent = (s.propia ? S.t("pulsera_bateria") : `${s.w} ${S.t("activo")}`) + (sim ? ` · ${S.t(`sim_${s.id}`)}` : "");
      return d;
    }));
    // lentes del módulo: se encienden las que la energía tiene activas
    const ys = [64, 94, 124, 154];
    $("lentes").innerHTML = MODULO.map((s, i) => {
      const on = Boolean(enc[s.id]);
      return `<circle cx="302" cy="${ys[i]}" r="9" fill="${on ? "#2a2a2a" : "#3a3a3a"}" stroke="${on ? "#89e5fc" : "#555"}" stroke-width="${on ? 3 : 1}"/>`
        + (on ? `<circle cx="302" cy="${ys[i]}" r="3" fill="#89e5fc"/>` : "")
        + `<text x="324" y="${ys[i] + 3}" font-family="ui-monospace,monospace" font-size="9" fill="${on ? "#161619" : "#999"}">${S.t("lente_" + s.id)}</text>`;
    }).join("");
    $("haz-camara").toggleAttribute("hidden", !enc.camara_rgb);
  }

  // ======================= 2 · señales =======================
  function lienzoLinea(id, ys, color, punto) {
    const c = S.lienzo($(id));
    if (!ys || !ys.length) return;
    const xs = ys.map((_, i) => i);
    const lim = Math.max(...ys.map(Math.abs)) || 1;
    const fx = S.escala(0, ys.length - 1, 4, c.w - 8), fy = S.escala(-lim, lim, c.h - 8, 8);
    c.ctx.strokeStyle = "#ececea"; c.ctx.beginPath(); c.ctx.moveTo(4, c.h / 2); c.ctx.lineTo(c.w - 4, c.h / 2); c.ctx.stroke();
    S.trazo(c.ctx, xs, ys, fx, fy, color, 1.6);
    if (punto) {
      c.ctx.fillStyle = color; c.ctx.beginPath();
      c.ctx.arc(fx(ys.length - 1), fy(ys[ys.length - 1]), 3.5, 0, 7); c.ctx.fill();
    }
  }

  function dibujarRitmo(det) {
    const c = S.lienzo($("cv-ritmo"));
    if (!det) return;
    const n = 40, f = det.f, p = det.p;
    const paso = Math.max(1, Math.floor(f.length / n));
    const barras = [];
    for (let i = 0; i < f.length; i += paso) barras.push([f[i], Math.max(...p.slice(i, i + paso))]);
    const pico = barras.reduce((a, b) => (b[1] > a[1] ? b : a));
    const w = (c.w - 8) / barras.length;
    barras.forEach(([fi, pi], i) => {
      const h = Math.max(2, pi * (c.h - 26));
      c.ctx.fillStyle = fi === pico[0] ? "#1a7f37" : "#d9d9d6";
      c.ctx.fillRect(4 + i * w + 1, c.h - 4 - h, Math.max(1, w - 2), h);
    });
    c.ctx.fillStyle = "#1a7f37";
    c.ctx.font = "11px ui-monospace, monospace";
    const xi = 4 + barras.indexOf(pico) * w;
    c.ctx.fillText(`${S.num(det.pico_lpm / 60, 2)} Hz`, Math.min(xi + 6, c.w - 60), 14);
  }

  function dibujarSenales() {
    const m = camaraFresca(), on = camaraEncendida();
    const pos = m && m.fuente === "camara_rgb" && m.detalle;
    let aviso = "";
    if (!on) aviso = S.t("s_apagada");
    else if (m && m.fuente === "reproduccion") aviso = S.t("s_reproduccion");
    else if (!pos) aviso = S.t("s_juntando");
    $("s-aviso").hidden = !aviso;
    S.escribir($("s-aviso"), aviso);
    lienzoLinea("cv-cruda", pos ? m.detalle.cruda : null, "#8a8a85", true);
    lienzoLinea("cv-filtro", pos ? m.detalle.senal : null, "#1a7f37", true);
    dibujarRitmo(pos ? m.detalle : null);
    const valor = m && m.calidad > 0 ? m.valor : null;
    const el = $("s-pulso");
    el.innerHTML = "";
    el.append(valor === null ? "—" : S.num(valor, 0), Object.assign(document.createElement("small"), { textContent: S.t("u_pulso") }));
    S.escribir($("s-calidad"), m ? S.t("s_calidad", { q: S.num(m.calidad, 2) }) : "");
    $("s-calidad-barra").style.width = `${m ? 100 * m.calidad : 0}%`;
    // dos fuentes
    const v = st.vital, pf = v ? v.por_fuente.pulso : {};
    const cam = pf.camara_rgb ?? pf.reproduccion;
    S.escribir($("s-cam"), cam === undefined ? "—" : `${S.num(cam, 0)} ${S.t("u_pulso")}`);
    S.escribir($("s-radar"), pf.radar === undefined ? "—" : `${S.num(pf.radar, 0)} ${S.t("u_pulso")}`);
    escribirPulsera("s-pulsera", pf);
    const co = v ? v.coinciden.pulso : null;
    const ins = $("s-coinciden");
    S.escribir(ins, S.t(co === true ? "p_coinciden" : co === false ? "p_no_coinciden" : "p_una_fuente"));
    ins.className = "insignia " + (co === true ? "verde" : co === false ? "rojo" : "gris");
    // oxímetro
    const ult = st.oxi[st.oxi.length - 1];
    S.escribir($("o-dif"), ult && ult.dif !== undefined ? `${S.num(ult.dif, 1)} ${S.t("u_pulso")}` : "—");
    const ahora = S.tAhora() ?? 0;
    const rec = st.oxi.filter((o) => o.dif !== undefined && o.t >= ahora - 60);
    const err = rec.length ? rec.reduce((s, o) => s + Math.abs(o.dif), 0) / rec.length : null;
    S.escribir($("o-err"), err === null ? "—" : `${S.num(err, 1)} ${S.t("u_pulso")}`);
    $("o-err").className = err === null ? "" : err <= 5 ? "verde" : "rojo";
    S.escribir($("o-n"), String(st.oxi.length));
    S.escribir($("o-nota"), ult && ult.dif === undefined ? S.t("p_oxi_sin_camara") : S.t("p_oxi_nota"));
  }

  // ======================= 3 · energía =======================
  const ESC = { E0: "≈ 2 W", E1: "≈ 2,5 W", E2: "≈ 22 W", E3: "60 W +" };

  function dibujarEnergia() {
    const e = st.energia;
    if (!e) return;
    $("escalera").replaceChildren(...["E0", "E1", "E2", "E3"].map((s) => {
      const d = document.createElement("div");
      d.className = `peldano ${s.toLowerCase()}` + (s === e.estado ? " actual" : "");
      d.innerHTML = `<span class="e">${s}</span><div><b></b><span class="d"></span></div><div class="w"><span></span><small></small></div>`;
      d.querySelector("b").textContent = S.t(`nombre_${s}`);
      d.querySelector(".d").textContent = S.t(`d_${s}`);
      d.querySelector(".w span").textContent = s === "E0" || s === "E1" ? `${S.num(e.vatios_estado[s], 1)} W` : ESC[s];
      d.querySelector(".w small").textContent = S.t(`cuando_${s}`);
      return d;
    }));
    const el = $("e-w");
    el.innerHTML = "";
    el.append(S.num(e.vatios, 2), Object.assign(document.createElement("small"), { textContent: "W" }));
    S.escribir($("e-chip"), `${e.estado} · ${S.t("nombre_" + e.estado)}`);
    S.escribir($("e-prom"), `${S.num(e.promedio_w, 2)} W`);
    S.escribir($("e-wh"), `${S.num(e.wh, 3)} Wh`);
    S.escribir($("e-e0"), `${S.num(e.porcentaje.E0, 0)} %`);
    S.escribir($("e-cam"), S.t(e.fuentes.camara_rgb ? "e_cam_on" : "e_cam_off"));
    S.escribir($("e-motivo"), S.t("e_motivo", { e: e.estado, m: S.t("motivo_" + e.motivo) }));
    const c = S.lienzo($("cv-vatios"));
    const pts = st.vatios;
    if (pts.length < 2) return;
    const t1 = pts[pts.length - 1][0];
    const fx = S.escala(t1 - 300, t1, 4, c.w - 4);
    const fy = (w) => S.escala(0, 2, c.h - 6, 6)(Math.log10(Math.max(w, 1)));
    c.ctx.strokeStyle = "#ececea";
    [2, 10, 60].forEach((w) => { c.ctx.beginPath(); c.ctx.moveTo(4, fy(w)); c.ctx.lineTo(c.w - 4, fy(w)); c.ctx.stroke(); });
    c.ctx.fillStyle = "#9ca3af"; c.ctx.font = "10px ui-monospace, monospace";
    [2, 10, 60].forEach((w) => c.ctx.fillText(`${w} W`, 6, fy(w) - 3));
    c.ctx.strokeStyle = "#161619"; c.ctx.lineWidth = 1.6; c.ctx.beginPath();
    pts.forEach(([t, w], i) => {   // escalones: el consumo cambia de golpe
      const x = fx(t), y = fy(w);
      if (i === 0) c.ctx.moveTo(x, y);
      else { c.ctx.lineTo(x, fy(pts[i - 1][1])); c.ctx.lineTo(x, y); }
    });
    c.ctx.stroke();
  }

  // ======================= 4 · gemelo =======================
  function dibujarGemelo() {
    const h = st.gem[st.ind];
    const ult = h[h.length - 1];
    S.escribir($("gm-etq"), S.t("gm_etq", { ind: S.t("ind_" + st.ind).toUpperCase(), u: S.t("u_" + st.ind).toUpperCase() }));
    const c = S.lienzo($("cv-gemelo"));
    if (ult) {
      const t1 = ult.t, t0 = t1 - 180, tf = t1 + 60;
      const xs = h.map((g) => g.t), med = h.map((g) => g.medido);
      const bLo = h.map((g) => g.normal && g.normal[0]), bHi = h.map((g) => g.normal && g.normal[1]);
      const iLo = h.map((g) => g.intervalo && g.intervalo[0]), iHi = h.map((g) => g.intervalo && g.intervalo[1]);
      const pred = ult.prediccion_60;
      const vals = [...med, ...bLo, ...bHi].filter((v) => v !== null && v !== undefined);
      if (pred) vals.push(pred[0] - 2 * pred[1], pred[0] + 2 * pred[1]);
      let lo = Math.min(...vals), hi = Math.max(...vals);
      const pad = (hi - lo) * 0.12 || 1; lo -= pad; hi += pad;
      const fx = S.escala(t0, tf, 36, c.w - 8), fy = S.escala(lo, hi, c.h - 18, 8);
      c.ctx.strokeStyle = "#f0f0ee"; c.ctx.fillStyle = "#9ca3af"; c.ctx.font = "10px ui-monospace, monospace";
      for (let k = 0; k <= 4; k++) {
        const v = lo + ((hi - lo) * k) / 4;
        c.ctx.beginPath(); c.ctx.moveTo(36, fy(v)); c.ctx.lineTo(c.w - 8, fy(v)); c.ctx.stroke();
        c.ctx.fillText(S.num(v, DEC[st.ind]), 2, fy(v) + 3);
      }
      S.area(c.ctx, xs, bLo, bHi, fx, fy, "rgba(26,127,55,0.15)");
      S.area(c.ctx, xs, iLo, iHi, fx, fy, "rgba(104,137,247,0.14)");
      S.trazo(c.ctx, xs, med, fx, fy, "#161619", 1.6);
      const ib = bHi.length - 1;
      if (bHi[ib] !== null && bHi[ib] !== undefined) {
        c.ctx.fillStyle = "#1a7f37"; c.ctx.font = "12px system-ui, sans-serif";
        c.ctx.fillText(S.t("gm_normal_de", { t: S.info.tripulante || "MS-2" }), fx(t1) - 110, fy(bHi[ib]) - 6);
      }
      if (pred && ult.previsto !== null) {
        const px = [t1, tf], sd = 1.96 * pred[1];
        S.area(c.ctx, px, [ult.previsto, pred[0] - sd], [ult.previsto, pred[0] + sd], fx, fy, "rgba(104,137,247,0.10)");
        c.ctx.setLineDash([5, 4]);
        S.trazo(c.ctx, px, [ult.previsto, pred[0]], fx, fy, "#6889f7", 1.5);
        c.ctx.setLineDash([]);
      }
      c.ctx.fillStyle = "#9ca3af"; c.ctx.font = "10px ui-monospace, monospace";
      c.ctx.fillText("−3 min", fx(t0), c.h - 3);
      c.ctx.fillText(S.t("ahora"), fx(t1) - 14, c.h - 3);
      c.ctx.fillText("+60 s", fx(tf) - 34, c.h - 3);
      c.ctx.strokeStyle = "#d4d4d0"; c.ctx.setLineDash([2, 3]);
      c.ctx.beginPath(); c.ctx.moveTo(fx(t1), 8); c.ctx.lineTo(fx(t1), c.h - 16); c.ctx.stroke(); c.ctx.setLineDash([]);
      S.escribir($("gm-detalle"), S.t("gm_detalle", {
        prev: S.num(ult.previsto, 1), int: ult.intervalo ? `${S.num(ult.intervalo[0], 1)}–${S.num(ult.intervalo[1], 1)}` : S.t("g_aprendiendo"),
        conf: S.num(100 * ult.confianza, 0), desvio: ult.desvio ? S.t("si") : S.t("no") }));
    }
    dibujarHolograma();
  }

  function etiquetaHolo(id, ind) {
    const g = st.gem[ind][st.gem[ind].length - 1];
    const el = $(id);
    if (!g) { el.innerHTML = ""; return; }
    el.className = "etq" + (g.fuera ? " fuera" : "");
    el.innerHTML = "<b></b><span></span>";
    el.querySelector("b").textContent = `${S.num(g.medido, DEC[ind])} ${S.t("u_" + ind)}`;
    el.querySelector("span").textContent = S.t("ind_" + ind).toLowerCase()
      + (g.normal ? ` · ${S.t("normal_corto")} ${S.num(g.normal[0], DEC[ind])}–${S.num(g.normal[1], DEC[ind])}` : "");
  }

  function dibujarHolograma() {
    const p = st.gem.pulso[st.gem.pulso.length - 1], r = st.gem.resp[st.gem.resp.length - 1];
    const fuera = ["pulso", "resp", "temp_piel"].some((i) => { const g = st.gem[i][st.gem[i].length - 1]; return g && g.fuera; });
    $("holo").classList.toggle("fuera", fuera);
    // el corazón late al pulso medido y el pecho se mueve a la respiración medida
    const corazon = document.querySelector(".holo .corazon"), pecho = document.querySelector(".holo .pecho");
    if (p && p.medido) ajustarRitmo(corazon, 60 / p.medido);
    if (r && r.medido) ajustarRitmo(pecho, 60 / r.medido);
    etiquetaHolo("h-pulso", "pulso"); etiquetaHolo("h-resp", "resp"); etiquetaHolo("h-temp", "temp_piel");
    const calib = p && p.calibracion[0] < p.calibracion[1];
    const est = $("h-estado");
    est.className = "etq" + (fuera ? " fuera" : "");
    S.escribir(est, calib ? S.t("calib_progreso", { s: p.calibracion[0], total: p.calibracion[1] })
      : S.t(fuera ? "h_fuera" : "h_dentro"));
    const g = st.gem[st.ind][st.gem[st.ind].length - 1];
    S.escribir($("h-normal"), g && g.normal ? S.t("h_normal", { ind: S.t("ind_" + st.ind).toLowerCase(),
      lo: S.num(g.normal[0], DEC[st.ind]), hi: S.num(g.normal[1], DEC[st.ind]), u: S.t("u_" + st.ind) }) : "");
    S.escribir($("h-pred"), g && g.prediccion_60 ? S.t("h_pred", { v: S.num(g.prediccion_60[0], DEC[st.ind]),
      sd: S.num(1.96 * g.prediccion_60[1], DEC[st.ind] || 1), u: S.t("u_" + st.ind) }) : "");
  }

  function ajustarRitmo(el, segundos) {
    const actual = parseFloat(el.style.animationDuration) || 0;
    if (Math.abs(actual - segundos) / segundos > 0.05) el.style.animationDuration = `${segundos.toFixed(2)}s`;
  }

  // ======================= 7 · caja negra =======================
  function resumenRegistro(r) {
    const d = r.datos || {};
    switch (r.tipo) {
      case "vital": return `${S.t("ind_pulso").toLowerCase()} ${S.num(d.pulso, 0)} · ${S.t("ind_resp").toLowerCase()} ${S.num(d.resp, 0)} · ${S.t("piel")} ${S.num(d.temp_piel, 1)}`;
      case "energia": return `${d.estado} · ${S.t("motivo_" + d.motivo)}`;
      case "evento": return d.cierra ? S.t("m_cerrado", { id: d.cierra, motivo: S.t("motivo_" + d.motivo) }) : `${d.id} · ${d.regla}`;
      case "recomendacion": return `${d.evento} · ${d.nivel}`;
      case "decision": return `${d.evento} · ${S.t(d.acepta ? "boton_si" : "boton_no")}`;
      case "t30_enviada": case "t30_recibida": return `30 bytes · ${(d.hex || "").slice(0, 23)}…`;
      case "oximetro": return `${S.num(d.valor, 0)} ${S.t("u_pulso")}`;
      case "control": if (d.accion === "pulsera_vibra") return S.t("r_pulsera_vibra", { n: d.nivel, e: d.evento });
        return d.accion + (d.modo ? ` · ${d.modo}` : "") + (d.valor !== undefined ? ` · ${d.valor}` : "");
      case "gemelo": return `${S.t("ind_" + d.indicador)} · ${d.fuera ? S.t("g_fuera") : S.t("g_dentro")}`;
      default: return d.version ? `v${d.version} · ${d.modo}` : "";
    }
  }

  function dibujarCaja() {
    $("registros").replaceChildren(...st.caja.slice().reverse().slice(0, 12).map((r) => {
      const d = document.createElement("div");
      d.className = "registro";
      d.innerHTML = "<span class='h'></span><span class='tipo'></span><span class='res'></span><span class='h hash'></span>";
      d.children[0].textContent = S.formatearTm(r.tm, true, false);
      d.children[1].textContent = S.t("tipo_" + r.tipo);
      d.children[2].textContent = resumenRegistro(r);
      d.children[3].textContent = r.hash.slice(0, 8) + "…";
      return d;
    }));
  }

  function dibujarVerif() {
    const v = st.verif, cont = $("verif");
    if (!v) { cont.replaceChildren(); return; }
    const linea = (ok, txt) => {
      const d = document.createElement("div");
      d.className = "exito";
      d.style.margin = "8px 0";
      if (!ok) { d.style.background = "var(--rojo-suave)"; d.style.color = "var(--rojo)"; }
      d.innerHTML = `<span class="check" style="${ok ? "" : "background:var(--rojo)"}">${ok ? "✓" : "✕"}</span><span></span>`;
      d.querySelector(".check").style.color = "#fff";
      d.lastChild.textContent = txt;
      return d;
    };
    cont.replaceChildren(
      linea(v.integra, v.integra ? S.t("v_integra", { n: v.registros }) : v.mensaje),
      linea(v.misma_decision, S.t(v.misma_decision ? "v_misma" : "v_distinta", { n: v.vital, e: v.eventos.join(", ") || "—" })),
    );
  }

  // ======================= barra superior =======================
  // la barra superior ya no muestra datos de un solo tripulante: eso está en Tripulación
  function dibujarChips() {
    $("chip-energia").hidden = true;
    $("chip-pulso").hidden = true;
  }

  function dibujarTodo() {
    nombrarMenu();
    dibujarChips();
    if (st.cap === "tripulacion") dibujarTripulacion();
    if (st.cap === "astronauta") dibujarAstronauta();
    if (st.cap === "rutina") dibujarRutina();
    if (st.cap === "datos") dibujarDatos();
    if (st.cap === "senales") dibujarSenales();
    if (st.cap === "energia") dibujarEnergia();
    if (st.cap === "gemelo") dibujarGemelo();
    if (st.cap === "caja") { dibujarCaja(); dibujarVerif(); dibujarCajas(); }
    refrescarVista();
    dibujarArca();
    dibujarAtencion();
    dibujarGuia();
  }

  // Lo que cambió en un compañero va al registro de eventos (como con el principal).
  function anotarCompanero(m, antes) {
    const t = m.tripulante, ev = m.evento, ea = antes.evento;
    if (ev && (!ea || ea.id !== ev.id)) {
      const pulso = m.vital && m.vital.pulso;
      if (ev.regla === "R1") anotar("rojo", S.t("b_r1", { t, id: ev.id, p: S.num(pulso, 0) }));
      else if (ev.regla === "R2") anotar("rojo", S.t("b_r2", { t, id: ev.id }));
      if (m.recomendacion) {
        anotar("rojo", S.t("b_rec", { n: m.recomendacion.nivel, t }));
        anotar("naranja", S.t("b_pulsera_vibra", { t, n: m.recomendacion.nivel }));
      }
      avisar(S.t("av_r1_t", { t }), S.t("av_otro", { id: ev.id }), "rojo");
      document.dispatchEvent(new CustomEvent("sonqo-alerta", { detail: { tipo: "evento", t, regla: ev.regla } }));
    }
    if (!ev && ea) anotar("ok", S.t("b_cierre", { t, id: ea.id }));
    const d = m.decision, da = antes.decision;
    if (ev && d && !(da && da.evento === d.evento)) anotar(d.acepta ? "ok" : "info", S.t(d.acepta ? "b_si" : "b_no", { t, e: d.evento }));
    if (m.radar_modo !== antes.radar_modo && antes.radar_modo) anotar("tu", S.t(`b_tu_radar_${m.radar_modo}`) + ` (${t})`);
  }

  function crearSimTrip() {
    $("sim-trip").replaceChildren(...tripulantes().map((t) => {
      const b = document.createElement("button");
      b.className = "pildora";
      b.dataset.trip = t;
      b.textContent = t;
      b.onclick = () => { st.simTrip = t; marcarRadar(); };
      return b;
    }));
    marcarRadar();
  }

  // Redibuja lo que está en pantalla como mucho ~3 veces por segundo (llegan varios mensajes por segundo).
  let vivoPendiente = false;
  function vivo() {
    if (vivoPendiente) return;
    vivoPendiente = true;
    setTimeout(() => {
      vivoPendiente = false;
      nombrarMenu(); dibujarAtencion();
      if (st.cap === "tripulacion") dibujarTripulacion();
      if (st.cap === "astronauta") dibujarAstronauta();
    }, 300);
  }

  // ======================= mensajes =======================
  // al conectarse llega el estado actual: no se avisa ni se anota lo viejo
  let listo = false;
  setTimeout(() => { listo = true; }, 1500);
  const trip = () => S.info.tripulante || "MS-2";

  S.on("hola", (h) => {
    Object.keys(st.gem).forEach((k) => (st.gem[k] = []));
    st.caja = []; st.vatios = []; st.evento = null; st.previo = {};
    if (h.radar_modo) { st.radar = h.radar_modo; marcarRadar(); }
    S.escribir($("caja-archivo"), h.caja_negra ? S.t("p_caja_archivo", { f: h.caja_negra }) : "");
    st.fichas = h.tripulacion || [];
    st.rutinaS = h.rutina_s || st.rutinaS;
    st.rutinas = []; st.crew = {}; st.hc = {};
    st.tsel = st.tsel || h.tripulante; st.simTrip = st.simTrip || h.tripulante;
    crearMenu(); crearSimTrip();
    if (!st.bitacora.length) anotar("info", S.t("b_conectado", { t: h.tripulante || "MS-2" }));
  });
  S.on("muestra", (m) => {
    (st.muestras[m.fuente] ||= {})[m.tipo] = m;
    if (m.fuente === "oximetro") st.oxi.push(m);
    if (m.tipo === "pulso" && (m.fuente === "camara_rgb" || m.fuente === "reproduccion")) {
      st.camara = m;
      // primera medida buena de la cámara desde que se encendió
      if (listo && m.fuente === "camara_rgb" && m.calidad >= 0.5 && !st.previo.camMidio) {
        st.previo.camMidio = true;
        anotar("ok", S.t("b_cam_midio", { v: S.num(m.valor, 0), q: S.num(m.calidad, 2) }));
      }
    }
    if (st.cap === "senales") dibujarSenales();
    if (st.cap === "datos" && m.tipo !== "resp") dibujarDatos();
  });
  S.on("energia", (e) => {
    const antes = st.previo.energia;
    if (listo && antes && antes !== e.estado) {
      anotar("info", S.t("b_energia", { e: e.estado, n: S.t("nombre_" + e.estado), w: S.num(e.vatios, 1),
        m: S.t("motivo_" + e.motivo), c: S.t(e.fuentes.camara_rgb ? "i_cam_abierta" : "i_cam_cerrada") }));
    }
    if (!e.fuentes.camara_rgb) st.previo.camMidio = false;
    st.previo.energia = e.estado;
    st.energia = e;
    st.vatios.push([e.t, e.vatios]);
    while (st.vatios.length && st.vatios[0][0] < e.t - 300) st.vatios.shift();
    $("c-mantener").setAttribute("aria-pressed", String(e.mantener_e2));
    marcarRadar();
    dibujarChips();
    if (st.cap === "energia") dibujarEnergia();
    if (st.cap === "datos") dibujarDatos();
    vivo();
    revisarGuia();
  });
  S.on("vital", (v) => {
    st.vital = v; dibujarChips();
    if (st.cap === "senales") dibujarSenales();
    vivo();
  });
  S.on("gemelo", (g) => {
    const h = st.gem[g.indicador];
    h.push(g);
    while (h.length && h[0].t < g.t - 180) h.shift();
    if (g.indicador === "pulso") {
      const cal = g.calibracion[0] >= g.calibracion[1];
      if (listo && st.previo.calibrado === false && cal && g.normal) {
        anotar("ok", S.t("b_calibrado", { t: trip(), lo: S.num(g.normal[0], 0), hi: S.num(g.normal[1], 0) }));
      }
      st.previo.calibrado = cal;
    }
    if (st.cap === "gemelo" && (g.indicador === st.ind || g.indicador === "temp_piel")) dibujarGemelo();
    if (g.indicador === "pulso") { vivo(); revisarGuia(); }
  });

  S.on("evento", (e) => {
    if (e.cierra) {
      if (st.evento && st.evento.id === e.cierra) {
        st.evento = null; st.cerrado = true;
        if (st.arca) st.arca.cerrado = true;
        if (listo) {
          avisar(S.t("av_cierre_t", { t: trip() }), S.t("av_cierre", { id: e.cierra }), "verde");
          anotar("ok", S.t("b_cierre", { t: trip(), id: e.cierra }));
        }
      }
    } else if (e.regla === "R1" || e.regla === "R2") {
      const nuevo = !st.evento || st.evento.id !== e.id;
      st.evento = e; st.cerrado = false;
      if (nuevo && listo) {
        avisar(S.t("av_r1_t", { t: trip() }), S.t(`av_${e.regla.toLowerCase()}`, { id: e.id }), "rojo");
        anotar("rojo", S.t(`b_${e.regla.toLowerCase()}`, { t: trip(), id: e.id, ...valoresGuia() }));
        document.dispatchEvent(new CustomEvent("sonqo-alerta", { detail: { tipo: "evento", t: trip(), regla: e.regla } }));
      }
    } else if (e.regla === "R3" && listo) {
      avisar(S.t("av_r3_t"), S.t("av_r3"), "naranja");
      anotar("naranja", S.t("b_r3"));
    }
    dibujarChips(); dibujarArca(); dibujarAtencion(); revisarGuia();
    vivo();
  });
  S.on("decision", (d) => {
    st.decision = d;
    if (listo) anotar(d.acepta ? "ok" : "info", S.t(d.acepta ? "b_si" : "b_no", { t: trip(), e: d.evento }));
    if (d.acepta && (d.acciones || []).includes("preparar_arca")) {
      st.arca = { evento: d.evento, t: d.t, cerrado: false };
      if (st.cap === "arca") $("arca-video").play().catch(() => {});
    }
    dibujarArca(); dibujarAtencion(); revisarGuia();
    vivo();
  });
  S.on("recomendacion", (r) => {
    const nueva = !st.rec || st.rec.evento !== r.evento || r.repregunta;
    st.rec = r;
    if (r.repregunta) st.decision = null;
    if (listo && nueva) anotar("rojo", S.t("b_rec", { n: r.nivel, t: trip() }));
    dibujarAtencion();
    vivo();
  });
  S.on("t30", (d) => {
    if (d.fase === "enviada" && d.bytes) st.enviada = d;
    if (d.fase === "enviada" && d.bytes && listo) {
      anotar("info", S.t(d.prueba ? "b_t30_prueba" : "b_t30_enviada", { c: d.copias, s: S.num(d.llega_en_s, 1) }));
    }
    if (d.fase !== "recibida") return;
    st.recibida = d;
    if (listo) {
      avisar(S.t("av_t30_t"), S.t(d.crc_ok ? "av_t30" : "crc_mal", { s: S.num(d.retraso_s, 1) }), "verde");
      anotar(d.crc_ok ? "ok" : "rojo", S.t(d.crc_ok ? "b_t30_recibida" : "crc_mal", { s: S.num(d.retraso_s, 1) }));
    }
    revisarGuia();
  });
  S.on("caja", (r) => {
    if (r.verificacion) {
      const vf = r.verificacion;
      if (vf.nombre) st.cajaVerif[vf.nombre] = vf;
      if (st.cap === "caja") dibujarCajas();
      document.dispatchEvent(new CustomEvent("sonqo-verificacion", { detail: vf }));
      if (vf.principal === false) {
        anotar(vf.integra && vf.misma_decision ? "ok" : "rojo", S.t("b_caja_otra", { t: vf.tripulante || "—", n: vf.registros, f: vf.nombre }));
        return;
      }
      st.verif = vf; dibujarVerif();
      const v = r.verificacion;
      anotar(v.integra && v.misma_decision ? "ok" : "rojo",
        v.integra ? S.t(v.misma_decision ? "b_caja_ok" : "b_caja_distinta", { n: v.registros }) : v.mensaje);
      revisarGuia(); return;
    }
    st.caja.push(r);
    st.cajaN = Math.max(st.cajaN, r.n || 0);
    if (listo && r.tipo === "control" && r.datos.accion === "pulsera_vibra") {
      anotar("naranja", S.t("b_pulsera_vibra", { t: trip(), n: r.datos.nivel }));
    }
    if (st.caja.length > 15) st.caja.shift();
    if (st.cap === "caja") dibujarCaja();
  });
  // compañeros: un mensaje por segundo con todo su estado
  S.on("tripulacion", (m) => {
    const antes = st.crew[m.tripulante] || {};
    st.crew[m.tripulante] = m;
    const h = (st.hc[m.tripulante] ||= { pulso: [], resp: [], temp_piel: [] });
    INDS.forEach((i) => {
      const g = m.gemelo && m.gemelo[i];
      if (!g) return;
      h[i].push(g);
      while (h[i].length && h[i][0].t < g.t - 180) h[i].shift();
    });
    if (listo) anotarCompanero(m, antes);
    vivo();
  });
  S.on("arca", (a) => {
    const antes = new Set(st.arcaHist.filter((u) => u.actual).map((u) => `${u.tripulante}/${u.evento}/${u.tm}`));
    st.arcaHist = a.historial || [];
    for (const u of st.arcaHist) {
      if (u.actual && !antes.has(`${u.tripulante}/${u.evento}/${u.tm}`) && listo) {
        avisar(S.t("av_arca_t"), S.t("av_arca", { t: u.tripulante }), "naranja");
        anotar("naranja", S.t("b_arca_de", { t: u.tripulante }));
        document.dispatchEvent(new CustomEvent("sonqo-alerta", { detail: { tipo: "arca", t: u.tripulante } }));
      }
    }
    dibujarArca(); vivo();
  });
  S.on("rutina", (f) => {
    st.rutinas.push(f);
    if (st.rutinas.length > 400) st.rutinas.shift();
    if (st.cap === "rutina") dibujarRutina();
    vivo();
  });
  S.on("error", (e) => {
    S.escribir($("g-error"), S.t("error", { m: e.mensaje }));
    setTimeout(() => S.escribir($("g-error"), ""), 5000);
  });
  S.on("idioma", () => {
    document.querySelectorAll(".marco").forEach((f) => f.remove());
    dibujarTodo();
    if (st.cap === "estado" || st.cap === "tierra") mostrarCap(st.cap);
  });

  // ======================= controles =======================
  $("g-atras").onclick = () => irAPaso(st.paso - 1);
  $("b-verificar").onclick = () => { anotar("tu", S.t("b_tu_caja")); S.enviar("verificar_caja"); };
  $("c-verificar").onclick = () => S.enviar("verificar_ahora");
  $("c-mantener").onclick = () => S.enviar("mantener_e2", { valor: $("c-mantener").getAttribute("aria-pressed") !== "true" });
  document.querySelectorAll("[data-radar]").forEach((b) => {
    b.onclick = () => {
      const t = st.simTrip || principal();
      if (t === principal()) anotar("tu", S.t("b_tu_radar_" + b.dataset.radar));
      radar(b.dataset.radar, t);
    };
  });
  $("c-cerrar").onclick = () => S.enviar("cerrar_episodio");
  $("c-t30").onclick = () => { anotar("tu", S.t("b_tu_t30")); S.enviar("t30_prueba"); };
  $("c-reiniciar").onclick = () => { if (confirm(S.t("c_confirmar_reinicio"))) S.enviar("reiniciar_normal"); };
  $("c-demo").onclick = reiniciarDemo;
  $("b-simulador").onclick = () => { $("simulador").hidden = !$("simulador").hidden; };
  $("sim-cerrar").onclick = () => { $("simulador").hidden = true; };
  $("c-tour").onclick = () => verGuia(!st.guia);
  $("g-ocultar").onclick = () => verGuia(false);
  document.querySelectorAll("[data-abrir-sim]").forEach((b) => { b.onclick = () => { $("simulador").hidden = false; }; });
  document.querySelectorAll("[data-encender]").forEach((b) => {
    b.onclick = () => { anotar("tu", S.t("b_tu_camara")); S.enviar("mantener_e2", { valor: true }); };
  });
  document.querySelectorAll("[data-ir]").forEach((b) => { b.onclick = () => mostrarCap(b.dataset.ir); });
  document.querySelectorAll("[data-ind]").forEach((b) => {
    b.onclick = () => {
      st.ind = b.dataset.ind;
      document.querySelectorAll("[data-ind]").forEach((x) => x.classList.toggle("activa", x === b));
      dibujarGemelo();
    };
  });
  $("f-oxi").onsubmit = (ev) => {
    ev.preventDefault();
    S.enviar("oximetro", { valor: Number($("i-oxi").value) });
    $("i-oxi").value = "";
  };
  window.addEventListener("resize", dibujarTodo);
  setInterval(() => {
    if (st.cap === "senales") dibujarSenales();
    vivo();
    dibujarAtencion(); revisarGuia();
  }, 2000);
  setInterval(refrescarVista, 200);   // ~5 cuadros por segundo mientras se ve la sección

  // lo que el asistente (asistente.js) necesita leer del sistema
  window.SONQO_APP = {
    principal, tripulantes, datosDe, resumenDe, ubic, arcaActivo, ir: mostrarCap,
    arcaHist: () => st.arcaHist, t30: () => ({ enviada: st.enviada, recibida: st.recibida }),
    rutinas: () => st.rutinas, rutinaS: () => st.rutinaS, energia: () => st.energia,
    cajaActual: (t) => (t === principal() ? null : (st.crew[t] || {}).caja),
  };

  crearMenu();
  marcarRadar();
  S.iniciar({ conSegundos: true }).then(() => {
    const pedida = new URLSearchParams(location.search).get("seccion");
    mostrarCap(CAPS.includes(pedida) ? pedida : "sonqo", new URLSearchParams(location.search).get("t") || undefined);
    irAPaso(calibrado() ? 1 : 0);
    verGuia(st.guia);
  });
})();
