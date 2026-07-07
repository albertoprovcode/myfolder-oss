# tests/test_rtl_css.py
from pathlib import Path

CSS = (Path(__file__).resolve().parents[1] / "static" / "css" / "style.css").read_text(encoding="utf-8")


def test_has_rtl_block():
    assert '[dir="rtl"]' in CSS, "falta el bloque [dir=rtl] en style.css"


def test_uses_logical_properties():
    # al menos algunas propiedades lógicas migradas
    assert "inline-start" in CSS or "inline-end" in CSS, "no se migró a propiedades lógicas"
