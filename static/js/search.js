import { get, post, esc } from "./api.js";
import { mountTree } from "./tree.js";
import { renderPager } from "./pager.js";
const root = () => document.getElementById("view-search");

const UNIT_BYTES = { KB: 1024, MB: 1024 ** 2, GB: 1024 ** 3 };

// ── Estado del módulo ────────────────────────────────────────────────────
let sort = "size";
let order = "desc";
let page = 0;
let lastParams = {}; // últimos filtros lanzados (sin sort/order/limit), para reordenar sin releer el form
let renderToken = 0; // corta sondeos de hash de renders anteriores
let dupeGroups = []; // [{paths: [ruta completa,...], size: bytes_por_archivo, total: bytes}]

const ROOT = "/data";
let currentPath = ROOT; // carpeta del árbol; PERSISTE entre búsquedas y presets
let searched = false; // ya se lanzó alguna búsqueda (para relanzar al cambiar de carpeta)
let tree = null;

const GROUPS_PER_PAGE = 15; // modo duplicados: grupos de tamaño por página
const ROWS_PER_PAGE = 50; // búsqueda normal: filas por página

const _fmtN = n => new Intl.NumberFormat("es-ES").format(n ?? 0);

function _thHtml(key, label, sortable = true) {
  if (!sortable) return `<th>${esc(label)}</th>`;
  const active = sort === key;
  const indicator = active ? (order === "asc" ? " ▲" : " ▼") : "";
  return `<th class="th-sort${active ? " th-sort-active" : ""}" data-sort="${esc(key)}">${esc(label)}${indicator}</th>`;
}

function rowsFiles(items, group = false) {
  // group=true (modo duplicados): banda de color por tamaño EXACTO, de forma
  // que cada bloque del mismo color = grupo de posibles duplicados.
  let gi = -1, prev = null;
  dupeGroups = [];
  const rows = items.map(i => {
    let first = false;
    if (group) {
      if (i.size !== prev) { gi++; prev = i.size; first = true; dupeGroups.push({ paths: [], size: i.size, total: 0 }); }
      const g = dupeGroups[gi];
      g.paths.push(i.path + "/" + i.name);
      g.total += i.size;
    }
    const cls = group ? ` class="dup-g${gi % 2}"` : "";
    const hashCell = group
      ? `<td data-label="Hash" class="hash-cell" data-hash-path="${esc(i.path + "/" + i.name)}">${first ? _verifyBtnHtml(gi) : ""}</td>`
      : "";
    return `<tr${cls}><td data-label="Nombre">${esc(i.name)}<div class="muted path-sub">${esc(i.path)}</div></td>
     <td data-label="Tamaño">${esc(i.size_h)}</td>
     <td data-label="Modificado">${esc(i.mtime)}</td>
     <td data-label="Accedido">${esc(i.atime)}</td>${hashCell}</tr>`;
  }).join("");
  return rows;
}

function _verifyBtnHtml(gi) {
  return `<button type="button" class="btn ghost btn-verify" data-group="${gi}">Verificar</button>`;
}

/** Estimación de lectura a ~150 MB/s, solo para grupos de más de 2 GB. */
function _estimacion(totalBytes) {
  if (totalBytes <= 2 * 1024 ** 3) return "";
  const min = Math.max(1, Math.round(totalBytes / (150 * 1024 ** 2) / 60));
  return ` (~${min} min)`;
}

