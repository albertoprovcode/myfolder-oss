/**
 * Paginador con números clicables, compartido por Buscar/Recuperable/Explorador.
 *
 *   renderPager(el, { page, totalPages, onPage, info });
 *
 * - page: página actual, 0-based. totalPages: total (>=1).
 * - onPage(n): callback al pulsar Anterior/Siguiente/un número (n 0-based).
 * - info (opcional): texto tipo "1.234 resultados · página 2 de 99".
 * - Sin estado propio: la vista guarda su página y re-renderiza al cambiar.
 * - totalPages <= 1 → solo pinta info (si existe), sin botones.
 */
export function renderPager(el, { page, totalPages, onPage, info } = {}) {
  if (!el) return;
  el.innerHTML = "";

  const addInfo = () => {
    if (!info) return;
    const s = document.createElement("span");
    s.className = "muted";
    s.textContent = info;
    el.appendChild(s);
  };

  if (totalPages <= 1) {
    addInfo();
    return;
  }

  const btn = (label, target, { disabled = false, current = false } = {}) => {
    const b = document.createElement("button");
    b.className = "btn ghost" + (current ? " page-current" : "");
    b.textContent = label;
    b.disabled = disabled || current;
    if (!disabled && !current) b.addEventListener("click", () => onPage(target));
    return b;
  };

  el.appendChild(btn("‹ Anterior", page - 1, { disabled: page === 0 }));
  for (const p of _pageWindow(page, totalPages)) {
    if (p === "…") {
      const s = document.createElement("span");
      s.className = "muted";
      s.textContent = "…";
      el.appendChild(s);
    } else {
      el.appendChild(btn(String(p + 1), p, { current: p === page }));
    }
  }
  addInfo();
  el.appendChild(btn("Siguiente ›", page + 1, { disabled: page >= totalPages - 1 }));
}

/** Páginas a mostrar (0-based): primera, última y ventana alrededor de la
 * actual, con "…" en los huecos. */
function _pageWindow(current, total) {
  const wanted = new Set([0, total - 1, current - 1, current, current + 1]);
  const list = [...wanted].filter(p => p >= 0 && p < total).sort((a, b) => a - b);
  const out = [];
  let prev = null;
  for (const p of list) {
    if (prev !== null && p - prev > 1) out.push("…");
    out.push(p);
    prev = p;
  }
  return out;
}
