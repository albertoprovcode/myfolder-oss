import { get, post } from "./api.js";
import { confirmDialog, toast } from "./modal.js";
import { initI18n, t, fmtNum, onLocaleChange } from "./i18n.js";
import { mountLangSelect } from "./langselect.js";

initI18n();
mountLangSelect(document.getElementById("lang-select"));
onLocaleChange(() => mountLangSelect(document.getElementById("lang-select")));

const VIEWS = ["dashboard", "explorer", "search", "map", "recoverable", "owners"];
const initialized = {};

async function showView(name) {
  if (!VIEWS.includes(name)) return;
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.querySelectorAll(".navbtn").forEach(b => b.classList.remove("active"));
  document.getElementById(`view-${name}`).classList.add("active");
  document.querySelector(`.navbtn[data-view="${name}"]`).classList.add("active");
  if (!initialized[name]) {
    try {
      const mod = await import(`./${name}.js`);
      initialized[name] = true;
      if (mod.init) await mod.init();
    } catch (e) {
      console.error(`Error en vista ${name}`, e);
      document.getElementById(`view-${name}`).innerHTML = `<p class="error">${t("common.error_view")}</p>`;
    }
  }
}

document.querySelectorAll(".navbtn").forEach(b =>
  b.addEventListener("click", () => showView(b.dataset.view)));

onLocaleChange(() => {
  if (_lastSummary) _updateIndexedAt(_lastSummary); // repinta la pill "Indexado:" al momento
  const active = document.querySelector(".view.active");
  if (!active) return;
  const name = active.id.replace("view-", "");
  initialized[name] = false;          // fuerza el repintado en el idioma nuevo
  showView(name);
});

document.getElementById("global-search").addEventListener("submit", async e => {
  e.preventDefault();
  const q = document.getElementById("q").value.trim();
  if (!q) return;
  await showView("search");
  const mod = await import("./search.js");
  if (mod.runFromQuery) mod.runFromQuery(q);
});

// Fecha de indexado / indicador de crawl en la topbar
let _pollTimer = null;
let _viewsIndexedAt = null; // indexed_at con el que se pintaron las vistas
let _lastSummary = null; // último /api/summary recibido, para repintar la pill al cambiar idioma

const POLL_CRAWLING_MS = 5000; // sondeo rápido mientras se indexa
const POLL_IDLE_MS = 60000; // sondeo lento en reposo

function _updateIndexedAt(s) {
  const el = document.getElementById("indexed-at");
  if (s.crawling) {
    const timePart = s.indexed_at ? s.indexed_at.split(" ")[1] || s.indexed_at : "";
    el.textContent = timePart
      ? t("header.indexing_since", { n: fmtNum(s.crawl_entries ?? s.files ?? 0), time: timePart })
      : t("header.indexing", { n: fmtNum(s.crawl_entries ?? s.files ?? 0) });
    el.classList.add("crawling");
  } else {
    el.textContent = s.indexed_at ? t("header.indexed_at", { when: s.indexed_at }) : "";
    el.classList.remove("crawling");
  }
  // Refresco por CAMBIO de indexed_at, no por "ver" acabar el crawl: cubre
  // también los indexados que esta pestaña no vio empezar (el programado de
  // las 13h, el de arranque del contenedor, otra pestaña, botón con 409).
  if (_viewsIndexedAt === null) {
    // Primera carga: las vistas nacen con este índice ("" si aún no hay ninguno,
    // para que el primer indexado que termine dispare el refresco).
    _viewsIndexedAt = s.indexed_at ?? "";
  } else if (!s.crawling && s.indexed_at && s.indexed_at !== _viewsIndexedAt) {
    _viewsIndexedAt = s.indexed_at;
    // Refrescar todas las vistas (la actual ya, el resto en su próxima visita).
    const activeView = document.querySelector(".view.active");
    Object.keys(initialized).forEach(k => delete initialized[k]);
    if (activeView) showView(activeView.id.replace(/^view-/, ""));
  }
}

async function _poll() {
  clearTimeout(_pollTimer);
  let crawling = false;
  try {
    const s = await get("/api/summary");
    _lastSummary = s;
    _updateIndexedAt(s);
    crawling = !!s.crawling;
  } catch (e) {
    // Red caída o backend reiniciando: se reintenta en el próximo tick.
  }
  _pollTimer = setTimeout(_poll, crawling ? POLL_CRAWLING_MS : POLL_IDLE_MS);
}

_poll(); // pinta el pill y deja el sondeo permanente en marcha

document.getElementById("btn-reindex").addEventListener("click", async () => {
  const ok = await confirmDialog({
    title: t("reindex.confirm_title"),
    message: t("reindex.confirm_body"),
    okText: t("reindex.confirm_ok"),
    cancelText: t("common.cancel"),
  });
  if (!ok) return;
  try {
    await post("/api/reindex");
    toast(t("reindex.started"), "ok");
  } catch (e) {
    toast(e.status === 409 ? t("reindex.busy") : t("reindex.failed"), "error");
    if (e.status !== 409) return;
    // Con 409 hay un crawl en marcha (lo lanzó otro): vigilarlo igualmente.
  }
  _poll(); // sondeo inmediato; la cadencia rápida se mantiene mientras dure el crawl
});

showView("dashboard");