async function runSearch(params, keepPage = false) {
  const token = ++renderToken; // invalida sondeos de hash de renders anteriores
  searched = true;
  lastParams = { ...params };
  if (!keepPage) page = 0;
  const out = root().querySelector("#s-results");
  out.innerHTML = `<p class="muted">Buscando…</p>`;
  const group = !!params.dupes_only;
  try {
    // Modo duplicados: paginación por GRUPOS de tamaño (el backend trae todas
    // las filas de los grupos de la página; nunca parte un grupo) y orden
    // fijo por tamaño. Búsqueda normal: paginación clásica por filas.
    const query = group
      ? { ...params, sort: "size", order,
          group_limit: GROUPS_PER_PAGE, group_offset: page * GROUPS_PER_PAGE }
      : { ...params, sort, order,
          limit: ROWS_PER_PAGE, offset: page * ROWS_PER_PAGE };
    if (currentPath !== ROOT) query.path = currentPath;
    const r = await get("/api/search", query);
    if (!r.items.length) {
      out.innerHTML = `<p class="muted">Sin resultados.</p>`;
      return;
    }
    const headHtml = `<thead><tr>
      ${_thHtml("name", "Nombre", !group)}
      ${_thHtml("size", "Tamaño")}
      ${_thHtml("mtime", "Modificado", !group)}
      ${_thHtml("atime", "Accedido", !group)}
      ${group ? "<th>Hash</th>" : ""}
    </tr></thead>`;
    const totalPages = group
      ? Math.max(1, Math.ceil((r.total_groups ?? 0) / GROUPS_PER_PAGE))
      : Math.max(1, Math.ceil(r.total / ROWS_PER_PAGE));
    const pageInfo = totalPages > 1 ? ` · página ${page + 1} de ${_fmtN(totalPages)}` : "";
    const note = group
      ? `<p class="muted">${_fmtN(r.total)} archivos en ${_fmtN(r.total_groups)} grupos${pageInfo} · cada bloque de color = archivos del mismo tamaño (posibles duplicados; mismo tamaño ≠ idéntico)</p>`
      : `<p class="muted">${_fmtN(r.total)} resultados${pageInfo}</p>`;
    out.innerHTML = `${note}
       <div class="scroll"><table>${headHtml}<tbody>${rowsFiles(r.items, group)}</tbody></table></div>
       <div class="pager" id="s-pager"></div>`;
    out.querySelectorAll(".th-sort").forEach(th => {
      th.addEventListener("click", () => {
        const key = th.dataset.sort;
        if (sort === key) order = order === "asc" ? "desc" : "asc";
        else { sort = key; order = key === "name" ? "asc" : "desc"; }
        runSearch(lastParams);
      });
    });
    renderPager(out.querySelector("#s-pager"), {
      page, totalPages,
      onPage: p => { page = p; runSearch(lastParams, true); },
    });
    if (group) _initHashUI(out, token);
  } catch (e) { console.error(e); out.innerHTML = `<p class="error">Error en la búsqueda.</p>`; }
}

function _readForm() {
  const el = root();
  const params = {};
  const name = el.querySelector("#s-name").value.trim();
  const ext = el.querySelector("#s-ext").value.trim();
  if (name) params.name = name;
  if (ext) params.ext = ext;
  const sizeMin = el.querySelector("#f-size-min").value;
  const sizeMax = el.querySelector("#f-size-max").value;
  const unitMin = el.querySelector("#f-size-min-unit").value;
  const unitMax = el.querySelector("#f-size-max-unit").value;
  if (sizeMin !== "" && !isNaN(Number(sizeMin))) {
    params.size_min = Math.round(Number(sizeMin) * UNIT_BYTES[unitMin]);
  }
  if (sizeMax !== "" && !isNaN(Number(sizeMax))) {
    params.size_max = Math.round(Number(sizeMax) * UNIT_BYTES[unitMax]);
  }
  const category = el.querySelector("#f-category").value;
  const type = el.querySelector("#f-type").value;
  const mtimeFrom = el.querySelector("#f-mtime-from").value;
  const mtimeTo = el.querySelector("#f-mtime-to").value;
  const atimeFrom = el.querySelector("#f-atime-from").value;
  const atimeTo = el.querySelector("#f-atime-to").value;
  const group = el.querySelector("#f-group").value;
  if (category) params.category = category;
  if (type) params.type = type;
  if (mtimeFrom) params.mtime_from = mtimeFrom;
  if (mtimeTo) params.mtime_to = mtimeTo;
  if (atimeFrom) params.atime_from = atimeFrom;
  if (atimeTo) params.atime_to = atimeTo;
  if (group) params.group = group;
  if (el.querySelector("#f-dupes-only").checked) params.dupes_only = true;
  return params;
}

function _clearForm() {
  const el = root();
  el.querySelector("#s-name").value = "";
  el.querySelector("#s-ext").value = "";
  el.querySelector("#f-size-min").value = "";
  el.querySelector("#f-size-max").value = "";
  el.querySelector("#f-size-min-unit").value = "MB";
  el.querySelector("#f-size-max-unit").value = "MB";
  el.querySelector("#f-category").value = "";
  el.querySelector("#f-type").value = "";
  el.querySelector("#f-mtime-from").value = "";
  el.querySelector("#f-mtime-to").value = "";
  el.querySelector("#f-atime-from").value = "";
  el.querySelector("#f-atime-to").value = "";
  el.querySelector("#f-group").value = "";
  el.querySelector("#f-dupes-only").checked = false;
}

