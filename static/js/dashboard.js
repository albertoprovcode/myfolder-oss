import { get, esc } from "./api.js";
import { donut, bars, stacked } from "./charts.js";

const root = () => document.getElementById("view-dashboard");

function kpi(big, label, warn, extra) {
  // Estilo MVP: etiqueta arriba, dato debajo, línea de contexto opcional.
  return `<div class="card${warn ? " warn" : ""}"><div class="muted">${esc(label)}</div><div class="big">${esc(big)}</div>${extra ? `<div class="muted">${esc(extra)}</div>` : ""}</div>`;
}
function num(n) { return new Intl.NumberFormat("es-ES").format(n ?? 0); }

export async function init() {
  const el = root();
  el.innerHTML = `<p class="muted">Cargando…</p>`;
  try {
    const [s, sp, rem] = await Promise.all([get("/api/summary"), get("/api/space"), get("/api/removable")]);
    el.innerHTML = `
      ${s.crawling ? `<div class="banner">⏳ Indexado en curso — cifras provisionales, se irán completando.</div>` : ""}
      <div class="cards">
        ${kpi(num(s.files), "Archivos")}
        ${kpi(num(s.dirs), "Carpetas")}
        ${kpi(sp.free_h, "Espacio libre")}
        ${kpi((100 - (sp.free_percent ?? 0)) + "%", "Ocupado")}
        ${kpi(rem.size_h, "Recuperable (frío)", true, num(rem.count) + " archivos")}
      </div>
      <div class="row">
        <div class="panel"><h2>Espacio en disco</h2><div id="d-space"></div></div>
        <div class="panel"><h2>Antigüedad <span id="d-age-toggle"></span></h2><div id="d-age" class="chart"></div></div>
      </div>
      <div class="row">
        <div class="panel"><h2>Uso por tipo</h2><div id="d-types" class="chart"></div></div>
        <div class="panel"><h2>Top extensiones (por tamaño)</h2><div id="d-ext" class="chart"></div></div>
      </div>
      <div class="tables">
        <div class="panel"><h2>Archivos más grandes</h2><div class="scroll"><table id="d-files"></table></div></div>
        <div class="panel"><h2>Carpetas más grandes</h2><div class="scroll"><table id="d-dirs"></table></div></div>
      </div>`;

    // Espacio: barra usado/libre
    const used = Math.max(0, Math.min(100, 100 - (sp.free_percent ?? 0)));
    el.querySelector("#d-space").innerHTML =
      `<div class="bar" style="width:${used}%;background:var(--warn)"></div>
       <p class="muted">${esc(sp.used_h)} usado · ${esc(sp.free_h)} libre · ${esc(sp.total_h)} total</p>`;

    // Antigüedad con conmutador Modificado/Accedido
    const ageEl = el.querySelector("#d-age");
    const toggle = el.querySelector("#d-age-toggle");
    toggle.innerHTML = `<button class="btn ghost" data-f="mtime">Modif.</button><button class="btn ghost" data-f="atime">Acced.</button>`;
    async function drawAge(field) {
      const a = await get("/api/age", { field });
      stacked(ageEl, a.buckets);
    }
    toggle.querySelectorAll("button").forEach(b => b.addEventListener("click", () => drawAge(b.dataset.f)));

    // Todo EN PARALELO: cada bloque pinta en cuanto llegan sus datos.
    // En serie, la carga era la SUMA de las 5 consultas pesadas.
    await Promise.all([
      drawAge("mtime"),
      get("/api/types").then(t =>
        donut(el.querySelector("#d-types"), t.items, { nameKey: "category", valueKey: "size" })),
      get("/api/extensions", { by: "size", limit: 8 }).then(ext =>
        bars(el.querySelector("#d-ext"), ext.items, { nameKey: "ext", valueKey: "size" })),
      get("/api/top/files", { limit: 20 }).then(tf => {
        el.querySelector("#d-files").innerHTML =
          `<thead><tr><th>Nombre</th><th>Tamaño</th></tr></thead><tbody>` +
          tf.items.map(i => `<tr><td data-label="Nombre" title="${esc(i.path)}">${esc(i.name)}</td><td data-label="Tamaño">${esc(i.size_h)}</td></tr>`).join("") +
          `</tbody>`;
      }),
      get("/api/top/dirs", { limit: 20 }).then(td => {
        el.querySelector("#d-dirs").innerHTML =
          `<thead><tr><th>Carpeta</th><th>Tamaño</th></tr></thead><tbody>` +
          td.items.map(i => `<tr><td data-label="Carpeta" title="${esc(i.path)}">${esc(i.name)}</td><td data-label="Tamaño">${esc(i.size_h)}</td></tr>`).join("") +
          `</tbody>`;
      }),
    ].map(p => Promise.resolve(p).catch(e => console.error("dashboard:", e))));
  } catch (e) {
    console.error(e);
    el.innerHTML = `<p class="error">No se pudo cargar el resumen.</p>`;
  }
}
