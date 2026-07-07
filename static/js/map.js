import { get, esc } from "./api.js";
import { treemap } from "./charts.js";
import { fmtNum, t } from "./i18n.js";

const ROOT = "/data";
let currentPath = ROOT;
const rootEl = () => document.getElementById("view-map");

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

async function loadMap(path) {
  currentPath = path;
  const el = rootEl();
  el.querySelector("#map-crumbs").innerHTML = crumbsHtml(path);
  const chartEl = el.querySelector("#map-chart");
  const info = el.querySelector("#map-info");
  info.textContent = t("common.loading");
  try {
    const data = await get("/api/tree", { path });
    const children = data.children ?? [];
    const c = data.current;
    info.textContent = c
      ? t("map.items", { size: c.size_h, n: fmtNum(c.items) })
      : "";
    if (!children.length) {
      chartEl.innerHTML = `<p class="muted">${t("map.empty")}</p>`;
      return;
    }
    chartEl.innerHTML = ""; // limpiar antes de montar
    treemap(chartEl, children, (p) => { if (p) loadMap(p); });
  } catch (e) {
    console.error(e);
    chartEl.innerHTML = `<p class="error">${t("map.error")}</p>`;
  }
}

export async function init() {
  const el = rootEl();
  el.innerHTML =
    `<div class="map-header">
       <div class="crumbs" id="map-crumbs"></div>
       <span id="map-info" class="muted"></span>
     </div>
     <div id="map-chart" class="map-chart"></div>`;
  el.querySelector("#map-crumbs").addEventListener("click", e => {
    const a = e.target.closest("[data-path]");
    if (a) loadMap(a.dataset.path);
  });
  await loadMap(ROOT);
}
