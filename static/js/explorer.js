import { get, esc } from "./api.js";
import { donut, bars, stacked } from "./charts.js";
import { renderPager } from "./pager.js";

const ROOT = "/data";
const PAGE_SIZE = 12;

// ── Module state ──────────────────────────────────────────────────────────────
let currentPath = ROOT;
let currentChartOption = "types"; // persisted across folder changes
let diskTotal = 0; // capacidad total del disco (para el % de ocupación en el árbol)

// Table pagination / sort state (sort/order persist across folder changes)
let tblPage = 0;
let tblSort = "size";
let tblOrder = "desc";
let tblParentSize = 0; // size of the currently selected folder

// Tree node cache: path → { children: [...], fetched: bool }
const treeCache = new Map();

// ── Helpers ───────────────────────────────────────────────────────────────────
function rootEl() { return document.getElementById("view-explorer"); }

function fmt(n) { return new Intl.NumberFormat("es-ES").format(n); }

/** Build breadcrumb HTML for a path */
function crumbsHtml(path) {
  const parts = path.replace(/^\/data\/?/, "").split("/").filter(Boolean);
  let acc = ROOT;
  const links = [`<a class="crumb-link" data-path="${esc(ROOT)}">data</a>`];
  for (const p of parts) {
    acc += "/" + p;
    links.push(`<a class="crumb-link" data-path="${esc(acc)}">${esc(p)}</a>`);
  }
  return links.join(" <span class='crumb-sep'>/</span> ");
}

function closeDrawer() {
  rootEl().querySelector(".tree-drawer")?.classList.remove("open");
  rootEl().querySelector(".drawer-backdrop")?.classList.remove("open");
}

// ── Tree (lazy, cached) ───────────────────────────────────────────────────────

/** Ensure node data is fetched and cached; returns children array */
async function fetchNode(path) {
  if (treeCache.has(path)) return treeCache.get(path);
  const data = await get("/api/tree", { path });
  treeCache.set(path, data.children ?? []);
  return treeCache.get(path);
}

/** Build the <ul> HTML for a node's children (without nesting — nesting is done dynamically) */
function buildChildrenHtml(children, parentMax) {
  if (!children.length) return "";
  const max = Math.max(1, ...children.map(c => c.size || 0));
  // % = ocupación de disco (sobre la capacidad total); fallback: suma del nivel
  const denom = diskTotal || children.reduce((s, c) => s + (c.size || 0), 0) || 1;
  return children.map(ch => {
    const barW = Math.round((ch.size / max) * 100);
    const pct = Math.round((ch.size / denom) * 100);
    return `<li class="tree-node" data-path="${esc(ch.path)}">
      <div class="tree-row">
        <span class="tree-caret" title="Expandir">▸</span>
        <span class="tree-name" data-path="${esc(ch.path)}">${esc(ch.name)}</span>
        <span class="tree-size muted">${esc(ch.size_h)} · ${esc(pct)}%</span>
        <div class="tree-bar-wrap"><div class="bar tree-bar" style="width:${esc(barW)}%"></div></div>
      </div>
      <ul class="tree tree-children" data-loaded="false"></ul>
    </li>`;
  }).join("");
}

/** Expand a tree node: fetch children (if needed) and render them */
async function expandNode(li) {
  const path = li.dataset.path;
  const childUl = li.querySelector(":scope > .tree-children");
  if (!childUl) return;

  const caret = li.querySelector(":scope > .tree-row > .tree-caret");
  if (childUl.dataset.loaded === "true") {
    // Toggle collapse
    const isCollapsed = !li.classList.contains("expanded");
    li.classList.toggle("expanded", isCollapsed);
    if (caret) caret.textContent = isCollapsed ? "▾" : "▸";
    return;
  }

  // First expand: fetch
  if (caret) caret.textContent = "…";
  try {
    const children = await fetchNode(path);
    childUl.dataset.loaded = "true";
    if (children.length === 0) {
      // No subfolders: mark as leaf
      li.classList.add("leaf");
      if (caret) caret.textContent = "·";
    } else {
      childUl.innerHTML = buildChildrenHtml(children);
      li.classList.add("expanded");
      if (caret) caret.textContent = "▾";
      bindTreeEvents(childUl);
    }
  } catch (e) {
    console.error(e);
    if (caret) caret.textContent = "!";
  }
}

