// La voz de la esfera: la voz neuronal local (voz/servidor_voz.py, IndexTTS-2.5) por /api/voz,
// o la voz del navegador si esa no está arriba. Mide el volumen para que la esfera hable.
(() => {
  const SR = 22050;

  // ======================= el texto, como se dice =======================
  // El modelo lee las letras tal cual: las cifras y las siglas se pasan a palabras.
  const ES = {
    u: ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez",
      "once", "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte",
      "veintiuno", "veintidós", "veintitrés", "veinticuatro", "veinticinco", "veintiséis", "veintisiete", "veintiocho", "veintinueve"],
    d: ["", "", "", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa"],
    c: ["", "ciento", "doscientos", "trescientos", "cuatrocientos", "quinientos", "seiscientos", "setecientos", "ochocientos", "novecientos"],
  };
  const EN = {
    u: ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
      "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"],
    d: ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"],
  };

  function enteroEs(n) {
    if (n < 30) return ES.u[n];
    if (n < 100) return ES.d[Math.floor(n / 10)] + (n % 10 ? ` y ${ES.u[n % 10]}` : "");
    if (n === 100) return "cien";
    if (n < 1000) return ES.c[Math.floor(n / 100)] + (n % 100 ? ` ${enteroEs(n % 100)}` : "");
    if (n < 1e6) {
      const m = Math.floor(n / 1000);
      return (m === 1 ? "mil" : `${enteroEs(m).replace(/uno$/, "un")} mil`) + (n % 1000 ? ` ${enteroEs(n % 1000)}` : "");
    }
    return String(n);
  }

  function enteroEn(n) {
    if (n < 20) return EN.u[n];
    if (n < 100) return EN.d[Math.floor(n / 10)] + (n % 10 ? `-${EN.u[n % 10]}` : "");
    if (n < 1000) return `${EN.u[Math.floor(n / 100)]} hundred` + (n % 100 ? ` ${enteroEn(n % 100)}` : "");
    if (n < 1e6) return `${enteroEn(Math.floor(n / 1000))} thousand` + (n % 1000 ? ` ${enteroEn(n % 1000)}` : "");
    return String(n);
  }

  function numero(txt, en) {
    const entero = en ? enteroEn : enteroEs;
    const [a, b] = txt.split(en ? "." : ",");
    let s = entero(parseInt(a.replace(/[.,\s]/g, ""), 10));
    if (b) s += (en ? " point " : " coma ") + (b.length <= 2 && !b.startsWith("0") ? entero(parseInt(b, 10)) : [...b].map((d) => entero(+d)).join(" "));
    return s;
  }

  function paraVoz(texto, lang, conPunto = true) {
    const en = lang === "en", entero = en ? enteroEn : enteroEs;
    let x = ` ${texto} `;
    const reglas = en ? [
      [/\bMS-(\d)/g, (_, n) => `M S ${entero(+n)}`], [/\bT-30\b/g, "T thirty"], [/\bN(\d)\b/g, (_, n) => `N ${entero(+n)}`],
      [/\bE(\d)\b/g, (_, n) => `E ${entero(+n)}`], [/(\d)\s*bpm\b/g, "$1 beats per minute"], [/(\d)\s*rpm\b/g, "$1 breaths per minute"], [/(\d)\s*br\/min\b/g, "$1 breaths per minute"],
      [/(\d)\s*°C/g, "$1 degrees"], [/(\d)\s*W\b/g, "$1 watts"], [/(\d)\s*s\b/g, "$1 seconds"], [/(\d)\s*%/g, "$1 percent"],
      [/\bCRC\b/g, "C R C"], [/\bOSDR\b/g, "O S D R"], [/\bNASA-STD-3001\b/g, "the NASA standard three thousand one"],
    ] : [
      // «MS-2» → «Eeme ese dos»: con «eme» a secas el modelo se come la «e» y se oye «mm»
      [/\bMS-(\d)/g, (_, n) => `Eeme ese ${entero(+n)}`], [/\bT-30\b/g, "te treinta"], [/\bN(\d)\b/g, (_, n) => `ene ${entero(+n)}`],
      [/\bE(\d)\b/g, (_, n) => `e ${entero(+n)}`], [/(\d)\s*lpm\b/g, "$1 latidos por minuto"], [/(\d)\s*rpm\b/g, "$1 respiraciones por minuto"],
      [/(\d)\s*°C/g, "$1 grados"], [/(\d)\s*W\b/g, "$1 vatios"], [/(\d)\s*s\b/g, "$1 segundos"], [/(\d)\s*%/g, "$1 por ciento"],
      [/\bCRC\b/g, "ce erre ce"], [/\bOSDR\b/g, "o ese de erre"], [/\bRAD\b/g, "rad"], [/\bNASA-STD-3001\b/g, "el estándar de NASA tres mil uno"],
    ];
    reglas.forEach(([re, por]) => { x = x.replace(re, por); });
    // el modelo lee «Sonqo» como «Qoncho»: se escribe como suena
    x = x.replace(/\bsonqo\b/gi, "Sonko").replace(/\bARCA\b/g, "Arca");
    // horas 03:12 o 03:12:00
    x = x.replace(/\b(\d{1,2}):(\d{2})(?::\d{2})?\b/g, (_, h, m) => (en
      ? `${entero(+h)} ${+m ? (+m < 10 ? "oh " : "") + entero(+m) : "hundred"}`
      : `${entero(+h)}${+m ? ` y ${entero(+m)}` : " en punto"}`));
    // sin comerse el punto final: "llevo 5." no es un decimal
    x = x.replace(en ? /\d+(?:,\d{3})*(?:\.\d+)?/g : /\d+(?:\.\d{3})*(?:,\d+)?/g, (m, i, todo) => {
      const s = numero(m, en);
      // "141 latidos" → "ciento cuarenta y un latidos"; "21 latidos" → "veintiún latidos"
      return !en && /^ [a-záéíóúñ]/i.test(todo.slice(i + m.length, i + m.length + 2)) && !m.includes(",")
        ? s.replace(/veintiuno$/, "veintiún").replace(/uno$/, "un") : s;
    });
    x = x.replace(/[«»]/g, "").replace(/…/g, ".").replace(/\s+/g, " ").trim();
    if (conPunto && !/[.!?:,]$/.test(x)) x += ".";
    return x;
  }

  // ======================= la voz neuronal =======================
  const v = { ok: null, ctx: null, analizador: null, onda: null, ctrl: null, fuentes: [], fin: 0, abierto: false, alTerminar: null };

  async function revisar() {
    try {
      const r = await fetch("/api/voz", { cache: "no-store" });
      v.ok = Boolean((await r.json()).ok);
    } catch { v.ok = false; }
    return v.ok;
  }

  // El audio se abre con un clic (regla de los navegadores): se llama desde el botón «Voz».
  function abrirAudio() {
    if (!v.ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      v.ctx = new AC();
      v.analizador = v.ctx.createAnalyser();
      v.analizador.fftSize = 1024;
      v.onda = new Float32Array(v.analizador.fftSize);
      v.analizador.connect(v.ctx.destination);
    }
    if (v.ctx.state === "suspended") v.ctx.resume();
    return v.ctx;
  }

  function callar() {
    if (v.ctrl) v.ctrl.abort();
    v.ctrl = null;
    v.fuentes.forEach((s) => { try { s.stop(); } catch { /* ya terminó */ } });
    v.fuentes = [];
    v.abierto = false;
    if (window.speechSynthesis) speechSynthesis.cancel();
  }

  function programar(i16) {
    const ctx = v.ctx, buf = ctx.createBuffer(1, i16.length, SR), f = new Float32Array(i16.length);
    for (let k = 0; k < i16.length; k++) f[k] = i16[k] / 32768;
    buf.copyToChannel(f, 0);   // Brave altera lo que se lee con getChannelData: se copia, no se escribe encima
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(v.analizador);
    const t0 = Math.max(v.fin, ctx.currentTime + 0.04);
    src.start(t0);
    v.fin = t0 + buf.duration;
    v.fuentes.push(src);
    src.onended = () => {
      v.fuentes = v.fuentes.filter((s) => s !== src);
      if (!v.fuentes.length && !v.abierto && v.alTerminar) v.alTerminar();
    };
  }

  // Lee el audio a medida que llega y lo pone en cola, trozo tras trozo, sin huecos.
  async function decirNeuronal(texto, { emocion = "neutral", lang = "es", alEmpezar, alTerminar } = {}) {
    callar();
    const ctx = abrirAudio();
    if (!ctx) throw new Error("sin audio");
    const ctrl = new AbortController();
    v.ctrl = ctrl; v.abierto = true; v.alTerminar = alTerminar; v.fin = 0;
    const r = await fetch("/api/voz/decir", {
      method: "POST", headers: { "Content-Type": "application/json" }, signal: ctrl.signal,
      body: JSON.stringify({ texto: paraVoz(texto, lang), emocion, idioma: lang }),
    });
    if (!r.ok || !r.body) { v.abierto = false; throw new Error(`voz ${r.status}`); }
    const lector = r.body.getReader();
    let resto = new Uint8Array(0), empezo = false;
    try {
      for (;;) {
        const { done, value } = await lector.read();
        if (done) break;
        const junto = new Uint8Array(resto.length + value.length);
        junto.set(resto); junto.set(value, resto.length);
        const util = junto.length - (junto.length % 2);
        if (util < SR * 0.12 * 2) { resto = junto; continue; }   // espera al menos 120 ms de audio
        programar(new Int16Array(junto.slice(0, util).buffer));
        resto = junto.slice(util);
        if (!empezo) { empezo = true; if (alEmpezar) alEmpezar(); }
      }
      if (resto.length >= 2) programar(new Int16Array(resto.slice(0, resto.length - (resto.length % 2)).buffer));
    } catch (e) {
      if (e.name === "AbortError") return;
      throw e;
    } finally {
      if (v.ctrl === ctrl) v.abierto = false;
    }
    if (!empezo && alEmpezar) alEmpezar();
    if (!v.fuentes.length && alTerminar) alTerminar();
  }

  // Las frases que SONQO dice más quedan en la caché de la voz y suenan al instante.
  // Se mandan enteras por oración, y los comienzos («eme ese dos está fuera de su normal:»), ya en palabras.
  function oraciones(texto, lang) {
    return paraVoz(texto, lang).split(/(?<=[.!?])\s+/).map((s) => s.trim()).filter(Boolean);
  }

  async function precalentar(lang, { enteras = [], comienzos = [], alerta = [] }) {
    const frases = [...new Set([...enteras.flatMap((t) => oraciones(t, lang)), ...comienzos.map((t) => paraVoz(t, lang, false))])];
    const pedir = (lista, emocion) => fetch("/api/voz/precargar", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frases: lista, idioma: lang, emocion }),
    }).then((r) => r.json()).catch(() => ({}));
    const a = await pedir(frases, "neutral");
    const b = await pedir(alerta.map((t) => paraVoz(t, lang, false)), "preocupacion");
    return (a.faltan || 0) + (b.faltan || 0);
  }

  // volumen de lo que suena ahora (0 a 1), para la esfera
  function nivel() {
    if (!v.analizador || !v.fuentes.length) return 0;
    v.analizador.getFloatTimeDomainData(v.onda);
    let s = 0;
    for (let k = 0; k < v.onda.length; k++) s += v.onda[k] * v.onda[k];
    return Math.min(1, Math.sqrt(s / v.onda.length) * 5);
  }

  window.SONQO_VOZ = { revisar, abrirAudio, decirNeuronal, callar, nivel, paraVoz, precalentar, estado: () => v.ok };
})();