function _dateYearsAgo(years) {
  const d = new Date();
  d.setFullYear(d.getFullYear() - years);
  return d.toISOString().slice(0, 10);
}

function _runPreset(fill) {
  _clearForm();
  const el = root();
  fill(el);
  sort = "size"; order = "desc";
  runSearch(_readForm());
}

const PRESETS = [
  { label: "Enormes (>25 GB)", fill: el => { el.querySelector("#f-size-min").value = "25"; el.querySelector("#f-size-min-unit").value = "GB"; } },
  { label: "Vídeos", fill: el => { el.querySelector("#f-category").value = "video"; } },
  { label: "No accedidos en 2 años", fill: el => { el.querySelector("#f-atime-to").value = _dateYearsAgo(2); } },
  { label: "Vacíos", fill: el => { el.querySelector("#f-size-max").value = "0"; el.querySelector("#f-size-max-unit").value = "KB"; } },
  { label: "Duplicados grandes (>100 MB)", fill: el => { el.querySelector("#f-size-min").value = "100"; el.querySelector("#f-size-min-unit").value = "MB"; el.querySelector("#f-dupes-only").checked = true; } },
];

export function runFromQuery(q) {
  currentPath = ROOT; // la búsqueda global siempre parte de la raíz
  tree?.select(ROOT);
  _updateScopeLabel();
  const input = root().querySelector("#s-name");
  if (input) input.value = q;
  sort = "size"; order = "desc";
  runSearch({ name: q });
}

async function _loadGroupOptions() {
  const el = root();
  const groupSel = el.querySelector("#f-group");
  try {
    const groups = await get("/api/owners", { field: "group" });
    groups.items.forEach(it => {
      const opt = document.createElement("option");
      opt.value = it.name; opt.textContent = it.name;
      groupSel.appendChild(opt);
    });
  } catch (e) {
    console.error(e); // el select queda solo con "Cualquiera": degradación aceptable
  }
}

export function toggleFilters() {
  const panel = document.getElementById("s-adv");
  if (!panel) return;
  panel.classList.toggle("open");
}

