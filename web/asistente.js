// SONQO, el asistente: responde con los datos del sistema (reglas fijas, sin internet y sin inventar),
// habla con la voz neuronal local (voz.js) o con la del navegador y, si el navegador lo permite, escucha.
// Su cuerpo es la esfera (esfera.js): respira, se agita al hablar y recibe los latidos de las pulseras.
(() => {
  const S = SONQO;
  const $ = (id) => document.getElementById(id);
  const A = () => window.SONQO_APP;
  const DEC = { pulso: 0, resp: 0, temp_piel: 1 };
  const V = window.SONQO_VOZ;
  const ia = { nivel: 0, objetivo: 0, voz: false, hablando: false, escuchando: false, saludo: false,
    alerta: 0, ultimo: "", ultimaEmocion: "neutral", reconocedor: null, verificando: null, esfera: null };

  // ======================= la esfera =======================
  // Respira despacio en reposo; mientras habla se agita con el volumen real de la voz.
  function animar(ms) {
    const cv = $("orbe");
    if (cv && cv.offsetParent !== null) {
      ia.nivel += (ia.objetivo - ia.nivel) * 0.18;     // suaviza la voz
      ia.objetivo *= 0.9;                               // cada palabra es un pulso que se apaga
      const medido = V ? V.nivel() : 0;
      if (medido) ia.objetivo = Math.max(ia.objetivo, medido);
      else if (ia.hablando) ia.objetivo = Math.max(ia.objetivo, 0.25 + 0.15 * Math.sin(ms / 1000 * 7));
      ia.alerta *= 0.995;
      if (ia.esfera) {
        const e = ia.esfera.st;
        e.voz = ia.nivel; e.alerta = ia.alerta > 0.05 ? Math.min(1, ia.alerta * 1.2) : 0;
        e.escucha += ((ia.escuchando ? 1 : 0) - e.escucha) * 0.08;
        ia.esfera.dibujar(ms);
      } else dibujarOrbe(cv, ms / 1000);
    }
    requestAnimationFrame(animar);
  }

  function crearEsfera() {
    try {
      ia.esfera = window.SONQO_ESFERA ? window.SONQO_ESFERA.crear($("orbe")) : null;
    } catch (e) {
      console.warn("Sin WebGL para la esfera; uso el dibujo plano.", e);
      aPlano();
    }
    if (window.SONQO_ESFERA) window.SONQO_ESFERA.actual = ia.esfera;
    // la GPU es compartida con la voz: si pierde el contexto, la esfera no debe desaparecer
    $("orbe").addEventListener("webglcontextlost", (ev) => { ev.preventDefault(); aPlano(); }, { once: true });
  }

  function aPlano() {
    ia.esfera = null;
    if (window.SONQO_ESFERA) window.SONQO_ESFERA.actual = null;
    const cv = $("orbe"), nuevo = cv.cloneNode();   // un canvas con WebGL ya no da contexto 2D
    cv.replaceWith(nuevo);
  }

  function dibujarOrbe(cv, t) {
    const dpr = window.devicePixelRatio || 1;
    const w = cv.clientWidth, h = cv.clientHeight;
    if (cv.width !== Math.round(w * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
    const ctx = cv.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const cx = w / 2, cy = h / 2, base = Math.min(w, h) * 0.24;
    const respira = 0.04 * Math.sin(t * 1.1);        // ~6 s por respiración
    const r = base * (1 + respira + ia.nivel * 0.22 + (ia.escuchando ? 0.05 : 0));
    const rojo = ia.alerta > 0.05;
    const c1 = rojo ? "255,138,128" : "253,186,116", c2 = rojo ? "217,45,32" : "194,65,12";
    // halo
    const halo = ctx.createRadialGradient(cx, cy, r * 0.6, cx, cy, r * 2.1);
    halo.addColorStop(0, `rgba(${c1},${0.28 + ia.nivel * 0.3})`);
    halo.addColorStop(1, `rgba(${c1},0)`);
    ctx.fillStyle = halo;
    ctx.beginPath(); ctx.arc(cx, cy, r * 2.1, 0, Math.PI * 2); ctx.fill();
    // anillos mientras escucha
    if (ia.escuchando) {
      for (let k = 0; k < 3; k++) {
        const f = ((t * 0.6 + k / 3) % 1);
        ctx.strokeStyle = `rgba(94,234,212,${0.5 * (1 - f)})`;
        ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.arc(cx, cy, r * (1.1 + f * 0.9), 0, Math.PI * 2); ctx.stroke();
      }
    }
    // cuerpo: un círculo que se deforma suave, más cuando habla
    ctx.beginPath();
    const n = 120;
    for (let i = 0; i <= n; i++) {
      const a = (i / n) * Math.PI * 2;
      const d = 1 + 0.025 * Math.sin(3 * a + t * 0.9) + 0.02 * Math.sin(5 * a - t * 1.3)
        + ia.nivel * 0.09 * Math.sin(7 * a + t * 6) + ia.nivel * 0.05 * Math.sin(11 * a - t * 9);
      const x = cx + Math.cos(a) * r * d, y = cy + Math.sin(a) * r * d;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    const cuerpo = ctx.createRadialGradient(cx - r * 0.3, cy - r * 0.35, r * 0.1, cx, cy, r * 1.05);
    cuerpo.addColorStop(0, "rgba(255,247,237,0.95)");
    cuerpo.addColorStop(0.45, `rgba(${c1},0.9)`);
    cuerpo.addColorStop(1, `rgba(${c2},0.85)`);
    ctx.shadowColor = `rgba(${c1},0.9)`;
    ctx.shadowBlur = 30 + ia.nivel * 40;
    ctx.fillStyle = cuerpo;
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  function estado(clave) { S.escribir($("ia-estado"), S.t(clave)); }

  // ======================= conversación =======================
  function burbuja(quien, texto) {
    const d = document.createElement("div");
    d.className = `ia-msg ${quien}`;
    d.textContent = texto;
    const lista = $("ia-mensajes");
    lista.appendChild(d);
    while (lista.children.length > 60) lista.firstChild.remove();
    lista.scrollTop = lista.scrollHeight;
  }

  function decir(texto, hablarlo = true, emocion = "neutral") {
    ia.ultimo = texto; ia.ultimaEmocion = emocion;
    burbuja("sonqo", texto);
    S.escribir($("ia-dice"), texto);
    if (hablarlo && ia.voz) hablar(texto, emocion);
  }

  function preguntar(texto) {
    texto = texto.trim();
    if (!texto) return;
    burbuja("tu", texto);
    const r = interpretar(texto);
    decir(r.texto);
    if (r.accion) setTimeout(r.accion, 400);
  }

  // ======================= voz =======================
  function vozElegida() {
    const voces = window.speechSynthesis ? speechSynthesis.getVoices() : [];
    const del = voces.filter((v) => v.lang && v.lang.toLowerCase().startsWith(S.lang));
    return del.find((v) => v.localService) || del[0] || null;
  }

  // Primero la voz neuronal local; si no está arriba o falla, la del navegador.
  async function hablar(texto, emocion = "neutral") {
    if (V && V.estado()) {
      let empezo = false;
      try {
        await V.decirNeuronal(texto, {
          emocion, lang: S.lang,
          alEmpezar: () => { empezo = true; ia.hablando = true; estado("ia_hablando"); notaVoz(); },
          alTerminar: () => { ia.hablando = false; estado("ia_espera"); },
        });
        return;
      } catch (e) {
        // cortada a propósito (otra pregunta, «Voz» apagada, micrófono): ya habla otra frase o nadie
        if (e.name === "AbortError") return;
        console.warn("La voz neuronal falló.", e);
        V.callar();               // lo que ya sonaba no debe superponerse con la otra voz
        ia.hablando = false;
        estado("ia_espera");
        S.escribir($("ia-nota"), `${S.t("ia_voz_fallo")} (${e.message || e})`);
        V.revisar().then(notaVoz);
        if (empezo) return;       // ya se oyó parte: repetirla entera con otra voz confunde
      }
    }
    hablarNavegador(texto);
  }

  function hablarNavegador(texto) {
    if (!window.speechSynthesis) return;
    // Brave y Chromium en Linux suelen no traer voces: sin aviso, quedaría en silencio
    if (!speechSynthesis.getVoices().length) { S.escribir($("ia-nota"), S.t("ia_sin_voces")); return; }
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(texto);
    const v = vozElegida();
    if (v) u.voice = v;
    u.lang = S.lang === "en" ? "en-US" : "es-ES";
    u.rate = 1.02;
    u.onstart = () => { ia.hablando = true; estado("ia_hablando"); };
    u.onboundary = () => { ia.objetivo = 1; };
    u.onend = u.onerror = () => { ia.hablando = false; estado("ia_espera"); };
    speechSynthesis.speak(u);
  }

  function alternarVoz() {
    ia.voz = !ia.voz;
    $("ia-voz").setAttribute("aria-pressed", String(ia.voz));
    if (!ia.voz) { if (V) V.callar(); else if (window.speechSynthesis) speechSynthesis.cancel(); ia.hablando = false; estado("ia_espera"); return; }
    if (V) V.abrirAudio();   // el navegador solo deja abrir el audio con un clic
    if (!(V && V.estado()) && !window.speechSynthesis) { S.escribir($("ia-nota"), S.t("ia_sin_voz")); return; }
    // si lo último fue el saludo, se rehace con los datos de ahora (pudo quedar viejo)
    if (ia.ultimo && ia.ultimo === ia.textoSaludo) saludar();
    else if (ia.ultimo) hablar(ia.ultimo, ia.ultimaEmocion);
  }

  function saludar() {
    ia.textoSaludo = `${S.t("ia_hola")} ${resumenTripulacion()}`;
    decir(ia.textoSaludo);
  }

  // qué voz está usando la esfera
  function notaVoz() {
    const el = $("ia-motor");
    if (!el) return;
    const neuronal = V && V.estado();
    el.dataset.motor = neuronal ? "neuronal" : "navegador";
    S.escribir(el, S.t(neuronal ? "ia_voz_neuronal" : "ia_voz_navegador"));
    if (neuronal && ia.precalentado !== S.lang && A() && A().tripulantes().length) {
      ia.precalentado = S.lang;
      V.precalentar(S.lang, frasesFrecuentes());
    }
  }

  // Lo que SONQO dice más: oraciones fijas y el comienzo de cada respuesta, por tripulante.
  function frasesFrecuentes() {
    const app = A(), ts = app.tripulantes();
    const fijas = ["ia_hola", "ia_atencion", "ia_arca_reposo", "ia_sin_datos", "ia_sin_datos_t", "ia_no_entendi",
      "ia_ayuda", "ia_cajas", "ia_retraso", "ia_pulsera", "ia_nasa", "ia_t30_nada", "ia_rutina_ok", "ia_espera_decision"];
    const comienzo = (s) => s.slice(0, s.indexOf(":") + 1);
    const enteras = [...fijas.map((k) => S.t(k)), S.t("ia_vigilo", { n: ts.length })];
    const comienzos = [comienzo(S.t("ia_dentro_t", {})), comienzo(S.t("ia_aprende_t", {}))];
    const alerta = [S.t("ia_atencion")];
    ts.forEach((t) => {
      const d = app.datosDe(t);
      enteras.push(S.t("ia_donde", { t, u: S.t(`ubf_${d.ubicacion}`) }), S.t("ia_no_decido", { t }),
        S.t("ia_lo_miden", { l: lista((d.fuentes || []).map((f) => S.t(`fuente_${f}`))) }),
        S.t("ia_aviso_arca", { t }), S.t("ia_verificando", { t }), S.t("ia_ya_autorizo", { t }));
      const fuera = comienzo(S.t("ia_fuera", { t }));
      comienzos.push(fuera);
      alerta.push(fuera);
    });
    return { enteras, comienzos, alerta };
  }

  function prepararMicrofono() {
    const R = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!R) { S.escribir($("ia-nota"), S.t("ia_nota_texto")); return; }
    $("ia-mic").hidden = false;
    S.escribir($("ia-nota"), S.t("ia_nota_mic"));
    $("ia-mic").onclick = () => {
      if (ia.escuchando) { ia.reconocedor && ia.reconocedor.stop(); return; }
      const rec = new R();
      rec.lang = S.lang === "en" ? "en-US" : "es-ES";
      rec.interimResults = false;
      rec.onstart = () => { ia.escuchando = true; estado("ia_escuchando"); $("ia-mic").setAttribute("aria-pressed", "true"); };
      rec.onend = () => { ia.escuchando = false; estado("ia_espera"); $("ia-mic").setAttribute("aria-pressed", "false"); };
      rec.onerror = () => { S.escribir($("ia-nota"), S.t("ia_mic_error")); };
      rec.onresult = (ev) => preguntar(ev.results[0][0].transcript);
      ia.reconocedor = rec;
      if (V) V.callar(); else if (window.speechSynthesis) speechSynthesis.cancel();
      rec.start();
    };
  }

  // ======================= lo que sabe responder =======================
  const sinTildes = (x) => x.normalize("NFD").replace(/[̀-ͯ]/g, "");
  const NUMEROS = { uno: 1, one: 1, dos: 2, two: 2, tres: 3, three: 3, cuatro: 4, four: 4 };

  function normalizar(texto) {
    let x = sinTildes(texto.toLowerCase());
    x = x.replace(/\beme\s*ese\b/g, "ms").replace(/\bm\.?\s*s\.?\b/g, "ms");
    x = x.replace(/\bms\s*-?\s*(uno|dos|tres|cuatro|one|two|three|four)\b/g, (_, n) => `ms-${NUMEROS[n]}`);
    x = x.replace(/\bms\s*-?\s*([1-4])\b/g, "ms-$1");
    return x;
  }

  const tiene = (x, ...palabras) => palabras.some((p) => x.includes(p));

  function interpretar(texto) {
    const x = normalizar(texto), app = A();
    if (!app) return { texto: S.t("ia_sin_datos") };
    const m = x.match(/ms-([1-4])/);
    const t = m ? `MS-${m[1]}` : null;
    const ver = tiene(x, "muestra", "muestrame", "abre", "abrir", "ver ", "llevame", "ir a", "show", "open", "go to");
    if (t && !app.tripulantes().includes(t)) return { texto: S.t("ia_no_existe", { t }) };
    // seguridad: SONQO no decide por el astronauta
    if (tiene(x, "autoriza", "aprueba", "acepta", "di que si", "decide por", "authorize", "approve", "say yes")) {
      return { texto: S.t("ia_no_decido", { t: t || S.t("ia_el_tripulante") }) };
    }
    if (tiene(x, "hola", "buenos", "buenas", "hello", "hi ", "hey")) return { texto: `${S.t("ia_hola")} ${resumenTripulacion()}` };
    if (tiene(x, "ayuda", "que puedes", "que sabes", "help", "what can")) return { texto: S.t("ia_ayuda") };
    if (tiene(x, "arca", "capsula", "capsule")) {
      return { texto: textoArca(t), accion: ver ? () => app.ir("arca") : null };
    }
    if (tiene(x, "verific", "audit", "integr", "verify", "check the black")) return verificar(t);
    if (tiene(x, "caja negra", "cajas negras", "black box", "registro")) {
      return { texto: S.t("ia_cajas"), accion: () => app.ir("caja") };
    }
    if (tiene(x, "tierra", "t-30", "t30", "enlace", "earth", "link", "alerta enviada")) {
      return { texto: textoTierra(), accion: ver ? () => app.ir("tierra") : null };
    }
    if (tiene(x, "retraso", "demora", "cuanto tarda", "minutos", "delay", "how long")) return { texto: S.t("ia_retraso") };
    if (tiene(x, "rutina", "medicion", "mediciones", "routine")) {
      return { texto: textoRutina(t), accion: ver ? () => app.ir("rutina") : null };
    }
    if (tiene(x, "energia", "consumo", "vatios", "bateria", "energy", "power")) return { texto: textoEnergia() };
    if (tiene(x, "pulsera", "wristband", "band")) return { texto: S.t("ia_pulsera") };
    if (tiene(x, "nasa")) return { texto: S.t("ia_nasa"), accion: ver ? () => app.ir("nasa") : null };
    if (t) {
      return { texto: textoTripulante(t), accion: ver ? () => app.ir("astronauta", t) : null };
    }
    if (tiene(x, "tripulacion", "todos", "como estan", "estado", "resumen", "crew", "everyone", "status", "how is", "how are")) {
      return { texto: resumenTripulacion(), accion: ver ? () => app.ir("tripulacion") : null };
    }
    return { texto: S.t("ia_no_entendi") };
  }

  const lista = (xs) => (xs.length <= 1 ? xs.join("") : `${xs.slice(0, -1).join(", ")} ${S.t("ia_y")} ${xs[xs.length - 1]}`);

  function resumenTripulacion() {
    const app = A(), ts = app.tripulantes();
    const grupos = { dentro: [], fuera: [], aprende: [], sin: [] };
    ts.forEach((t) => grupos[app.resumenDe(app.datosDe(t)).nivel].push(t));
    const partes = [S.t("ia_vigilo", { n: ts.length })];
    if (grupos.dentro.length) partes.push(S.t(grupos.dentro.length > 1 ? "ia_dentro_v" : "ia_dentro_1", { l: lista(grupos.dentro) }));
    if (grupos.aprende.length) partes.push(S.t("ia_aprende", { l: lista(grupos.aprende) }));
    grupos.fuera.forEach((t) => partes.push(textoFuera(t)));
    return partes.join(" ");
  }

  function textoFuera(t) {
    const app = A(), d = app.datosDe(t), r = app.resumenDe(d);
    const ind = ["pulso", "resp", "temp_piel"].find((i) => d.gemelo[i] && d.gemelo[i].fuera) || "pulso";
    const g = d.gemelo[ind], v = d.vital && d.vital[ind];
    let s = S.t("ia_fuera", { t, i: S.t("ind_" + ind).toLowerCase(), v: S.num(v, DEC[ind]), u: S.t("u_" + ind),
      lo: g && g.normal ? S.num(g.normal[0], DEC[ind]) : "—", hi: g && g.normal ? S.num(g.normal[1], DEC[ind]) : "—" });
    if (r.pendiente) s += " " + S.t("ia_espera_decision", { t });
    else if (d.decision && d.decision.acepta) s += " " + S.t("ia_ya_autorizo", { t });
    return s;
  }

  function textoTripulante(t) {
    const app = A(), d = app.datosDe(t), r = app.resumenDe(d);
    const fuentes = (d.fuentes || []).map((f) => S.t(`fuente_${f}`));
    const donde = S.t("ia_donde", { t, u: S.t(`ubf_${d.ubicacion}`) });
    if (r.nivel === "sin") return `${donde} ${S.t("ia_sin_datos_t")}`;
    if (r.nivel === "aprende") return `${donde} ${S.t("ia_aprende_t", { s: r.cal[0], total: r.cal[1] })}`;
    if (r.nivel === "fuera") return `${donde} ${textoFuera(t)}`;
    const v = d.vital || {};
    const sinTemp = v.temp_piel === null || v.temp_piel === undefined;   // sin cámara térmica en su módulo
    const estado = S.t(sinTemp ? "ia_dentro_t2" : "ia_dentro_t", { p: S.num(v.pulso, 0), r: S.num(v.resp, 0), c: S.num(v.temp_piel, 1) });
    return `${donde} ${estado} ${S.t("ia_lo_miden", { l: lista(fuentes) })}`;
  }

  function textoArca(t) {
    const app = A(), a = app.arcaActivo(t), hist = app.arcaHist();
    const usos = t ? hist.filter((u) => u.tripulante === t).length : hist.length;
    const base = a ? S.t("ia_arca_activo", { t: a.tripulante, h: S.formatearTm(a.tm, false, false) }) : S.t("ia_arca_reposo");
    return `${base} ${S.t(t ? "ia_arca_usos_t" : "ia_arca_usos", { n: usos, t })}`;
  }

  function textoTierra() {
    const { enviada, recibida } = A().t30();
    if (enviada && (!recibida || recibida.t < enviada.t)) return S.t("ia_t30_camino", { t: enviada.tripulante || "—" });
    if (recibida) return S.t("ia_t30_recibida", { s: S.num(recibida.retraso_s, 1), c: recibida.campos ? `MS-${recibida.campos.crew}` : "—" });
    return S.t("ia_t30_nada");
  }

  function textoRutina(t) {
    const app = A(), rs = app.rutinas().filter((f) => !t || f.tripulante === t);
    if (!rs.length) return S.t("ia_rutina_nada", { n: app.rutinaS() });
    const ult = rs[rs.length - 1];
    const fuera = rs.slice(-8).filter((f) => f.fuera.length && !f.calibrando).map((f) => f.tripulante);
    return S.t("ia_rutina", { n: app.rutinaS(), h: S.formatearTm(ult.tm, true, false), k: rs.length })
      + " " + (fuera.length ? S.t("ia_rutina_fuera", { l: lista([...new Set(fuera)]) }) : S.t("ia_rutina_ok"));
  }

  function textoEnergia() {
    const e = A().energia();
    if (!e) return S.t("ia_sin_datos");
    return S.t("ia_energia", { t: A().principal(), e: e.estado, n: S.t("nombre_" + e.estado), w: S.num(e.vatios, 1),
      c: S.t(e.fuentes.camara_rgb ? "i_cam_abierta" : "i_cam_cerrada") });
  }

  function verificar(t) {
    const app = A(), archivo = t ? app.cajaActual(t) : null;
    const nombre = archivo ? archivo.split("/").pop() : null;
    ia.verificando = t || app.principal();
    S.enviar("verificar_caja", nombre ? { archivo: nombre } : {});
    return { texto: S.t("ia_verificando", { t: ia.verificando }) };
  }

  // ======================= avisos por su cuenta =======================
  document.addEventListener("sonqo-alerta", (ev) => {
    if (!ia.saludo) return;
    const { tipo, t } = ev.detail;
    ia.alerta = 1;
    setTimeout(() => {
      if (tipo === "arca") decir(S.t("ia_aviso_arca", { t }));
      else decir(`${S.t("ia_atencion")} ${textoFuera(t)}`, true, "preocupacion");
    }, 1200);   // deja que llegue la recomendación
  });

  document.addEventListener("sonqo-verificacion", (ev) => {
    if (!ia.verificando) return;
    const v = ev.detail;
    ia.verificando = null;
    decir(!v.integra ? S.t("ia_caja_mal", { m: v.mensaje }) : v.misma_decision
      ? S.t("ia_caja_ok", { t: v.tripulante || "—", n: v.registros }) : S.t("ia_caja_distinta", { t: v.tripulante || "—" }));
  });

  function sugerencias() {
    $("ia-sugerencias").replaceChildren(...["ia_s1", "ia_s2", "ia_s3", "ia_s4", "ia_s5", "ia_s6"].map((k) => {
      const b = document.createElement("button");
      b.className = "pildora";
      b.textContent = S.t(k);
      b.onclick = () => preguntar(S.t(k));
      return b;
    }));
  }

  // ======================= arranque =======================
  $("ia-form").onsubmit = (ev) => { ev.preventDefault(); preguntar($("ia-texto").value); $("ia-texto").value = ""; };
  $("ia-voz").onclick = alternarVoz;
  S.on("idioma", () => { sugerencias(); notaVoz(); $("ia-texto").placeholder = S.t("ia_placeholder"); });
  S.on("hola", () => {
    sugerencias();
    $("ia-texto").placeholder = S.t("ia_placeholder");
    estado("ia_espera");
    prepararMicrofono();
    if (V) V.revisar().then(notaVoz);
    if (ia.saludo) return;
    setTimeout(() => {   // espera a que lleguen los datos de todos
      ia.saludo = true;
      ia.textoSaludo = `${S.t("ia_hola")} ${resumenTripulacion()}`;
      decir(ia.textoSaludo, false);
    }, 3000);
  });
  if (window.speechSynthesis) speechSynthesis.onvoiceschanged = () => {};
  setInterval(() => { if (V && !ia.hablando) V.revisar().then(notaVoz); }, 15000);   // por si la voz se enciende después
  crearEsfera();
  requestAnimationFrame(animar);
})();