/** Attach caret + name click events to all direct .tree-node children of a container */
function bindTreeEvents(container) {
  container.querySelectorAll(":scope > .tree-node").forEach(li => {
    const row = li.querySelector(":scope > .tree-row");
    const caret = row?.querySelector(".tree-caret");
    const name = row?.querySelector(".tree-name");

    caret?.addEventListener("click", e => {
      e.stopPropagation();
      expandNode(li);
    });

    name?.addEventListener("click", e => {
      e.stopPropagation();
      selectFolder(li.dataset.path);
    });
  });
}

/** Highlight the selected node in the tree */
function highlightTree(path) {
  rootEl().querySelectorAll(".tree-node.sel").forEach(n => n.classList.remove("sel"));
  const target = rootEl().querySelector(`.tree-node[data-path="${CSS.escape(path)}"]`);
  target?.classList.add("sel");
}

/**
 * Expand the path ancestors in the tree to make `path` visible,
 * then highlight it. Expands lazily from ROOT downward.
 */
async function ensureVisibleInTree(path) {
  if (path === ROOT) { highlightTree(ROOT); return; }
  // Build ancestor list: /data/A/B → ["/data/A", "/data/A/B"]
  const parts = path.replace(/^\/data\/?/, "").split("/").filter(Boolean);
  let acc = ROOT;
  for (const p of parts) {
    acc += "/" + p;
    // Find or expand the node
    const li = rootEl().querySelector(`.tree-node[data-path="${CSS.escape(acc)}"]`);
    if (!li) break; // not rendered yet — tree might not have loaded this level
    if (!li.classList.contains("expanded") && !li.classList.contains("leaf")) {
      await expandNode(li);
    }
  }
  highlightTree(path);
}

// ── Chart panel ───────────────────────────────────────────────────────────────

async function renderChart(path, option) {
  const chartArea = rootEl().querySelector("#ex-chart-area");
  if (!chartArea) return;
  chartArea.innerHTML = `<p class="muted">Cargando…</p>`;
  try {
    if (option === "types") {
      const [bySize, byCount] = await Promise.all([
        get("/api/extensions", { path, by: "size", limit: 10 }),
        get("/api/extensions", { path, by: "count", limit: 10 }),
      ]);
      chartArea.innerHTML =
        `<div class="chart-duo">
          <div class="chart-col">
            <p class="chart-label muted">Por tamaño</p>
            <div class="chart" id="ex-chart-a"></div>
          </div>
          <div class="chart-col">
            <p class="chart-label muted">Por conteo</p>
            <div class="chart" id="ex-chart-b"></div>
          </div>
        </div>`;
      bars(chartArea.querySelector("#ex-chart-a"), bySize.items, { nameKey: "ext", valueKey: "size" });
      donut(chartArea.querySelector("#ex-chart-b"), byCount.items, { nameKey: "ext", valueKey: "count" });

    } else if (option === "dirs") {
      const { items } = await get("/api/top/dirs", { path, limit: 10 });
      chartArea.innerHTML =
        `<div class="chart-duo">
          <div class="chart-col">
            <p class="chart-label muted">Por tamaño</p>
            <div class="chart" id="ex-chart-a"></div>
          </div>
          <div class="chart-col">
            <p class="chart-label muted">Por conteo</p>
            <div class="chart" id="ex-chart-b"></div>
          </div>
        </div>`;
      bars(chartArea.querySelector("#ex-chart-a"), items, { nameKey: "name", valueKey: "size" });
      donut(chartArea.querySelector("#ex-chart-b"), items, { nameKey: "name", valueKey: "count" });

    } else if (option === "agem") {
      const { buckets } = await get("/api/age", { path, field: "mtime" });
      chartArea.innerHTML = `<div class="chart" id="ex-chart-a"></div>`;
      stacked(chartArea.querySelector("#ex-chart-a"), buckets);

    } else if (option === "agea") {
      const { buckets } = await get("/api/age", { path, field: "atime" });
      chartArea.innerHTML = `<div class="chart" id="ex-chart-a"></div>`;
      stacked(chartArea.querySelector("#ex-chart-a"), buckets);
    }
  } catch (e) {
    console.error(e);
    chartArea.innerHTML = `<p class="error">No se pudo cargar el gráfico.</p>`;
  }
}

// ── Subfolders table (paginated, sortable, multi-column) ──────────────────────