export async function init() {
  // Vista recién montada = ámbito fresco: el árbol nuevo nace resaltando la
  // raíz, así que el estado de módulo debe volver a la raíz con él.
  currentPath = ROOT;
  searched = false;
  lastParams = {};
  const el = root();
  el.innerHTML =
    `<aside class="panel s-tree">
       <div class="s-tree-head">
         <h2>Carpetas</h2>
         <button id="s-btn-tree-close" class="btn ghost s-tree-close" title="Cerrar">✕</button>
       </div>
       <div class="scroll">
         <ul class="tree" id="s-tree-root"></ul>
       </div>
     </aside>
     <div class="tree-resizer" id="s-resizer" title="Arrastra para redimensionar"></div>
     <div class="s-main">
       <div class="panel"><h2>Buscar</h2>
       <button id="s-btn-tree" class="btn ghost s-btn-tree">☰ Carpetas</button>
       <div class="filters">
         ${PRESETS.map((p, idx) => `<button type="button" class="btn ghost" data-preset="${idx}">${esc(p.label)}</button>`).join("")}
         <form id="s-form" class="filters-form">
           <input id="s-name" placeholder="Nombre contiene…">
           <input id="s-ext" placeholder="Extensión (p.ej. mp4)">
           <button class="btn" type="submit">Buscar</button>
           <button class="btn ghost" type="button" id="s-toggle-adv">Filtros</button>
         </form>
       </div>
       <div id="s-adv" class="filters-adv">
         <label>Tamaño mín
           <span class="size-input"><input id="f-size-min" type="number" min="0" placeholder="0">
           <select id="f-size-min-unit"><option>KB</option><option selected>MB</option><option>GB</option></select></span>
         </label>
         <label>Tamaño máx
           <span class="size-input"><input id="f-size-max" type="number" min="0" placeholder="sin límite">
           <select id="f-size-max-unit"><option>KB</option><option selected>MB</option><option>GB</option></select></span>
         </label>
         <label>Categoría<select id="f-category">
           <option value="">Todas</option>
           <option value="video">Vídeo</option>
           <option value="image">Imagen</option>
           <option value="audio">Audio</option>
           <option value="document">Documento</option>
           <option value="archive">Archivo (comprimido)</option>
           <option value="code">Código</option>
           <option value="other">Otros</option>
         </select></label>
         <label>Tipo<select id="f-type"><option value="">Todos</option><option value="file">Archivos</option><option value="directory">Carpetas</option></select></label>
         <label>Modificado desde<input id="f-mtime-from" type="date"></label>
         <label>Modificado hasta<input id="f-mtime-to" type="date"></label>
         <label>Accedido desde<input id="f-atime-from" type="date"></label>
         <label>Accedido hasta<input id="f-atime-to" type="date"></label>
         <label>Grupo<select id="f-group"><option value="">Cualquiera</option></select></label>
         <label class="chk-inline"><input id="f-dupes-only" type="checkbox"> Solo posibles duplicados (mismo tamaño)</label>
       </div>
       <p id="s-scope" class="muted"></p>
       <div id="s-results"><p class="muted">Usa un preset o lanza una búsqueda.</p></div></div>
     </div>`;

  el.querySelector("#s-toggle-adv").addEventListener("click", toggleFilters);

  el.querySelector("#s-form").addEventListener("submit", e => {
    e.preventDefault();
    sort = "size"; order = "desc";
    runSearch(_readForm());
  });

  el.querySelectorAll("[data-preset]").forEach(btn => {
    btn.addEventListener("click", () => _runPreset(PRESETS[Number(btn.dataset.preset)].fill));
  });

  await _loadGroupOptions();

  // Árbol de carpetas: la selección acota TODO (búsquedas y presets) hasta cambiarla
  tree = mountTree(el.querySelector("#s-tree-root"), { onSelect: _onTreeSelect });
  el.querySelector("#s-btn-tree").addEventListener("click", () => {
    el.querySelector(".s-tree")?.classList.add("open");
  });
  el.querySelector("#s-btn-tree-close").addEventListener("click", () => {
    el.querySelector(".s-tree")?.classList.remove("open");
  });
  _setupTreeResizer(el);
  _updateScopeLabel();
}

// ── Verificación por hash (modo duplicados) ──────────────────────────────

function _initHashUI(out, token) {
  // Grupo con una sola fila visible: su gemelo está fuera de la carpeta acotada.
  // Verificarlo solo daría "✓ Idénticos" de un único archivo — engañoso.
  dupeGroups.forEach((g, gi) => {
    if (g.paths.length >= 2) return;
    const btn = out.querySelector(`.btn-verify[data-group="${gi}"]`);
    if (btn) {
      const nota = document.createElement("span");
      nota.className = "muted";
      nota.textContent = "resto del grupo fuera de esta carpeta";
      btn.replaceWith(nota);
    }
  });
  out.querySelectorAll(".btn-verify").forEach(btn => {
    const g = dupeGroups[Number(btn.dataset.group)];
    btn.textContent = "Verificar" + _estimacion(g.total);
    btn.addEventListener("click", () => _verifyGroup(out, Number(btn.dataset.group), token));
  });
  // Grupos ya verificados (caché): una sola consulta con todas las rutas de la página
  const all = dupeGroups.flatMap(g => g.paths);
  if (all.length) _pollStatus(out, all, token, { once: true });
}

async function _verifyGroup(out, gi, token) {
  const g = dupeGroups[gi];
  const btn = out.querySelector(`.btn-verify[data-group="${gi}"]`);
  if (btn) { btn.disabled = true; btn.textContent = "Calculando…"; }
  g.paths.slice(1).forEach(p => _setCell(out, p, `<span class="muted">calculando…</span>`));
  try {
    await post("/api/hash", { paths: g.paths });
  } catch (e) {
    console.error(e);
    if (btn) { btn.disabled = false; btn.textContent = "Verificar" + _estimacion(g.total); }
    return;
  }
  _pollStatus(out, g.paths, token);
}

