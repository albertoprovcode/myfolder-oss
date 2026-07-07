import { get, esc } from "./api.js";
import { bars } from "./charts.js";
import { fmtNum, t } from "./i18n.js";

// ── Estado del módulo ──────────────────────────────────────────────────────────
let field = "owner";   // owner | group
let metric = "size";   // size | files
let sort = "size";     // name | files | size
let order = "desc";
let cache = null;      // último payload de /api/owners para re-render sin refetch

function rootEl() { return document.getElementById("view-owners"); }
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

  const fieldWord = field === "group" ? t("owners.field_group") : t("owners.field_owner");
  const colHead = field === "group" ? t("explorer.col_group") : t("explorer.col_owner");
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
    ? t("owners.uid_note")
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
    chartEl.innerHTML = `<p class="muted">${t("owners.no_data")}</p>`;
  }

  // Tabla
  if (!items.length) {
    scrollEl.innerHTML = `<p class="muted">${t("owners.no_owner_data")}</p>`;
    return;
  }
  const headHtml = `<thead><tr>
    ${_thHtml("name", colHead)}
    ${_thHtml("files", t("owners.num_files"))}
    ${_thHtml("size", t("common.size"))}
    <th>${metric === "size" ? t("owners.pct_size") : t("owners.pct_files")}</th>
  </tr></thead>`;

  const bodyRows = items.map(it => {
    const val = metric === "size" ? it.size : it.files;
    const pct = Math.round((val / totalMetric) * 1000) / 10;
    const numTag = isNumericName(it.name) ? ` <span class="muted own-uid">${t("owners.uid_tag")}</span>` : "";
    return `<tr>
      <td data-label="${esc(colHead)}"><strong>${esc(it.name || "—")}</strong>${numTag}</td>
      <td data-label="${esc(t("owners.num_files"))}">${esc(fmtNum(it.files))}</td>
      <td data-label="${esc(t("common.size"))}">${esc(it.size_h || "—")}</td>
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
  scrollEl.innerHTML = `<p class="muted">${t("common.loading")}</p>`;
  const chartEl = el.querySelector(".own-chart");
  if (chartEl) chartEl.innerHTML = `<p class="muted">${t("common.loading")}</p>`;
  try {
    cache = await get("/api/owners", { field, limit: 200 });
    render();
  } catch (e) {
    console.error(e);
    cache = null;
    scrollEl.innerHTML = `<p class="error">${t("owners.error")}</p>`;
    const chartElErr = el.querySelector(".own-chart");
    if (chartElErr) chartElErr.innerHTML = "";
  }
}

// ── Init ───────────────────────────────────────────────────────────────────────
export async function init() {
  const el = rootEl();
  el.innerHTML = `
    <div class="own-controls">
      <label class="muted" for="own-field">${t("owners.group_by")}</label>
      <select id="own-field">
        <option value="owner" selected>${t("explorer.col_owner")}</option>
        <option value="group">${t("explorer.col_group")}</option>
      </select>
      <label class="muted" for="own-metric">${t("owners.metric_label")}</label>
      <select id="own-metric">
        <option value="size" selected>${t("common.size")}</option>
        <option value="files">${t("owners.metric_files")}</option>
      </select>
    </div>
    <div class="panel own-chart-panel">
      <h2>${t("owners.chart_title")} <span id="own-field-label">${t("owners.field_owner")}</span></h2>
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
