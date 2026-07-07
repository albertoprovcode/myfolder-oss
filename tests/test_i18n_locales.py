import re
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parents[1] / "static" / "js" / "locales"
LOCALE_CODES = ["es", "en", "pt", "ar"]

def _keys(code):
    """Extrae las claves "..." : de un locale JS con un default export plano."""
    text = (LOCALES_DIR / f"{code}.js").read_text(encoding="utf-8")
    # claves tipo "scope.name": (antes de los dos puntos)
    return set(re.findall(r'"([a-z0-9_]+(?:\.[a-z0-9_]+)+)"\s*:', text))

def test_all_locale_files_exist():
    for code in LOCALE_CODES:
        assert (LOCALES_DIR / f"{code}.js").exists(), f"falta locales/{code}.js"

def test_locales_share_exact_key_set():
    es = _keys("es")
    assert es, "el locale es no tiene claves"
    for code in LOCALE_CODES[1:]:
        other = _keys(code)
        missing = es - other
        extra = other - es
        assert not missing, f"{code} le faltan claves: {sorted(missing)}"
        assert not extra, f"{code} tiene claves de más: {sorted(extra)}"

def test_index_has_four_locales_and_ar_is_rtl():
    idx = (LOCALES_DIR / "index.js").read_text(encoding="utf-8")
    for code in LOCALE_CODES:
        assert f'"{code}"' in idx or f"'{code}'" in idx, f"index.js no menciona {code}"
    m = re.search(r'\{[^}]*"ar"[^}]*\}', idx)
    assert m and "rtl" in m.group(0), "ar debe declararse dir rtl en index.js"
