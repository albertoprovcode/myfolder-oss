/* global echarts */
import { esc } from "./api.js";
const DARK = { backgroundColor: "transparent",
  textStyle: { color: "#e7edf3" },
  color: ["#1d4ed8", "#c2410c", "#15803d", "#6d28d9", "#be123c", "#0e7490", "#b45309"] };
// Etiquetas siempre en claro y sin borde (evita el texto oscuro con halo blanco por defecto de ECharts)
const LABEL = { color: "#e7edf3", textBorderWidth: 0 };
const AXIS = { axisLabel: { color: "#e7edf3" } };
// RTL: el nombre (etiquetas de categoría, en árabe) va al lado por donde
// empieza la lectura. No se toca la geometría de las barras (siguen
// creciendo igual, es solo dónde se ancla el eje de categorías).
const isRTL = () => document.documentElement.dir === "rtl";

const _chartEls = new Set();
let _resizeBound = false;
function mount(el) {
  echarts.getInstanceByDom(el)?.dispose();
  const chart = echarts.init(el, null, { renderer: "canvas" });
  _chartEls.add(el);
  if (!_resizeBound) {
    _resizeBound = true;
    // Un único listener global: redimensiona solo las instancias vivas (las dispuestas se ignoran).
    window.addEventListener("resize", () => _chartEls.forEach(e => echarts.getInstanceByDom(e)?.resize()));
  }
  return chart;
}

export function donut(el, items, { nameKey, valueKey }) {
  const chart = mount(el);
  chart.setOption({ ...DARK, tooltip: { trigger: "item" },
    series: [{ type: "pie", radius: ["45%", "70%"],
      label: LABEL, labelLine: { lineStyle: { color: "#8a97a6" } },
      data: items.map(i => ({ name: i[nameKey], value: i[valueKey] })) }] });
  return chart;
}

export function bars(el, items, { nameKey, valueKey }) {
  const chart = mount(el);
  const rtl = isRTL();
  chart.setOption({ ...DARK, tooltip: {}, grid: { left: rtl ? 16 : 90, right: rtl ? 90 : 16, top: 10, bottom: 20 },
    xAxis: { type: "value", ...AXIS },
    yAxis: { type: "category", inverse: true, position: rtl ? "right" : "left", ...AXIS, data: items.map(i => i[nameKey]) },
    series: [{ type: "bar", data: items.map(i => i[valueKey]) }] });
  return chart;
}

export function stacked(el, buckets) {
  const chart = mount(el);
  chart.setOption({ ...DARK, tooltip: { trigger: "axis" },
    grid: { left: 50, right: 16, top: 10, bottom: 24 },
    xAxis: { type: "category", ...AXIS, data: buckets.map(b => b.label) },
    yAxis: { type: "value", ...AXIS },
    series: [{ type: "bar", data: buckets.map(b => b.count) }] });
  return chart;
}

// Paleta del Mapa (elegida por el usuario, 2026-07-04): zafiro profundo →
// cobalto → índigo → marino → uva → carmesí. Asignación por RANKING de
// tamaño: la carpeta más grande recibe el tono más profundo y tranquilo,
// las pequeñas van ganando viveza. El texto claro contrasta ≥5.7:1 en los
// 10 pasos (calculado, no a ojo).
const TREEMAP_RAMP = ["#0A1628", "#132744", "#1C3860", "#25497C", "#2E5A98",
                      "#372E98", "#6C2E98", "#982E8F", "#982E5A", "#98372E"];

/** Parte un nombre largo en líneas de ~14 caracteres SIN cortar palabras
 * (máx. 3 líneas): mejor un salto que unos puntos suspensivos. Los nombres
 * cortos salen intactos; el ocultado en bloques minúsculos sigue siendo de
 * ECharts. */
function _partirNombre(nombre, ancho = 14, maxLineas = 3) {
  if (nombre.length <= ancho) return nombre;
  const palabras = nombre.split(" ");
  const lineas = [];
  let actual = "";
  for (let i = 0; i < palabras.length; i++) {
    const p = palabras[i];
    if (actual && (actual + " " + p).length > ancho) {
      lineas.push(actual);
      if (lineas.length === maxLineas - 1) {
        // Última línea: se lleva todo lo que queda (ECharts recorta si no cabe).
        actual = palabras.slice(i).join(" ");
        break;
      }
      actual = p;
    } else {
      actual = actual ? actual + " " + p : p;
    }
  }
  lineas.push(actual);
  return lineas.join("\n");
}

export function treemap(el, children, onClick) {
  const chart = mount(el);
  const porTamano = [...children].sort((a, b) => (b.size || 0) - (a.size || 0));
  const rango = new Map(porTamano.map((c, i) => [c.path, i]));
  const tramo = Math.max(1, children.length - 1);
  const total = children.reduce((s, c) => s + (c.size || 0), 0) || 1;
  chart.setOption({ ...DARK, tooltip: { formatter: p => `${esc(p.name)}: ${esc(p.data.size_h)}` },
    series: [{ type: "treemap", roam: false, breadcrumb: { show: false },
      itemStyle: { borderColor: "#1a212b", borderWidth: 2, gapWidth: 2 },
      // OJO: ni rich text ni overflow:"break" aquí — ambos desanclan la
      // etiqueta del centro y pintan fuera de los bloques (comprobado dos
      // veces en prod). El aire nombre↔tamaño se da solo con lineHeight.
      label: { ...LABEL, formatter: p => p.data.etiqueta },
      upperLabel: { ...LABEL },
      data: children.map(c => {
        const idx = Math.round((rango.get(c.path) / tramo) * (TREEMAP_RAMP.length - 1));
        // Letra ligeramente proporcional al peso de la carpeta (11-17px).
        const fs = Math.max(11, Math.min(17, Math.round(11 + Math.sqrt((c.size || 0) / total) * 9)));
        return { name: c.name, value: c.size, size_h: c.size_h, path: c.path,
                 etiqueta: `${_partirNombre(c.name)}\n${c.size_h}`,
                 itemStyle: { color: TREEMAP_RAMP[idx] },
                 label: { fontSize: fs, lineHeight: Math.round(fs * 1.5) } };
      }) }] });
  if (onClick) chart.on("click", p => onClick(p.data.path));
  return chart;
}
