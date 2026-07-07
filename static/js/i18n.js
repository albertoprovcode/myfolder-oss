import { LOCALES, DICTS, FALLBACK } from "./locales/index.js";

const STORAGE_KEY = "myfolder.lang";
const SUPPORTED = LOCALES.map(l => l.code);
const _warned = new Set();
const _listeners = new Set();
let _locale = FALLBACK;

function _dirFor(code) {
  return (LOCALES.find(l => l.code === code) || {}).dir || "ltr";
}

function _detect() {
  let saved = null;
  try { saved = localStorage.getItem(STORAGE_KEY); } catch { /* storage bloqueado */ }
  if (saved && SUPPORTED.includes(saved)) return saved;
  for (const lang of navigator.languages || [navigator.language || ""]) {
    const code = String(lang).toLowerCase().split("-")[0];
    if (SUPPORTED.includes(code)) return code;
  }
  return FALLBACK;
}

export function getLocale() { return _locale; }

export function t(key, params = {}) {
  const dict = DICTS[_locale] || DICTS[FALLBACK];
  let s = dict[key];
  if (s === undefined) {
    s = DICTS[FALLBACK][key];
    if (s === undefined) {
      if (!_warned.has(key)) { console.warn(`[i18n] clave sin traducir: ${key}`); _warned.add(key); }
      return key;
    }
    if (!_warned.has(key)) { console.warn(`[i18n] ${_locale} sin clave, uso ${FALLBACK}: ${key}`); _warned.add(key); }
  }
  return s.replace(/\{(\w+)\}/g, (m, k) => (params[k] !== undefined ? params[k] : m));
}

export function fmtNum(n) { return new Intl.NumberFormat(_locale, { numberingSystem: "latn" }).format(n ?? 0); }

export function fmtDate(s) {
  if (!s) return "";
  // entrada del backend: "YYYY-MM-DD HH:MM"
  const d = new Date(s.replace(" ", "T"));
  if (isNaN(d)) return s;
  return new Intl.DateTimeFormat(_locale, { dateStyle: "medium", timeStyle: "short" }).format(d);
}

export function fmtSize(bytes) {
  const b = bytes ?? 0;
  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  let v = b, i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  const digits = i === 0 ? 0 : 1;
  return `${new Intl.NumberFormat(_locale, { numberingSystem: "latn", minimumFractionDigits: digits, maximumFractionDigits: digits }).format(v)} ${units[i]}`;
}

export function hydrateStatic() {
  document.querySelectorAll("[data-i18n]").forEach(el => {
    el.textContent = t(el.getAttribute("data-i18n"));
  });
  document.querySelectorAll("[data-i18n-attr]").forEach(el => {
    // formato: "placeholder:key" o "title:key;placeholder:key2"
    el.getAttribute("data-i18n-attr").split(";").forEach(pair => {
      const [attr, key] = pair.split(":");
      if (attr && key) el.setAttribute(attr.trim(), t(key.trim()));
    });
  });
}

export function onLocaleChange(cb) { _listeners.add(cb); }

export function setLocale(code) {
  if (!SUPPORTED.includes(code)) return;
  _locale = code;
  try { localStorage.setItem(STORAGE_KEY, code); } catch { /* storage bloqueado */ }
  document.documentElement.lang = code;
  document.documentElement.dir = _dirFor(code);
  hydrateStatic();
  _listeners.forEach(cb => { try { cb(code); } catch (e) { console.error(e); } });
}

export function initI18n() {
  _locale = _detect();
  document.documentElement.lang = _locale;
  document.documentElement.dir = _dirFor(_locale);
  hydrateStatic();
}
