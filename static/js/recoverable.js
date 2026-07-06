import { get, esc } from "./api.js";
import { mountTree } from "./tree.js";
import { renderPager } from "./pager.js";

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
function fmt(n) { return new Intl.NumberFormat("es-ES").format(n); }

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

  scrollEl.innerHTML = `<p class="muted">Cargando…</p>`;
  pagerEl.innerHTML = "";
  summaryEl.textContent = "Cargando…";

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

    summaryEl.innerHTML =
      `Recuperable: <strong>${esc(fmt(total))}</strong> archivos · <strong>${esc(total_size_h)}</strong>`;

    if (!items.length) {
      scrollEl.innerHTML = `<p class="muted">Sin archivos con estos criterios.</p>`;
      pagerEl.innerHTML = `<span class="muted">0 resultados</span>`;
      return;
    }

    const headHtml = `<thead><tr>
      ${_thHtml("name", "Nombre")}
      <th>Ruta</th>
      ${_thHtml("size", "Tamaño")}
      ${_thHtml("mtime", "Modificado")}
      ${_thHtml("atime", "Accedido")}
    </tr></thead>`;

    const bodyRows = items.map(it => `<tr>
      <td data-label="Nombre">${esc(it.name || "—")}</td>
      <td data-label="Ruta" class="rec-path">${esc(it.path || "—")}</td>
      <td data-label="Tamaño">${esc(it.size_h || "—")}</td>
      <td data-label="Modificado">${esc(it.mtime || "—")}</td>
      <td data-label="Accedido">${esc(it.atime || "—")}</td>
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
      info: `${fmt(total)} resultados · página ${page + 1} de ${totalPages}`,
    });

  } catch (e) {
    console.error(e);
    scrollEl.innerHTML = `<p class="error">No se pudo cargar la vista Recuperable.</p>`;
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
        <h2>Carpetas</h2>
        <button id="rec-btn-tree-close" class="btn ghost rec-tree-close" title="Cerrar">✕</button>
      </div>
      <div class="scroll">
        <ul class="tree" id="rec-tree-root"></ul>
      </div>
    </aside>
    <div class="tree-resizer" id="rec-resizer" title="Arrastra para redimensionar"></div>
    <div class="rec-main">
      <button id="rec-btn-tree" class="btn ghost rec-btn-tree">☰ Carpetas</button>
      <div class="rec-crumbs"></div>
      <div class="rec-controls">
        <label class="muted" for="rec-field">Campo:</label>
        <select id="rec-field">
          <option value="mtime" selected>Modificado</option>
          <option value="atime">Accedido</option>
        </select>
        <label class="muted" for="rec-days">Antigüedad:</label>
        <select id="rec-days">
          <option value="90">&gt;90 días</option>
          <option value="180">&gt;180 días</option>
          <option value="365" selected>&gt;1 año</option>
          <option value="730">&gt;2 años</option>
        </select>
        <label class="muted" for="rec-min">Tamaño mín.:</label>
        <select id="rec-min">
          <option value="0" selected>Cualquiera</option>
          <option value="104857600">&gt;100 MB</option>
          <option value="1073741824">&gt;1 GB</option>
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
    const w = Math.max(200, Math.min(640, e.clientX - rect.left));
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