const _SORT_DEFAULTS = {
  name: "asc",
  size: "desc",
  mtime: "desc",
  atime: "desc",
  files: "desc",
  dirs: "desc",
};

const _COL_LABELS = [
  { key: "name",   label: "Nombre",    sortable: true },
  { key: "_bar",   label: "Barra",     sortable: false },
  { key: "_pct",   label: "%",         sortable: false },
  { key: "size",   label: "Tamaño",    sortable: true },
  { key: "mtime",  label: "Modificado",sortable: true },
  { key: "atime",  label: "Accedido",  sortable: true },
  { key: "files",  label: "Archivos",  sortable: true },
  { key: "dirs",   label: "Carpetas",  sortable: true },
  { key: "owner",  label: "Owner",     sortable: false },
  { key: "group",  label: "Grupo",     sortable: false },
  { key: "_type",  label: "Tipo",      sortable: false },
];

function _thHtml(col) {
  if (!col.sortable) return `<th>${esc(col.label)}</th>`;
  const active = tblSort === col.key;
  const indicator = active ? (tblOrder === "asc" ? " ▲" : " ▼") : "";
  return `<th class="th-sort${active ? " th-sort-active" : ""}" data-sort="${esc(col.key)}">${esc(col.label)}${indicator}</th>`;
}

async function loadChildrenTable(path) {
  const panel = rootEl().querySelector(".ex-subfolders-panel");
  if (!panel) return;

  // Ensure we have a scroll container and a pager container
  let scrollEl = panel.querySelector(".scroll");
  if (!scrollEl) return;
  scrollEl.innerHTML = `<p class="muted">Cargando…</p>`;

  let pagerEl = panel.querySelector(".pager");
  if (!pagerEl) {
    pagerEl = document.createElement("div");
    pagerEl.className = "pager";
    panel.appendChild(pagerEl);
  }
  pagerEl.innerHTML = "";

  try {
    const data = await get("/api/children", {
      path,
      limit: PAGE_SIZE,
      offset: tblPage * PAGE_SIZE,
      sort: tblSort,
      order: tblOrder,
    });

    const { items, total } = data;
    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

    if (!items.length) {
      scrollEl.innerHTML = `<p class="muted">Sin elementos.</p>`;
      pagerEl.innerHTML = `<span class="muted">0 resultados</span>`;
      return;
    }

    const maxSize = Math.max(1, ...items.map(it => it.size || 0));

    const headHtml = `<thead><tr>${_COL_LABELS.map(_thHtml).join("")}</tr></thead>`;
    const bodyRows = items.map(it => {
      const barW = Math.min(100, Math.round((it.size / maxSize) * 100));
      const pct = tblParentSize > 0
        ? ((it.size / tblParentSize) * 100).toFixed(1) + "%"
        : "—";
      const nameCell = it.type === "directory"
        ? `<a class="row-dir-link" data-path="${esc(it.path)}">${esc(it.name)}</a>`
        : esc(it.name);
      const typeLabel = it.type === "directory" ? "Carpeta" : "Archivo";
      return `<tr class="${it.type === "directory" ? "row-dir" : ""}">
        <td data-label="Nombre">${nameCell}</td>
        <td data-label="Barra" class="bar-cell"><div class="bar" style="width:${esc(String(barW))}%;max-width:100px"></div></td>
        <td data-label="%">${esc(pct)}</td>
        <td data-label="Tamaño">${esc(it.size_h)}</td>
        <td data-label="Modificado">${esc(it.mtime || "—")}</td>
        <td data-label="Accedido">${esc(it.atime || "—")}</td>
        <td data-label="Archivos">${esc(fmt(it.files))}</td>
        <td data-label="Carpetas">${esc(fmt(it.dirs))}</td>
        <td data-label="Owner">${esc(it.owner || "—")}</td>
        <td data-label="Grupo">${esc(it.group || "—")}</td>
        <td data-label="Tipo">${esc(typeLabel)}</td>
      </tr>`;
    }).join("");

    scrollEl.innerHTML = `<table>${headHtml}<tbody>${bodyRows}</tbody></table>`;

    // Bind sortable headers
    scrollEl.querySelectorAll(".th-sort").forEach(th => {
      th.addEventListener("click", () => {
        const key = th.dataset.sort;
        if (tblSort === key) {
          tblOrder = tblOrder === "asc" ? "desc" : "asc";
        } else {
          tblSort = key;
          tblOrder = _SORT_DEFAULTS[key] ?? "desc";
        }
        tblPage = 0;
        loadChildrenTable(currentPath);
      });
    });

    // Bind dir-link clicks
    scrollEl.querySelectorAll(".row-dir-link[data-path]").forEach(a => {
      a.addEventListener("click", () => selectFolder(a.dataset.path));
    });

    // Paginador con números clicables (componente compartido)
    renderPager(pagerEl, {
      page: tblPage, totalPages,
      onPage: p => { tblPage = p; loadChildrenTable(currentPath); },
      info: `${fmt(total)} resultados · página ${tblPage + 1} de ${totalPages}`,
    });

  } catch (e) {
    console.error(e);
    scrollEl.innerHTML = `<p class="error">No se pudo cargar la tabla de elementos.</p>`;
    pagerEl.innerHTML = "";
  }
}

