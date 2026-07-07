import { get, esc } from "./api.js";
import { t } from "./i18n.js";

const ROOT = "/data";

/**
 * Árbol de carpetas reutilizable (carga perezosa sobre /api/tree).
 *
 *   const tree = mountTree(containerUl, { onSelect: path => … });
 *   tree.select("/data");   // resalta SIN disparar onSelect
 *
 * - container: <ul class="tree"> vacío donde se pinta el árbol.
 * - onSelect(path): callback al pinchar el NOMBRE de una carpeta (el
 *   componente ya ha resaltado el nodo cuando llama).
 * - La caché de hijos es por instancia: cada init de vista crea árbol nuevo,
 *   así el refresco post-reindexado de app.js renueva los datos.
 * - Reutiliza las clases CSS existentes del árbol (.tree-node, .tree-row…).
 */
export function mountTree(container, { onSelect } = {}) {
  const cache = new Map();

  function buildChildrenHtml(children) {
    if (!children.length) return "";
    const max = Math.max(1, ...children.map(c => c.size || 0));
    return children.map(ch => {
      const barW = Math.round((ch.size / max) * 100);
      return `<li class="tree-node" data-path="${esc(ch.path)}">
        <div class="tree-row">
          <span class="tree-caret" title="${esc(t("explorer.expand"))}">▸</span>
          <span class="tree-name" data-path="${esc(ch.path)}">${esc(ch.name)}</span>
          <span class="tree-size muted">${esc(ch.size_h)}</span>
          <div class="tree-bar-wrap"><div class="bar tree-bar" style="width:${esc(barW)}%"></div></div>
        </div>
        <ul class="tree tree-children" data-loaded="false"></ul>
      </li>`;
    }).join("");
  }

  async function fetchChildren(path) {
    if (cache.has(path)) return cache.get(path);
    const data = await get("/api/tree", { path });
    const children = data.children ?? [];
    cache.set(path, children);
    return children;
  }

  async function expandNode(li) {
    const path = li.dataset.path;
    const childUl = li.querySelector(":scope > .tree-children");
    if (!childUl) return;
    const caret = li.querySelector(":scope > .tree-row > .tree-caret");

    if (childUl.dataset.loaded === "true") {
      const isCollapsed = !li.classList.contains("expanded");
      li.classList.toggle("expanded", isCollapsed);
      if (caret) caret.textContent = isCollapsed ? "▾" : "▸";
      return;
    }

    if (caret) caret.textContent = "…";
    try {
      const children = await fetchChildren(path);
      childUl.dataset.loaded = "true";
      if (children.length === 0) {
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
      if (caret) caret.textContent = "!"; // reintentable: data-loaded sigue "false"
    }
  }

  function bindTreeEvents(scopeEl) {
    scopeEl.querySelectorAll(":scope > .tree-node").forEach(li => {
      const row = li.querySelector(":scope > .tree-row");
      const caret = row?.querySelector(".tree-caret");
      const name = row?.querySelector(".tree-name");

      caret?.addEventListener("click", e => {
        e.stopPropagation();
        expandNode(li);
      });

      name?.addEventListener("click", e => {
        e.stopPropagation();
        highlight(li.dataset.path);
        onSelect?.(li.dataset.path);
      });
    });
  }

  function highlight(path) {
    container.querySelectorAll(".tree-node.sel").forEach(n => n.classList.remove("sel"));
    const target = container.querySelector(`.tree-node[data-path="${CSS.escape(path)}"]`);
    target?.classList.add("sel");
  }

  (async function initRoot() {
    container.innerHTML = `<li class="muted">${t("common.loading")}</li>`;
    try {
      const children = await fetchChildren(ROOT);
      container.innerHTML =
        `<li class="tree-node expanded sel" data-path="${esc(ROOT)}">
          <div class="tree-row">
            <span class="tree-caret" title="${esc(t("explorer.collapse"))}">▾</span>
            <span class="tree-name" data-path="${esc(ROOT)}">data</span>
          </div>
          <ul class="tree tree-children" data-loaded="true">${buildChildrenHtml(children)}</ul>
        </li>`;
      bindTreeEvents(container);
      const rootChildrenUl = container.querySelector(":scope > .tree-node > .tree-children");
      if (rootChildrenUl) bindTreeEvents(rootChildrenUl);
    } catch (e) {
      console.error(e);
      container.innerHTML = `<li class="error">${t("explorer.tree_error")}</li>`;
    }
  })();

  return { select: highlight, root: ROOT };
}
