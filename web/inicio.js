// El inicio: una frase grande que dice lo importante ahora, armada con los datos de la tripulación.
// «MS-3 está fuera de su normal. Los otros 3, bien.» y, debajo, el detalle del desvío.
(() => {
  const S = SONQO;
  const $ = (id) => document.getElementById(id);
  const INDS = ["pulso", "resp", "temp_piel"];
  const DEC = { pulso: 0, resp: 0, temp_piel: 1 };

  const lista = (xs) => (xs.length <= 1 ? xs.join("") : `${xs.slice(0, -1).join(", ")} ${S.t("ia_y")} ${xs[xs.length - 1]}`);

  // El desvío del primer tripulante fuera: «Pulso de 141 lpm cuando lo habitual es 52–61.»
  function detalleDe(app, t) {
    const d = app.datosDe(t), r = app.resumenDe(d);
    const ind = INDS.find((i) => d.gemelo[i] && d.gemelo[i].fuera) || "pulso";
    const g = d.gemelo[ind], v = d.vital && d.vital[ind];
    const datos = { ind: S.t("ind_" + ind), v: S.num(v, DEC[ind]), u: S.t("u_" + ind) };
    let s = g && g.normal
      ? S.t("ini_detalle", { ...datos, lo: S.num(g.normal[0], DEC[ind]), hi: S.num(g.normal[1], DEC[ind]) })
      : S.t("ini_detalle_sin", datos);
    if (r.pendiente) s += " " + S.t("ini_espera");
    return s;
  }

  // Sin efectos: la usa la pantalla y la prueban con datos falsos.
  function titular(app) {
    const ts = app.tripulantes();
    const nivel = Object.fromEntries(ts.map((t) => [t, app.resumenDe(app.datosDe(t)).nivel]));
    const de = (n) => ts.filter((t) => nivel[t] === n);
    const fuera = de("fuera"), aprende = de("aprende");
    if (fuera.length) {
      const otros = ts.length - fuera.length;
      return {
        linea1: fuera.length === 1 ? S.t("ini_fuera_1", { t: fuera[0] }) : S.t("ini_fuera_v", { l: lista(fuera) }),
        linea2: otros ? S.t("ini_otros", { k: otros }) : "",
        detalle: detalleDe(app, fuera[0]),
      };
    }
    if (!ts.length || de("sin").length) return { linea1: S.t("ini_esperando"), linea2: "", detalle: "" };
    if (aprende.length) return { linea1: S.t("ini_todos_bien"), linea2: S.t("ini_aprendo", { l: lista(aprende) }), detalle: "" };
    return { linea1: S.t("ini_todos"), linea2: S.t("ini_vigilados", { n: ts.length }), detalle: "" };
  }

  function dibujar() {
    const app = window.SONQO_APP;
    if (!app || !$("ini-l1")) return;
    const f = titular(app);
    S.escribir($("ini-l1"), f.linea1);
    S.escribir($("ini-l2"), f.linea2);
    S.escribir($("ini-detalle"), f.detalle);
    $("ini-hero").classList.toggle("alerta", f.detalle !== "");
  }

  S.on("idioma", dibujar);
  setInterval(dibujar, 1000);
  window.SONQO_INICIO = { titular };
})();
