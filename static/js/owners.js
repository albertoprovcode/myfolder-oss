import { get, esc } from "./api.js";
import { bars } from "./charts.js";

// ── Estado del módulo ──────────────────────────────────────────────────────────
let field = "owner";   // owner | group
let metric = "size";   // size | files
let sort = "size";     // name | files | size
let order = "desc";
let cache = null;      // último payload de /api/owners para re-render sin refetch

function rootEl() { return document.getElementById("view-owners"); }
function fmt(n) { return new Intl.NumberFormat("es-ES").format(n); }
function isNumericName(name) { return /^\d+$/.test(name); }

function _thHtml(key, label) {
  const active = sort === key;
  const indicator = active ? (order === "asc" ? " ▲" : " ▼") : "";
  return `<th class="th-sort${active ? " th-sort-active" : ""}" data-sort="${esc(key)}">${esc(label)}${indicator}</th>`;
}

// ── Render (usa la caché; no refetch salvo cambio de campo) ─────────────────────
function render() {
  const el = rootEl();
  const chartEl = el.querySelector(".own-chart");
  const scrollEl = el.querySelector(".own-scroll");
  const noteEl = el.querySelector(".own-note");
  const labelEl = el.querySelector("#own-field-label");
  if (!chartEl || !scrollEl || !cache) return;

  const fieldWord = field === "group" ? "grupo" : "propietario";
  const colHead = field === "group" ? "Grupo" : "Propietario";
  if (labelEl) labelEl.textContent = fieldWord;

  const totalMetric = (metric === "size" ? cache.total_size : cache.total_files) || 1;

  // Orden de la tabla
  const items = cache.items.slice().sort((a, b) => {
    let cmp;
    if (sort === "name") cmp = String(a.name).localeCompare(String(b.name), "es", { numeric: true });
    else cmp = (a[sort] || 0) - (b[sort] || 0);
    return order === "asc" ? cmp : -cmp;
  });

  // Nota sobre UID/GID sin resolver
  const hasNumeric = items.some(i => isNumericName(i.name));
  noteEl.innerHTML = hasNumeric
    ? `Los valores numéricos (p.ej. <strong>1000</strong>) son UID/GID sin resolver del sistema de archivos.`
    : "";
  noteEl.style.display = hasNumeric ? "" : "none";

  // Gráfico: top por la métrica elegida (tamaño en GiB para que el eje sea legible)
  const top = cache.items.slice()
    .sort((a, b) => (b[metric] || 0) - (a[metric] || 0))
    .slice(0, 15)
    .map(i => ({ name: i.name, files: i.files, size_gib: Math.round((i.size / (1024 ** 3)) * 10) / 10 }));
  if (top.length) {
    bars(chartEl, top, { nameKey: "name", valueKey: metric === "size" ? "size_gib" : "files" });
  } else {
    chartEl.innerHTML = `<p class="muted">Sin datos.</p>`;
  }

  // Tabla
  if (!items.length) {
    scrollEl.innerHTML = `<p class="muted">Sin datos de propietario en el índice.</p>`;
    return;
  }
  const headHtml = `<thead><tr>
    ${_thHtml("name", colHead)}
    ${_thHtml("files", "Nº archivos")}
    ${_thHtml("size", "Tamaño")}
    <th>% (${metric === "size" ? "tamaño" : "archivos"})</th>
  </tr></thead>`;

  const bodyRows = items.map(it => {
    const val = metric === "size" ? it.size : it.files;
    const pct = Math.round((val / totalMetric) * 1000) / 10;
    const numTag = isNumericName(it.name) ? ` <span class="muted own-uid">(UID)</span>` : "";
    return `<tr>
      <td data-label="${esc(colHead)}"><strong>${esc(it.name || "—")}</strong>${numTag}</td>
      <td data-label="Nº archivos">${esc(fmt(it.files))}</td>
      <td data-label="Tamaño">${esc(it.size_h || "—")}</td>
      <td data-label="%">
        <div class="own-pct"><span>${esc(String(pct))}%</span>
          <span class="bar own-bar" style="width:${Math.max(2, pct)}%"></span></div>
      </td>
    </tr>`;
  }).join("");

  scrollEl.innerHTML = `<table>${headHtml}<tbody>${bodyRows}</tbody></table>`;

  scrollEl.querySelectorAll(".th-sort").forEach(th => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (sort === key) order = order === "asc" ? "desc" : "asc";
      else { sort = key; order = key === "name" ? "asc" : "desc"; }
      render();
    });
  });
}

async function load() {
  const el = rootEl();
  const scrollEl = el.querySelector(".own-scroll");
  scrollEl.innerHTML = `<p class="muted">Cargando…</p>`;
  const chartEl = el.querySelector(".own-chart");
  if (chartEl) chartEl.innerHTML = `<p class="muted">Cargando…</p>`;
  try {
    cache = await get("/api/owners", { field, limit: 200 });
    render();
  } catch (e) {
    console.error(e);
    cache = null;
    scrollEl.innerHTML = `<p class="error">No se pudo cargar el reparto por propietario.</p>`;
    const chartElErr = el.querySelector(".own-chart");
    if (chartElErr) chartElErr.innerHTML = "";
  }
}

// ── Init ───────────────────────────────────────────────────────────────────────
export async function init() {
  const el = rootEl();
  el.innerHTML = `
    <div class="own-controls">
      <label class="muted" for="own-field">Agrupar por:</label>
      <select id="own-field">
        <option value="owner" selected>Propietario</option>
        <option value="group">Grupo</option>
      </select>
      <label class="muted" for="own-metric">Métrica:</label>
      <select id="own-metric">
        <option value="size" selected>Tamaño</option>
        <option value="files">Nº de archivos</option>
      </select>
    </div>
    <div class="panel own-chart-panel">
      <h2>Reparto por <span id="own-field-label">propietario</span></h2>
      <div class="chart own-chart"></div>
    </div>
    <div class="panel own-table-panel">
      <p class="own-note muted"></p>
      <div class="scroll own-scroll"></div>
    </div>
  `;

  el.querySelector("#own-field").addEventListener("change", e => {
    field = e.target.value;
    sort = "size"; order = "desc";
    load();
  });
  el.querySelector("#own-metric").addEventListener("change", e => {
    metric = e.target.value;
    // el orden por defecto sigue a la métrica elegida
    sort = metric; order = "desc";
    render();
  });

  await load();
}
