"""TDD para el precálculo de agregaciones del Resumen (tabla `agg`).

Contrato: los valores servidos desde caché deben ser IDÉNTICOS a los que
devolvería la consulta en vivo. Estos tests comprueban tres caminos:
"cache-hit" (tras build_index, que llama a precompute_dashboard),
"cache-miss" (tabla agg presente pero vacía, BD creada solo con
create_schema sin precompute) y BD antigua (tabla agg inexistente,
ejercitando el except sqlite3.OperationalError de Storage._read_agg).
"""
from __future__ import annotations

import json

import pytest

from app import db
from app.crawler.build import build_index
from app.storage import Storage
from tests.helpers import DEFAULT_EPOCH, add_entry, make_store


@pytest.fixture
def data_root(tmp_path):
    root = tmp_path / "data"
    (root / "Music" / "sub").mkdir(parents=True)
    (root / "Video").mkdir()
    (root / "Music" / "a.mp3").write_bytes(b"x" * 100)
    (root / "Music" / "sub" / "b.flac").write_bytes(b"x" * 200)
    (root / "Video" / "c.mkv").write_bytes(b"x" * 1000)
    return str(root)


def test_build_index_populates_agg_table(tmp_path, data_root):
    dbfile = str(tmp_path / "myfolder.db")
    build_index(dbfile, data_root)

    conn = db.open_ro(dbfile)
    rows = conn.execute("SELECT key FROM agg ORDER BY key").fetchall()
    keys = {r["key"] for r in rows}
    assert keys == {"summary", "types", "extensions_size", "age_mtime",
                    "age_atime", "removable"}


def test_summary_matches_live_computation_after_build(tmp_path, data_root):
    dbfile = str(tmp_path / "myfolder.db")
    build_index(dbfile, data_root)

    store = Storage(dbfile)
    cached = store.summary()

    conn = db.open_ro(dbfile)
    blob = json.loads(
        conn.execute("SELECT json FROM agg WHERE key='summary'").fetchone()["json"])

    assert cached == blob
    assert cached == {"files": 3, "dirs": 4, "total_size": 1300,
                       "total_size_h": "1.3 KB"}


def test_types_matches_cached_blob_after_build(tmp_path, data_root):
    dbfile = str(tmp_path / "myfolder.db")
    build_index(dbfile, data_root)

    store = Storage(dbfile)
    cached = store.types(path=None)

    conn = db.open_ro(dbfile)
    blob = json.loads(
        conn.execute("SELECT json FROM agg WHERE key='types'").fetchone()["json"])
    assert cached == blob
    assert cached["items"]


def test_age_uses_cache_for_global_but_live_for_path(tmp_path, data_root):
    dbfile = str(tmp_path / "myfolder.db")
    build_index(dbfile, data_root)

    store = Storage(dbfile)
    global_age = store.age(path=None, field="mtime")
    conn = db.open_ro(dbfile)
    blob = json.loads(
        conn.execute("SELECT json FROM agg WHERE key='age_mtime'").fetchone()["json"])
    assert global_age == blob

    # Con path concreto, sigue en vivo: sin filtro de tiempo "now" del blob,
    # debe reflejar solo las entradas bajo ese path (no puede venir del blob
    # global, que no tiene ese desglose).
    scoped = store.age(path="/data/Music", field="mtime")
    assert scoped != global_age
    total_scoped = sum(b["count"] for b in scoped["buckets"])
    assert total_scoped == 2  # a.mp3 + b.flac


def test_extensions_size_cache_respects_limit(tmp_path, data_root):
    dbfile = str(tmp_path / "myfolder.db")
    build_index(dbfile, data_root)

    store = Storage(dbfile)
    limited = store.extensions(path=None, by="size", limit=2)["items"]
    full = store.extensions(path=None, by="size", limit=500)["items"]

    assert len(limited) == 2
    assert limited == full[:2]

    conn = db.open_ro(dbfile)
    blob = json.loads(
        conn.execute(
            "SELECT json FROM agg WHERE key='extensions_size'").fetchone()["json"])
    assert full == blob["items"]


def test_removable_cache_used_when_days_matches(tmp_path, data_root):
    dbfile = str(tmp_path / "myfolder.db")
    build_index(dbfile, data_root)

    conn = db.open_ro(dbfile)
    blob = json.loads(
        conn.execute("SELECT json FROM agg WHERE key='removable'").fetchone()["json"])
    days_cached = blob["days"]

    store = Storage(dbfile)
    cached = store.removable(days=days_cached)
    assert cached == {"count": blob["count"], "size": blob["size"],
                       "size_h": blob["size_h"]}


