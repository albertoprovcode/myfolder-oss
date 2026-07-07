# tests/test_langselect.py
from pathlib import Path
JS = (Path(__file__).resolve().parents[1] / "static" / "js" / "langselect.js").read_text(encoding="utf-8")

def test_uses_locales_metadata():
    assert "LOCALES" in JS and "setLocale" in JS and "getLocale" in JS

def test_index_html_has_lang_container():
    html = (Path(__file__).resolve().parents[1] / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="lang-select"' in html
