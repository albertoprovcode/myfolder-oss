import { get, esc } from "./api.js";
import { mountTree } from "./tree.js";
import { renderPager } from "./pager.js";
import { fmtNum, t } from "./i18n.js";

const PAGE_SIZE = 12;
const ROOT = "/data";

// ── Estado del módulo ──────────────────────────────────────────────────────────
let field = "mtime";
let days = 365;
let minSize = 0;
let page = 0;
let sort = "size";
let order = "desc";
let currentPath = ROOT;
let tree = null;

function rootEl() { return document.getElementById("view-recoverable"); }

function breadcrumbHtml(path) {
  const parts = path.replace(/^\/data\/?/, "").split("/").filter(Boolean);
  let acc = ROOT;
  const links = [`<a class="crumb-link" data-path="${esc(ROOT)}">data</a>`];
  for (const p of parts) {
    acc += "/" + p;
    links.push(`<a class="crumb-link" data-path="${esc(acc)}">${esc(p)}</a>`);
  }
  return links.join(" <span class='crumb-sep'>/</span> ");
}

async function selectFolder(path) {
  currentPath = path;
  page = 0;
  tree?.select(path);
  const crumbsEl = rootEl().querySelector(".rec-crumbs");
  if (crumbsEl) {
    crumbsEl.innerHTML = breadcrumbHtml(path);
    crumbsEl.querySelectorAll(".crumb-link").forEach(a =>
      a.addEventListener("click", () => selectFolder(a.dataset.path))
    );
  }
  if (window.innerWidth <= 760) {
    rootEl().querySelector(".rec-tree")?.classList.remove("open");
  }
  await load();
}

// ── Render tabla + resumen ───────────────────────────────────────────────────────

function _thHtml(key, label) {
  const active = sort === key;
  const indicator = active ? (order === "asc" ? " ▲" : " ▼") : "";
  return `<th class="th-sort${active ? " th-sort-active" : ""}" data-sort="${esc(key)}">${esc(label)}${indicator}</th>`;
}

async function load() {
  const el = rootEl();
  const summaryEl = el.querySelector(".rec-summary");
  const scrollEl = el.querySelector(".rec-scroll");
  const pagerEl = el.querySelector(".rec-pager");

  if (!summaryEl || !scrollEl || !pagerEl) return;

  scrollEl.innerHTML = `<p class="muted">${t("common.loading")}</p>`;
  pagerEl.innerHTML = "";
  summaryEl.textContent = t("common.loading");

  try {
    const data = await get("/api/cold", {
      field,
      days,
      size_min: minSize,
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
      sort,
      order,
      path: currentPath,
    });

    const { items, total, total_size_h } = data;
    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

    summaryEl.innerHTML = t("recoverable.summary", { n: esc(fmtNum(total)), size: esc(total_size_h) });

    if (!items.length) {
      scrollEl.innerHTML = `<p class="muted">${t("recoverable.empty")}</p>`;
      pagerEl.innerHTML = `<span class="muted">${t("explorer.zero_results")}</span>`;
      return;
    }

    const headHtml = `<thead><tr>
      ${_thHtml("name", t("common.name"))}
      <th>${esc(t("common.path"))}</th>
      ${_thHtml("size", t("common.size"))}
      ${_thHtml("mtime", t("explorer.col_modified"))}
      ${_thHtml("atime", t("explorer.col_accessed"))}
    </tr></thead>`;

    const bodyRows = items.map(it => `<tr>
      <td data-label="${esc(t("common.name"))}">${esc(it.name || "—")}</td>
      <td data-label="${esc(t("common.path"))}" class="rec-path">${esc(it.path || "—")}</td>
      <td data-label="${esc(t("common.size"))}">${esc(it.size_h || "—")}</td>
      <td data-label="${esc(t("explorer.col_modified"))}">${esc(it.mtime || "—")}</td>
      <td data-label="${esc(t("explorer.col_accessed"))}">${esc(it.atime || "—")}</td>
    </tr>`).join("");

    scrollEl.innerHTML = `<table>${headHtml}<tbody>${bodyRows}</tbody></table>`;

    // Cabeceras ordenables
    scrollEl.querySelectorAll(".th-sort").forEach(th => {
      th.addEventListener("click", () => {
        const key = th.dataset.sort;
        if (sort === key) {
          order = order === "asc" ? "desc" : "asc";
        } else {
          sort = key;
          order = key === "name" ? "asc" : "desc";
        }
        page = 0;
        load();
      });
    });

    // Paginador con números clicables (componente compartido)
    renderPager(pagerEl, {
      page, totalPages,
      onPage: p => { page = p; load(); },
      info: t("common.pager_info", { n: fmtNum(total), page: page + 1, total: totalPages }),
    });

  } catch (e) {
    console.error(e);
    scrollEl.innerHTML = `<p class="error">${t("recoverable.error")}</p>`;
    pagerEl.innerHTML = "";
    summaryEl.textContent = "";
  }
}

