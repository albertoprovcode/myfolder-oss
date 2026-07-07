import es from "./es.js";
import en from "./en.js";
import pt from "./pt.js";
import ar from "./ar.js";

export const LOCALES = [
  { code: "es", name: "Español",   dir: "ltr" },
  { code: "en", name: "English",   dir: "ltr" },
  { code: "pt", name: "Português", dir: "ltr" },
  { code: "ar", name: "العربية",   dir: "rtl" },
];
export const DICTS = { es, en, pt, ar };
export const FALLBACK = "es";
