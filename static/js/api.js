// La app puede servirse bajo un prefijo (p. ej. detrás de un proxy inverso en /proxy/8017/):
// las rutas "/api/..." se resuelven contra el directorio actual, no contra la raíz.
const BASE = location.pathname.endsWith("/") ? location.pathname : "/";

function withBase(path) {
  return path.startsWith("/") ? BASE + path.slice(1) : path;
}

export async function get(path, params = {}) {
  const url = new URL(withBase(path), window.location.origin);
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
  });
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error(`API ${path} → ${r.status}`);
  return r.json();
}

export async function post(url, body = undefined) {
  const opts = { method: "POST" };
  if (body !== undefined) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(body);
  }
  const r = await fetch(withBase(url), opts);
  if (!r.ok) {
    const b = await r.json().catch(() => ({}));
    throw Object.assign(new Error(b.detail || r.statusText), { status: r.status });
  }
  return r.json();
}

const _ESC_MAP = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => _ESC_MAP[c]);
}