// ── Init ───────────────────────────────────────────────────────────────────────

export async function init() {
  const el = rootEl();

  el.innerHTML = `
    <aside class="panel rec-tree">
      <div class="rec-tree-head">
        <h2>${t("explorer.folders_heading")}</h2>
        <button id="rec-btn-tree-close" class="btn ghost rec-tree-close" title="${esc(t("common.close"))}">✕</button>
      </div>
      <div class="scroll">
        <ul class="tree" id="rec-tree-root"></ul>
      </div>
    </aside>
    <div class="tree-resizer" id="rec-resizer" title="${esc(t("explorer.resize_title"))}"></div>
    <div class="rec-main">
      <button id="rec-btn-tree" class="btn ghost rec-btn-tree">${t("search.folders_toggle")}</button>
      <div class="rec-crumbs"></div>
      <div class="rec-controls">
        <label class="muted" for="rec-field">${t("recoverable.field_label")}</label>
        <select id="rec-field">
          <option value="mtime" selected>${t("explorer.col_modified")}</option>
          <option value="atime">${t("explorer.col_accessed")}</option>
        </select>
        <label class="muted" for="rec-days">${t("recoverable.age_label")}</label>
        <select id="rec-days">
          <option value="90">${t("recoverable.opt_90d")}</option>
          <option value="180">${t("recoverable.opt_180d")}</option>
          <option value="365" selected>${t("recoverable.opt_1y")}</option>
          <option value="730">${t("recoverable.opt_2y")}</option>
        </select>
        <label class="muted" for="rec-min">${t("recoverable.min_size_label")}</label>
        <select id="rec-min">
          <option value="0" selected>${t("search.group_any")}</option>
          <option value="104857600">${t("recoverable.opt_100mb")}</option>
          <option value="1073741824">${t("recoverable.opt_1gb")}</option>
        </select>
      </div>
      <p class="rec-summary"></p>
      <div class="panel rec-table-panel">
        <div class="scroll rec-scroll"></div>
        <div class="pager rec-pager"></div>
      </div>
    </div>
  `;

  el.querySelector("#rec-field").addEventListener("change", e => {
    field = e.target.value;
    page = 0;
    load();
  });

  el.querySelector("#rec-days").addEventListener("change", e => {
    days = parseInt(e.target.value, 10);
    page = 0;
    load();
  });

  el.querySelector("#rec-min").addEventListener("change", e => {
    minSize = parseInt(e.target.value, 10);
    page = 0;
    load();
  });

  // Toggle del árbol en móvil (clase simple, sin backdrop)
  el.querySelector("#rec-btn-tree").addEventListener("click", () => {
    el.querySelector(".rec-tree")?.classList.add("open");
  });
  el.querySelector("#rec-btn-tree-close").addEventListener("click", () => {
    el.querySelector(".rec-tree")?.classList.remove("open");
  });

  el.querySelector(".rec-crumbs").innerHTML = breadcrumbHtml(currentPath);
  el.querySelector(".rec-crumbs").querySelectorAll(".crumb-link").forEach(a =>
    a.addEventListener("click", () => selectFolder(a.dataset.path))
  );

  setupResizer(el);
  tree = mountTree(el.querySelector("#rec-tree-root"), { onSelect: selectFolder });
  await load();
}

// ── Divisor arrastrable árbol/tabla (persistido en localStorage) ──────────────
function setupResizer(el) {
  const rez = el.querySelector("#rec-resizer");
  if (!rez) return;
  try {
    const saved = localStorage.getItem("myfolder.recTreeW");
    if (saved) el.style.setProperty("--rec-tree-w", saved);
  } catch (e) { /* localStorage no disponible */ }
  let dragging = false;
  rez.addEventListener("pointerdown", e => {
    dragging = true;
    rez.setPointerCapture(e.pointerId);
    document.body.style.userSelect = "none";
  });
  rez.addEventListener("pointermove", e => {
    if (!dragging) return;
    const rect = el.getBoundingClientRect();
    const rtl = document.documentElement.dir === "rtl";
    const delta = rtl ? (rect.right - e.clientX) : (e.clientX - rect.left);
    const w = Math.max(200, Math.min(640, delta));
    el.style.setProperty("--rec-tree-w", w + "px");
  });
  const end = e => {
    if (!dragging) return;
    dragging = false;
    document.body.style.userSelect = "";
    try {
      const w = el.style.getPropertyValue("--rec-tree-w");
      if (w) localStorage.setItem("myfolder.recTreeW", w);
    } catch (err) { /* ignore */ }
  };
  rez.addEventListener("pointerup", end);
  rez.addEventListener("pointercancel", end);
}
