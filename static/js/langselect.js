// static/js/langselect.js
import { LOCALES } from "./locales/index.js";
import { getLocale, setLocale } from "./i18n.js";

// Listener de "click fuera" registrado UNA sola vez a nivel de módulo (evita
// acumular un listener en document por cada re-mount tras cambiar idioma).
let _outsideClickBound = false;
function _bindOutsideClickOnce() {
  if (_outsideClickBound) return;
  _outsideClickBound = true;
  document.addEventListener("click", () => {
    document.querySelectorAll(".lang-menu:not([hidden])").forEach(menu => {
      menu.hidden = true;
      menu.previousElementSibling?.setAttribute("aria-expanded", "false");
    });
  });
}

export function mountLangSelect(container) {
  function render() {
    const cur = getLocale();
    const curName = (LOCALES.find(l => l.code === cur) || LOCALES[0]).name;
    container.innerHTML =
      `<button class="lang-btn" aria-haspopup="listbox" aria-expanded="false">🌐 <span>${curName}</span></button>
       <ul class="lang-menu" role="listbox" hidden>
         ${LOCALES.map(l => `<li role="option" data-code="${l.code}" class="${l.code === cur ? "active" : ""}" dir="${l.dir}">${l.name}</li>`).join("")}
       </ul>`;
    const btn = container.querySelector(".lang-btn");
    const menu = container.querySelector(".lang-menu");
    const toggle = open => { menu.hidden = !open; btn.setAttribute("aria-expanded", String(open)); };
    btn.addEventListener("click", e => { e.stopPropagation(); toggle(menu.hidden); });
    menu.addEventListener("click", e => {
      const li = e.target.closest("[data-code]");
      if (!li) return;
      setLocale(li.dataset.code);   // dispara onLocaleChange → repinta vista + selector
    });
  }
  render();
  _bindOutsideClickOnce();
  // el selector se re-renderiza solo tras cambiar idioma (app.js lo re-monta en onLocaleChange)
}