// ── selectFolder: the central sync function ───────────────────────────────────

async function selectFolder(path) {
  currentPath = path;
  tblPage = 0; // reset pagination on folder change

  // 1. Update crumbs + header stats
  const crumbsEl = rootEl().querySelector(".crumbs");
  const statsEl = rootEl().querySelector("#ex-stats");
  if (crumbsEl) crumbsEl.innerHTML = crumbsHtml(path);

  // Re-bind crumb links (they are new DOM nodes)
  crumbsEl?.querySelectorAll(".crumb-link").forEach(a =>
    a.addEventListener("click", () => selectFolder(a.dataset.path))
  );

  // Fetch tree data for this path (also provides current stats + children)
  let treeData;
  try {
    if (statsEl) statsEl.innerHTML = `<span class="muted">Cargando…</span>`;
    treeData = await get("/api/tree", { path });
    // Cache children
    treeCache.set(path, treeData.children ?? []);
  } catch (e) {
    console.error(e);
    if (statsEl) statsEl.innerHTML = `<span class="error">No se pudo cargar.</span>`;
    return;
  }

  // Header stats + set tblParentSize for % column
  if (statsEl) {
    const c = treeData.current;
    if (c) {
      tblParentSize = c.size || 0;
      statsEl.innerHTML =
        `<span class="muted">${esc(c.size_h)} · ${esc(fmt(c.items))} items · ` +
        `${esc(fmt(c.files))} archivos · ${esc(fmt(c.dirs))} carpetas · ` +
        `modif. ${esc(c.mtime)}</span>`;
    } else {
      // Root: no current; use sum of direct children sizes for %
      tblParentSize = (treeData.children ?? []).reduce((acc, ch) => acc + (ch.size || 0), 0);
      statsEl.innerHTML = `<span class="muted">/data</span>`;
    }
  }

  // 2. Re-render chart for current option
  await renderChart(path, currentChartOption);

  // 3. Load paginated children table from /api/children
  await loadChildrenTable(path);

  // 4. Expand + highlight tree node
  await ensureVisibleInTree(path);

  // 5. On mobile close drawer
  if (window.innerWidth < 760) closeDrawer();
}

// ── init ──────────────────────────────────────────────────────────────────────