async function _pollStatus(out, paths, token, { once = false } = {}) {
  if (token !== renderToken) return; // la vista ya se re-renderizó
  let res;
  try {
    res = (await get("/api/hash/status", { paths: paths.join("|") })).results;
  } catch (e) { console.error(e); return; }
  if (token !== renderToken) return;
  let pending = false;
  for (const p of paths) {
    const s = res[p];
    if (!s) continue;
    if (s.status === "done") _setCell(out, p, `<code class="hash-val">${esc(s.sha256.slice(0, 10))}</code>`);
    else if (s.status === "pending") {
      pending = true;
      // Si la celda aún tiene el botón (primera fila del grupo), el propio
      // botón hace de indicador — evita duplicar "calculando…" y cubre el
      // prefill de página: un grupo que se está hasheando desde otro sitio
      // muestra "Calculando…" en vez de un "Verificar" desfasado.
      const cell = out.querySelector(`.hash-cell[data-hash-path="${CSS.escape(p)}"]`);
      const btn = cell?.querySelector(".btn-verify");
      if (btn) { btn.disabled = true; btn.textContent = "Calculando…"; }
      else _setCell(out, p, `<span class="muted">calculando…</span>`);
    }
    else if (s.status === "error") _setCell(out, p, `<span class="dup-warn">error: ${esc(s.error)}</span>`);
    // unknown: se deja como esté (botón Verificar)
  }
  _updateVerdicts(out, res);
  if (pending && !once) setTimeout(() => _pollStatus(out, paths, token), 3000);
}

function _setCell(out, path, html) {
  const cell = out.querySelector(`.hash-cell[data-hash-path="${CSS.escape(path)}"]`);
  if (!cell) return;
  const btn = cell.querySelector(".btn-verify, .dup-badge");
  cell.innerHTML = html;
  if (btn) cell.prepend(btn); // la primera fila conserva el botón/badge delante
}

function _updateVerdicts(out, res) {
  dupeGroups.forEach((g, gi) => {
    const estados = g.paths.map(p => res[p]).filter(Boolean);
    if (estados.length !== g.paths.length) return;
    // Veredicto solo cuando TODO el grupo está en estado terminal: con el
    // worker de a uno, el primer archivo puede acabar en error mientras el
    // resto sigue calculando — decidir antes pintaría un veredicto que el
    // siguiente ciclo de sondeo destruiría.
    if (!estados.every(s => s.status === "done" || s.status === "error")) return;
    if (estados.every(s => s.status === "done")) {
      const hashes = new Set(estados.map(s => s.sha256));
      if (hashes.size === 1) _setBadge(out, gi, "dup-ok", "✓ Idénticos");
      else _setBadge(out, gi, "dup-warn", "⚠ Hay diferencias");
    } else {
      _setBadge(out, gi, "dup-warn", "⚠ incompleto");
    }
  });
}

function _setBadge(out, gi, cls, texto) {
  const btn = out.querySelector(`.btn-verify[data-group="${gi}"]`);
  if (!btn) return;
  const badge = document.createElement("span");
  // "dup-badge" distingue el veredicto de los spans de error (que también
  // usan dup-warn como color): solo el badge debe sobrevivir a _setCell.
  badge.className = "dup-badge " + cls;
  badge.textContent = texto;
  btn.replaceWith(badge);
}

// ── Árbol de carpetas (acota las búsquedas al subárbol) ──────────────────

function _onTreeSelect(path) {
  currentPath = path;
  _updateScopeLabel();
  if (window.innerWidth <= 760) {
    root().querySelector(".s-tree")?.classList.remove("open");
  }
  if (searched) runSearch(lastParams); // relanza la búsqueda en curso, ya acotada
}

function _updateScopeLabel() {
  const elScope = root().querySelector("#s-scope");
  if (!elScope) return;
  elScope.textContent = currentPath !== ROOT ? `Buscando en: ${currentPath}` : "";
}

// Divisor arrastrable del árbol (persistido), calcado del de Recuperable
function _setupTreeResizer(el) {
  const rez = el.querySelector("#s-resizer");
  if (!rez) return;
  try {
    const saved = localStorage.getItem("myfolder.searchTreeW");
    if (saved) el.style.setProperty("--search-tree-w", saved);
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
    el.style.setProperty("--search-tree-w", w + "px");
  });
  const end = () => {
    if (!dragging) return;
    dragging = false;
    document.body.style.userSelect = "";
    try {
      const w = el.style.getPropertyValue("--search-tree-w");
      if (w) localStorage.setItem("myfolder.searchTreeW", w);
    } catch (err) { /* ignore */ }
  };
  rez.addEventListener("pointerup", end);
  rez.addEventListener("pointercancel", end);
}
