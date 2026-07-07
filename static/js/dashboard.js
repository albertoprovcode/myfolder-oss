import { get, esc } from "./api.js";
import { donut, bars, stacked } from "./charts.js";
import { t, fmtNum } from "./i18n.js";

const root = () => document.getElementById("view-dashboard");

// Mapa de etiquetas de antigüedad del backend (español) → clave i18n.
const AGE_KEY = {
  "0-30d": "age.0_30d",
  "30-90d": "age.30_90d",
  "90d-1a": "age.90d_1y",
  "1-2a": "age.1_2y",
  ">2a": "age.gt2y",
};

function kpi(big, label, warn, extra) {
  // Estilo MVP: etiqueta arriba, dato debajo, línea de contexto opcional.
  return `<div class="card${warn ? " warn" : ""}"><div class="muted">${esc(label)}</div><div class="big">${esc(big)}</div>${extra ? `<div class="muted">${esc(extra)}</div>` : ""}</div>`;
}

export async function init() {
  const el = root();
  el.innerHTML = `<p class="muted">${t("common.loading")}</p>`;
  try {
    const [s, sp, rem] = await Promise.all([get("/api/summary"), get("/api/space"), get("/api/removable")]);
    el.innerHTML = `
      ${s.crawling ? `<div class="banner">${t("dashboard.crawling_banner")}</div>` : ""}
      <div class="cards">
        ${kpi(fmtNum(s.files), t("dashboard.files"))}
        ${kpi(fmtNum(s.dirs), t("dashboard.dirs"))}
        ${kpi(sp.free_h, t("dashboard.free_space"))}
        ${kpi((100 - (sp.free_percent ?? 0)) + "%", t("dashboard.occupied"))}
        ${kpi(rem.size_h, t("dashboard.recoverable_cold"), true, t("dashboard.n_files", { n: fmtNum(rem.count) }))}
      </div>
      <div class="row">
        <div class="panel"><h2>${t("dashboard.disk_space")}</h2><div id="d-space"></div></div>
        <div class="panel"><h2>${t("dashboard.age")} <span id="d-age-toggle"></span></h2><div id="d-age" class="chart"></div></div>
      </div>
      <div class="row">
        <div class="panel"><h2>${t("dashboard.usage_by_type")}</h2><div id="d-types" class="chart"></div></div>
        <div class="panel"><h2>${t("dashboard.top_ext")}</h2><div id="d-ext" class="chart"></div></div>
      </div>
      <div class="tables">
        <div class="panel"><h2>${t("dashboard.largest_files")}</h2><div class="scroll"><table id="d-files"></table></div></div>
        <div class="panel"><h2>${t("dashboard.largest_dirs")}</h2><div class="scroll"><table id="d-dirs"></table></div></div>
      </div>`;

    // Espacio: barra usado/libre
    const used = Math.max(0, Math.min(100, 100 - (sp.free_percent ?? 0)));
    el.querySelector("#d-space").innerHTML =
      `<div class="bar" style="width:${used}%;background:var(--warn)"></div>
       <p class="muted">${esc(t("dashboard.used_free_total", { used: sp.used_h, free: sp.free_h, total: sp.total_h }))}</p>`;

    // Antigüedad con conmutador Modificado/Accedido
    const ageEl = el.querySelector("#d-age");
    const toggle = el.querySelector("#d-age-toggle");
    toggle.innerHTML = `<button class="btn ghost" data-f="mtime">${t("dashboard.mod")}</button><button class="btn ghost" data-f="atime">${t("dashboard.acc")}</button>`;
    async function drawAge(field) {
      const a = await get("/api/age", { field });
      const buckets = a.buckets.map(b => ({ ...b, label: t(AGE_KEY[b.label] || "age.unknown") }));
      stacked(ageEl, buckets);
    }
    toggle.querySelectorAll("button").forEach(b => b.addEventListener("click", () => drawAge(b.dataset.f)));

    // Todo EN PARALELO: cada bloque pinta en cuanto llegan sus datos.
    // En serie, la carga era la SUMA de las 5 consultas pesadas.
    await Promise.all([
      drawAge("mtime"),
      get("/api/types").then(tp =>
        donut(el.querySelector("#d-types"), tp.items.map(i => ({ ...i, category: t("cat." + i.category) })), { nameKey: "category", valueKey: "size" })),
      get("/api/extensions", { by: "size", limit: 8 }).then(ext =>
        bars(el.querySelector("#d-ext"), ext.items, { nameKey: "ext", valueKey: "size" })),
      get("/api/top/files", { limit: 20 }).then(tf => {
        el.querySelector("#d-files").innerHTML =
          `<thead><tr><th>${t("common.name")}</th><th>${t("common.size")}</th></tr></thead><tbody>` +
          tf.items.map(i => `<tr><td data-label="${esc(t("common.name"))}" title="${esc(i.path)}">${esc(i.name)}</td><td data-label="${esc(t("common.size"))}">${esc(i.size_h)}</td></tr>`).join("") +
          `</tbody>`;
      }),
      get("/api/top/dirs", { limit: 20 }).then(td => {
        el.querySelector("#d-dirs").innerHTML =
          `<thead><tr><th>${t("dashboard.folder")}</th><th>${t("common.size")}</th></tr></thead><tbody>` +
          td.items.map(i => `<tr><td data-label="${esc(t("dashboard.folder"))}" title="${esc(i.path)}">${esc(i.name)}</td><td data-label="${esc(t("common.size"))}">${esc(i.size_h)}</td></tr>`).join("") +
          `</tbody>`;
      }),
    ].map(p => Promise.resolve(p).catch(e => console.error("dashboard:", e))));
  } catch (e) {
    console.error(e);
    el.innerHTML = `<p class="error">${t("dashboard.load_error")}</p>`;
  }
}