export async function init() {
  const el = rootEl();

  el.innerHTML =
    `<button id="btn-tree" class="btn ghost">☰ Árbol</button>
     <div class="explorer-grid">

       <!-- LEFT: tree drawer -->
       <aside class="tree-drawer panel">
         <h2>Carpetas</h2>
         <div class="scroll">
           <ul class="tree" id="ex-tree-root"></ul>
         </div>
       </aside>

       <!-- Divisor arrastrable (solo escritorio) -->
       <div class="tree-resizer" id="ex-resizer" title="Arrastra para redimensionar"></div>

       <!-- RIGHT: detail pane -->
       <div class="ex-detail panel">

         <!-- Section 1: Crumbs + stats -->
         <div class="ex-header">
           <div class="crumbs" id="ex-crumbs"></div>
           <div id="ex-stats"></div>
         </div>

         <!-- Section 2: Chart panel -->
         <div class="ex-chart-panel panel">
           <div class="ex-chart-toolbar">
             <h2>Estadísticas</h2>
             <select id="ex-chart">
               <option value="types">Top tipos de archivo</option>
               <option value="dirs">Top carpetas</option>
               <option value="agem">Antigüedad (modificado)</option>
               <option value="agea">Antigüedad (accedido)</option>
             </select>
           </div>
           <div id="ex-chart-area" class="ex-chart-area"></div>
         </div>

         <!-- Section 3: Subfolders table -->
         <div class="ex-subfolders-panel panel">
           <h2>Subcarpetas</h2>
           <div class="scroll" id="ex-subfolders"></div>
         </div>

       </div>
     </div>
     <div class="drawer-backdrop"></div>`;

  // Btn-tree (mobile)
  el.querySelector("#btn-tree").addEventListener("click", () => {
    el.querySelector(".tree-drawer").classList.add("open");
    el.querySelector(".drawer-backdrop").classList.add("open");
  });
  el.querySelector(".drawer-backdrop").addEventListener("click", closeDrawer);

  // Divisor arrastrable del árbol (solo escritorio)
  setupResizer(el);

  // Chart selector — fija el valor persistido ANTES de la carga (sin parpadeo)
  const sel = el.querySelector("#ex-chart");
  if (sel) sel.value = currentChartOption;
  sel.addEventListener("change", e => {
    currentChartOption = e.target.value;
    renderChart(currentPath, currentChartOption);
  });

  // Bootstrap tree: nodo raíz "data" clicable + su primer nivel expandido
  const treeRoot = el.querySelector("#ex-tree-root");
  treeRoot.innerHTML = `<li class="muted">Cargando…</li>`;
  try {
    const [rootData, space] = await Promise.all([
      get("/api/tree", { path: ROOT }),
      get("/api/space").catch(() => null),
    ]);
    if (space && space.total) diskTotal = space.total; // fija el denominador antes de pintar
    const children = rootData.children ?? [];
    treeCache.set(ROOT, children);
    const occupiedPct = space ? Math.round(100 - (space.free_percent ?? 0)) : 0;
    const rootLabel = space ? `${esc(space.used_h)} · ${esc(occupiedPct)}%` : "";
    treeRoot.innerHTML =
      `<li class="tree-node expanded sel" data-path="${esc(ROOT)}">
        <div class="tree-row">
          <span class="tree-caret" title="Contraer">▾</span>
          <span class="tree-name" data-path="${esc(ROOT)}">data</span>
          <span class="tree-size muted">${rootLabel}</span>
          <div class="tree-bar-wrap"><div class="bar tree-bar" style="width:${esc(occupiedPct)}%"></div></div>
        </div>
        <ul class="tree tree-children" data-loaded="true">${buildChildrenHtml(children)}</ul>
      </li>`;
    bindTreeEvents(treeRoot); // vincula el nodo raíz (caret + nombre)
    const rootChildrenUl = treeRoot.querySelector(":scope > .tree-node > .tree-children");
    if (rootChildrenUl) bindTreeEvents(rootChildrenUl); // vincula los hijos
  } catch (e) {
    console.error(e);
    treeRoot.innerHTML = `<li class="error">No se pudo cargar el árbol.</li>`;
  }

  // Load initial folder (root)
  await selectFolder(ROOT);
}

// ── Divisor arrastrable árbol/detalle (persistido en localStorage) ────────────
function setupResizer(el) {
  const grid = el.querySelector(".explorer-grid");
  const rez = el.querySelector("#ex-resizer");
  if (!grid || !rez) return;
  try {
    const saved = localStorage.getItem("myfolder.treeW");
    if (saved) grid.style.setProperty("--tree-w", saved);
  } catch (e) { /* localStorage no disponible */ }
  let dragging = false;
  rez.addEventListener("pointerdown", e => {
    dragging = true;
    rez.setPointerCapture(e.pointerId);
    document.body.style.userSelect = "none";
  });
  rez.addEventListener("pointermove", e => {
    if (!dragging) return;
    const rect = grid.getBoundingClientRect();
    const w = Math.max(180, Math.min(600, e.clientX - rect.left));
    grid.style.setProperty("--tree-w", w + "px");
  });
  const end = () => {
    if (!dragging) return;
    dragging = false;
    document.body.style.userSelect = "";
    const w = grid.style.getPropertyValue("--tree-w");
    try { if (w) localStorage.setItem("myfolder.treeW", w); } catch (e) { /* ignore */ }
    window.dispatchEvent(new Event("resize")); // reajusta las gráficas ECharts
  };
  rez.addEventListener("pointerup", end);
  rez.addEventListener("pointercancel", end);
}
