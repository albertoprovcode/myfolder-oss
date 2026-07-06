// Diálogos y avisos con el estilo de la app — sustituyen a confirm()/alert() nativos.

function _root() {
  let r = document.getElementById("modal-root");
  if (!r) {
    r = document.createElement("div");
    r.id = "modal-root";
    document.body.appendChild(r);
  }
  return r;
}

/** Diálogo de confirmación. Devuelve Promise<boolean>. */
export function confirmDialog({
  title = "¿Confirmar?", message = "",
  okText = "Aceptar", cancelText = "Cancelar", danger = false,
} = {}) {
  return new Promise(resolve => {
    const back = document.createElement("div");
    back.className = "modal-backdrop";
    back.innerHTML =
      `<div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-t">
         <h3 class="modal-title" id="modal-t"></h3>
         <p class="modal-msg"></p>
         <div class="modal-actions">
           <button class="btn ghost" data-act="cancel"></button>
           <button class="btn${danger ? " danger" : ""}" data-act="ok"></button>
         </div>
       </div>`;
    back.querySelector(".modal-title").textContent = title;
    back.querySelector(".modal-msg").textContent = message;
    back.querySelector('[data-act="cancel"]').textContent = cancelText;
    back.querySelector('[data-act="ok"]').textContent = okText;
    _root().appendChild(back);
    requestAnimationFrame(() => back.classList.add("open"));

    function close(val) {
      back.classList.remove("open");
      setTimeout(() => back.remove(), 150);
      document.removeEventListener("keydown", onKey);
      resolve(val);
    }
    function onKey(e) {
      if (e.key === "Escape") close(false);
      else if (e.key === "Enter") close(true);
    }
    back.addEventListener("click", e => {
      if (e.target === back) return close(false);        // clic fuera = cancelar
      const act = e.target.dataset.act;
      if (act === "ok") close(true);
      else if (act === "cancel") close(false);
    });
    document.addEventListener("keydown", onKey);
    back.querySelector('[data-act="ok"]').focus();
  });
}

/** Aviso efímero abajo-centrado. kind: "info" | "ok" | "error". */
export function toast(message, kind = "info") {
  const t = document.createElement("div");
  t.className = `toast toast-${kind}`;
  t.textContent = message;
  _root().appendChild(t);
  requestAnimationFrame(() => t.classList.add("open"));
  setTimeout(() => {
    t.classList.remove("open");
    setTimeout(() => t.remove(), 300);
  }, 3500);
}
