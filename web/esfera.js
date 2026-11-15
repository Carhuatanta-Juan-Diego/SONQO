// La esfera de SONQO: un globo sólido y luminoso (cian → lavanda → azul profundo) con brillo arriba a la
// izquierda y un halo suave debajo. Respira en reposo, su borde ondula apenas al hablar, cada latido de una
// pulsera le cruza un reflejo desde el lado donde orbita esa pulsera. WebGL puro, sin librerías ni internet.
(() => {
  // un triángulo que cubre todo el lienzo: la esfera se pinta píxel a píxel en el fragment shader
  const VS = `
attribute vec2 pos;
void main(){ gl_Position = vec4(pos, 0.0, 1.0); }`;

  const FS = `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
uniform vec2 res;
uniform float t, voz, alerta, escucha, aspecto, radio, sube;
uniform vec4 ondas[4];      // xyz: de dónde viene el reflejo; w: hace cuánto latió (s)
uniform vec4 fuerza;        // fuerza del reflejo de cada pulsera (más si está fuera de su normal)

vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
vec4 taylor(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1.0/6.0,1.0/3.0); const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.0-g; vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx; vec3 x2=x0-i2+C.yyy; vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=0.142857142857; vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.0*floor(p*ns.z*ns.z); vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.0*x_);
  vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy; vec4 h=1.0-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0; vec4 s1=floor(b1)*2.0+1.0; vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y); vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylor(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
  vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0); m=m*m;
  return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}

// el degradado del boceto: #dff8ff 0 % → #89e5fc 35 % → #6889f7 75 % → #3c4fb8 100 %
vec3 degradado(float g){
  vec3 c0=vec3(0.875,0.973,1.0), c1=vec3(0.537,0.898,0.988), c2=vec3(0.408,0.537,0.969), c3=vec3(0.235,0.31,0.722);
  if (g < 0.35) return mix(c0, c1, g / 0.35);
  if (g < 0.75) return mix(c1, c2, (g - 0.35) / 0.4);
  return mix(c2, c3, clamp((g - 0.75) / 0.25, 0.0, 1.0));
}

void main(){
  vec2 uv = gl_FragCoord.xy / res * 2.0 - 1.0;
  vec2 q = vec2(uv.x * aspecto, uv.y - sube) / radio;        // en radios de la esfera
  float ang = atan(q.y, q.x);
  vec3 sobre = vec3(cos(ang), sin(ang), 0.0);
  // el borde: respira y ondula apenas; al hablar, un poco más
  float borde = 1.0 + 0.012 * sin(t * 1.05)
              + 0.005 * snoise(sobre * 1.2 + vec3(0.0, 0.0, t * 0.18))
              + voz * 0.035 * snoise(sobre * 2.2 + vec3(0.0, 0.0, t * 1.6));
  float d = length(q) / borde;
  float px = 2.0 / (res.y * radio);                          // un píxel, en radios

  // halo debajo, como la sombra de color del boceto
  float halo = smoothstep(1.5, 0.8, length(q - vec2(0.0, -0.25))) * (0.26 + 0.22 * voz);
  vec3 colHalo = mix(vec3(0.53, 0.63, 1.0), vec3(0.95, 0.35, 0.3), alerta * 0.8);

  // el cuerpo
  vec2 s = q / borde;
  vec3 n = vec3(s, sqrt(max(0.0, 1.0 - dot(s, s))));
  float g = length(s - vec2(-0.2, 0.3)) / 1.3;
  vec3 col = degradado(g);
  col = mix(col, mix(vec3(1.0, 0.72, 0.66), vec3(0.85, 0.18, 0.13), g), alerta * 0.75);   // alerta: rojo
  col = mix(col, mix(vec3(0.82, 1.0, 0.97), vec3(0.05, 0.62, 0.72), g), escucha * 0.45);  // escucha: verde agua
  float sombra = smoothstep(0.5, 1.0, d) * max(0.0, dot(normalize(q + 1e-5), vec2(0.6, -0.8))) * 0.28;
  col *= 1.0 - sombra;                                       // sombra interior abajo a la derecha
  col += vec3(0.06) * voz;                                   // al hablar, se enciende
  for (int i = 0; i < 4; i++) {                              // reflejos de los latidos
    float edad = ondas[i].w;
    float a = acos(clamp(dot(n, ondas[i].xyz), -1.0, 1.0));
    float frente = a - edad * 2.4;
    float o = exp(-edad * 1.8) * exp(-frente * frente * 14.0) * fuerza[i];
    col = mix(col, vec3(1.0), clamp(o * 0.32, 0.0, 0.5));
  }
  float cuerpo = clamp((1.0 - d) / px, 0.0, 1.0);            // borde suave, sin dientes

  vec3 fin = mix(colHalo, col, cuerpo);
  float alfa = max(cuerpo, halo * (1.0 - cuerpo));
  gl_FragColor = vec4(fin, alfa);
}`;

  // satélites: las pulseras que orbitan
  const VS_SAT = `
attribute vec4 sat;   // xy en pantalla (ya proyectado), w: tamaño
attribute vec4 color;
uniform float dpr;
varying vec4 c;
void main(){ gl_Position = vec4(sat.xy, 0.0, 1.0); gl_PointSize = sat.w * dpr; c = color; }`;
  const FS_SAT = `
precision mediump float;
varying vec4 c;
void main(){
  float d = length(gl_PointCoord - 0.5);
  float nucleo = smoothstep(0.16, 0.05, d), halo = smoothstep(0.5, 0.0, d) * 0.25;
  gl_FragColor = vec4(c.rgb, (nucleo + halo) * c.a);         // translúcido: sin cuadro alrededor
}`;

  const ORBITA = 1.62, ESCALA = 2.55, DIST = 4.2, SUBE = 0.08;

  function compilar(gl, tipo, src) {
    const s = gl.createShader(tipo);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  }

  function programa(gl, vs, fs) {
    const p = gl.createProgram();
    gl.attachShader(p, compilar(gl, gl.VERTEX_SHADER, vs));
    gl.attachShader(p, compilar(gl, gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    return p;
  }

  // dónde está la pulsera i en el espacio (órbita inclinada alrededor de la esfera)
  function posSatelite(i, t) {
    const a = t * 0.09 + i * Math.PI / 2 + 0.6;
    const x = Math.cos(a) * ORBITA, z = Math.sin(a) * ORBITA, y = Math.sin(a + 0.9) * 0.42 + (i % 2 ? 0.18 : -0.18);
    return [x, y, z];
  }

  function proyectar([x, y, z], aspecto) {
    const k = ESCALA / (DIST - z);
    return [x * k / aspecto, y * k + SUBE];
  }

  function crear(canvas) {
    const gl = canvas.getContext("webgl", { antialias: false, alpha: true, premultipliedAlpha: false });
    if (!gl) return null;
    const p = programa(gl, VS, FS), ps = programa(gl, VS_SAT, FS_SAT);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const bufSat = gl.createBuffer(), bufCol = gl.createBuffer();
    const U = {};
    ["res", "t", "voz", "alerta", "escucha", "aspecto", "radio", "sube", "ondas", "fuerza"]
      .forEach((n) => (U[n] = gl.getUniformLocation(p, n)));
    const aPos = gl.getAttribLocation(p, "pos");
    const aSat = gl.getAttribLocation(ps, "sat"), aCol = gl.getAttribLocation(ps, "color"), uDprSat = gl.getUniformLocation(ps, "dpr");

    const st = {
      voz: 0, alerta: 0, escucha: 0,
      pulseras: [],                       // [{nivel: 'dentro'|'fuera'|..., latio: t, activa}]
      etiquetas: [],                      // posiciones en pantalla para el HTML (px)
    };
    const ondas = new Float32Array(16), fuerza = new Float32Array(4);

    function dibujar(ms) {
      const t = ms / 1000;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = canvas.clientWidth, h = canvas.clientHeight;
      if (!w || !h) return;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      }
      const aspecto = w / h;
      // si la escena es angosta, la esfera se achica para que quepa a lo ancho
      const escala = ESCALA * Math.min(1, aspecto * 1.05);
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.enable(gl.BLEND);
      // mezcla normal (fondo claro); el alfa se acumula bien para que la página se vea a través
      gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);

      // reflejos de las pulseras: salen del lado de la esfera que mira a cada pulsera
      const sats = [];
      for (let i = 0; i < 4; i++) {
        const s = posSatelite(i, t), n = Math.hypot(...s);
        const pu = st.pulseras[i];
        ondas.set([s[0] / n, s[1] / n, s[2] / n, pu && pu.latio ? t - pu.latio : 99], i * 4);
        fuerza[i] = !pu || !pu.activa ? 0 : pu.nivel === "fuera" ? 1.0 : 0.45;
        sats.push(s);
      }

      gl.useProgram(p);
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.enableVertexAttribArray(aPos);
      gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);
      gl.uniform2f(U.res, canvas.width, canvas.height);
      gl.uniform1f(U.t, t); gl.uniform1f(U.voz, st.voz); gl.uniform1f(U.alerta, st.alerta);
      gl.uniform1f(U.escucha, st.escucha); gl.uniform1f(U.aspecto, aspecto);
      gl.uniform1f(U.radio, escala / DIST); gl.uniform1f(U.sube, SUBE);
      gl.uniform4fv(U.ondas, ondas); gl.uniform4fv(U.fuerza, fuerza);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      gl.disableVertexAttribArray(aPos);

      // pulseras en órbita: detrás de la esfera (que ahora es sólida) se ocultan
      const pos = [], col = [];
      st.etiquetas = sats.map((s, i) => {
        const [x0, y0] = proyectar(s, aspecto), x = x0 * escala / ESCALA, y = (y0 - SUBE) * escala / ESCALA + SUBE;
        const pu = st.pulseras[i] || {};
        const detras = s[2] < 0 && Math.hypot(x * aspecto, y - SUBE) < 1.05 * escala / DIST;
        const latido = pu.latio ? Math.exp(-(t - pu.latio) * 5) : 0;
        const tam = (10 + 5 * (s[2] + ORBITA) / (2 * ORBITA)) * (1 + 0.8 * latido);
        const c = pu.nivel === "fuera" ? [0.85, 0.18, 0.13] : pu.nivel === "aprende" ? [0.77, 0.4, 0.1] : [0.41, 0.54, 0.97];
        const a = detras ? 0 : !pu.activa ? 0.25 : 0.7 + 0.6 * latido;
        pos.push(x, y, 0, tam * 2.2); col.push(...c, a);
        return { x: (x + 1) / 2 * w, y: (1 - y) / 2 * h, detras, frente: s[2] };
      });
      gl.useProgram(ps);
      gl.uniform1f(uDprSat, dpr);
      gl.bindBuffer(gl.ARRAY_BUFFER, bufSat);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(pos), gl.DYNAMIC_DRAW);
      gl.enableVertexAttribArray(aSat);
      gl.vertexAttribPointer(aSat, 4, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, bufCol);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(col), gl.DYNAMIC_DRAW);
      gl.enableVertexAttribArray(aCol);
      gl.vertexAttribPointer(aCol, 4, gl.FLOAT, false, 0, 0);
      gl.drawArrays(gl.POINTS, 0, 4);
      gl.disableVertexAttribArray(aSat); gl.disableVertexAttribArray(aCol);
    }

    return { st, dibujar };
  }

  window.SONQO_ESFERA = { crear };
})();