def test_removable_falls_back_live_when_days_differ(tmp_path, data_root):
    dbfile = str(tmp_path / "myfolder.db")
    build_index(dbfile, data_root)

    store = Storage(dbfile)
    # días distinto al cacheado (por defecto 365): forzamos un valor absurdo
    # para asegurar que no coincide y así se ejercita el camino en vivo.
    live = store.removable(days=1)
    assert live["count"] >= 0  # no debe lanzar y debe calcular en vivo


# ------------------------------------------------ cache-miss (tabla agg vacía)

def test_summary_live_fallback_when_agg_empty(tmp_path):
    """BD creada solo con create_schema (sin build_index/precompute): la
    tabla agg existe pero está vacía (cache-miss por clave ausente).
    summary() debe caer al cómputo en vivo sin fallar."""
    store, conn = make_store(tmp_path)
    add_entry(conn, "a.mp3", "/data/Music", size=100, extension="mp3")
    add_entry(conn, "b.mkv", "/data/Video", size=1000, extension="mkv")
    add_entry(conn, "Music", "/data", type="directory", size=100)

    assert store.summary() == {"files": 2, "dirs": 1, "total_size": 1100,
                                "total_size_h": "1.1 KB"}


def test_types_live_fallback_when_agg_empty(tmp_path):
    """Tabla agg presente pero vacía (cache-miss): types() calcula en vivo."""
    store, conn = make_store(tmp_path)
    add_entry(conn, "a.mp3", "/data/Music", size=100, extension="mp3")

    t = store.types(path=None)["items"]
    assert t[0]["category"] == "audio"


def test_age_live_fallback_when_agg_empty(tmp_path):
    """Tabla agg presente pero vacía (cache-miss): age() calcula en vivo."""
    store, conn = make_store(tmp_path)
    now = DEFAULT_EPOCH
    add_entry(conn, "reciente.txt", "/data/Docs", size=10, mtime=now - 5 * 86400)
    add_entry(conn, "antiguo.txt", "/data/Docs", size=99, mtime=now - 800 * 86400)

    buckets = store.age(path=None, field="mtime", now=now)["buckets"]
    assert buckets[0]["count"] == 1 and buckets[-1]["size"] == 99


def test_extensions_live_fallback_when_agg_empty(tmp_path):
    """Tabla agg presente pero vacía (cache-miss): extensions() calcula en
    vivo."""
    store, conn = make_store(tmp_path)
    add_entry(conn, "a.mp3", "/data/Music", size=100, extension="mp3")
    add_entry(conn, "b.pdf", "/data/Docs", size=50, extension="pdf")

    items = store.extensions(path=None, by="size", limit=1)["items"]
    assert len(items) == 1 and items[0]["ext"] == "mp3"


def test_removable_live_fallback_when_agg_empty(tmp_path):
    """Tabla agg presente pero vacía (cache-miss): removable() calcula en
    vivo."""
    store, conn = make_store(tmp_path)
    now = DEFAULT_EPOCH + 400 * 86400
    add_entry(conn, "viejo.iso", "/data/Backup", size=500)
    r = store.removable(days=365, now=now)
    assert r == {"count": 1, "size": 500, "size_h": "500 B"}


# ------------------------------------------------ BD antigua (sin tabla agg)

def test_dashboard_methods_survive_missing_agg_table(tmp_path):
    """BD realmente antigua: la tabla agg no existe en absoluto (se hace
    DROP tras create_schema, simulando una BD de antes de introducir el
    precálculo). _read_agg debe capturar sqlite3.OperationalError y caer
    al cómputo en vivo en summary(), types() y age() sin reventar.

    Sin el except sqlite3.OperationalError en Storage._read_agg, este test
    fallaría con sqlite3.OperationalError: no such table: agg."""
    store, conn = make_store(tmp_path)
    conn.execute("DROP TABLE agg")
    conn.commit()

    add_entry(conn, "a.mp3", "/data/Music", size=100, extension="mp3")
    add_entry(conn, "b.mkv", "/data/Video", size=1000, extension="mkv")
    add_entry(conn, "Music", "/data", type="directory", size=100)

    assert store.summary() == {"files": 2, "dirs": 1, "total_size": 1100,
                                "total_size_h": "1.1 KB"}

    t = store.types(path=None)["items"]
    cats = {it["category"]: it["size"] for it in t}
    assert cats == {"audio": 100, "video": 1000}

    now = DEFAULT_EPOCH
    buckets = store.age(path=None, field="mtime", now=now)["buckets"]
    assert sum(b["count"] for b in buckets) == 2
