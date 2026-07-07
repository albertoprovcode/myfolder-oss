# tests/test_static_i18n.py
import glob
import os
import re
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1] / "static" / "index.html").read_text(encoding="utf-8")

def test_nav_buttons_use_data_i18n():
    # cada navbtn con data-view debe tener un <span data-i18n=...>
    navblock = re.search(r'<nav class="topnav">(.*?)</nav>', HTML, re.S).group(1)
    buttons = re.findall(r'<button[^>]*data-view="[^"]+"[^>]*>(.*?)</button>', navblock, re.S)
    assert buttons, "no se encontraron navbtn"
    for b in buttons:
        assert "data-i18n" in b, f"navbtn sin data-i18n: {b}"

def test_global_search_placeholder_is_i18n():
    assert re.search(r'id="q"[^>]*data-i18n-attr="[^"]*placeholder:', HTML), \
        "el buscador global debe localizar el placeholder vía data-i18n-attr"

def test_no_hardcoded_es_ES_numberformat():
    root = os.path.join(os.path.dirname(__file__), "..", "static", "js")
    offenders = []
    for p in glob.glob(os.path.join(root, "**", "*.js"), recursive=True):
        if p.endswith("i18n.js"):
            continue  # el motor es el único sitio con Intl explícito
        txt = open(p, encoding="utf-8").read()
        if 'NumberFormat("es' in txt or "NumberFormat('es" in txt:
            offenders.append(os.path.basename(p))
    assert not offenders, f"quedan NumberFormat es-ES hardcodeados: {offenders}"
