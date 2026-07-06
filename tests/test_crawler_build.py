import os

import pytest

from app import db
from app.crawler.build import build_index
from app.crawler.state import CrawlState


@pytest.fixture
def data_root(tmp_path):
    root = tmp_path / "data"
    (root / "Music" / "sub").mkdir(parents=True)
    (root / "Video").mkdir()
    (root / "Music" / "a.mp3").write_bytes(b"x" * 100)
    (root / "Music" / "sub" / "b.flac").write_bytes(b"x" * 200)
    (root / "Video" / "c.mkv").write_bytes(b"x" * 1000)
    return str(root)


def test_build_index_full(tmp_path, data_root):
    dbfile = str(tmp_path / "myfolder.db")
    state = CrawlState()
    result = build_index(dbfile, data_root, state=state)

    assert os.path.exists(dbfile)
    assert not os.path.exists(dbfile + ".building")
    # 3 files + 3 dirs (Music, sub, Video) + raíz = 7 filas
    assert result["entries"] == 7
    assert state.entries == 7

    conn = db.open_ro(dbfile)
    files = conn.execute("SELECT COUNT(*) c FROM entries WHERE type='file'").fetchone()["c"]
    assert files == 3
    root_row = conn.execute(
        "SELECT * FROM entries WHERE parent_path='' AND type='directory'").fetchone()
    assert root_row["name"] == "data"
    assert root_row["size"] == 1300
    assert root_row["file_count"] == 3 and root_row["dir_count"] == 3

    # Los shares cuelgan del path lógico /data, no del path físico de data_root.
    music_dir = conn.execute(
        "SELECT * FROM entries WHERE type='directory' AND name='Music'").fetchone()
    assert music_dir["parent_path"] == "/data"
    music_file = conn.execute(
        "SELECT * FROM entries WHERE type='file' AND name='a.mp3'").fetchone()
    assert music_file["parent_path"] == "/data/Music"

    space = conn.execute("SELECT * FROM spaceinfo WHERE path=?", ("/data",)).fetchone()
    assert space is not None and space["total"] > 0
    space_share = conn.execute(
        "SELECT * FROM spaceinfo WHERE path=?", ("/data/Music",)).fetchone()
    assert space_share is not None and space_share["total"] > 0

    ii = conn.execute("SELECT * FROM indexinfo").fetchone()
    assert ii["end_at"] is not None and ii["entries"] == 7

    hit = conn.execute("SELECT rowid FROM entries_fts WHERE name LIKE '%flac%'").fetchone()
    assert hit is not None


def test_build_failure_keeps_previous_db(tmp_path, data_root):
    dbfile = str(tmp_path / "myfolder.db")
    build_index(dbfile, data_root)
    before = os.path.getmtime(dbfile)

    with pytest.raises(FileNotFoundError):
        build_index(dbfile, str(tmp_path / "no-existe"))

    assert os.path.getmtime(dbfile) == before  # el vivo no se tocó
    assert not os.path.exists(dbfile + ".building")


def test_writer_failure_cleans_up_and_raises(tmp_path, data_root, monkeypatch):
    import sqlite3

    from app import db as db_module
    from app.crawler import build as build_module

    dbfile = str(tmp_path / "myfolder.db")
    build_index(dbfile, data_root)  # db vivo previo
    before = os.path.getmtime(dbfile)

    monkeypatch.setattr(build_module.db, "INSERT_ENTRY",
                        "INSERT INTO no_existe(x) VALUES (:name)", raising=True)
    with pytest.raises(sqlite3.OperationalError):
        build_index(dbfile, data_root)

    assert os.path.getmtime(dbfile) == before
    assert not os.path.exists(dbfile + ".building")


def test_root_row_parent_path_is_empty_for_nested_data_root(tmp_path):
    nested = tmp_path / "a" / "b" / "data"
    (nested / "docs").mkdir(parents=True)
    (nested / "docs" / "f.txt").write_bytes(b"x" * 10)
    dbfile = str(tmp_path / "myfolder.db")

    build_index(dbfile, str(nested))

    conn = db.open_ro(dbfile)
    # El nombre de la raíz sale de ROOT_PATH ("/data" -> "data"), no del basename
    # físico de data_root: aquí data_root también se llama "data" por coincidencia,
    # pero lo que se está comprobando es el basename de ROOT_PATH.
    root_row = conn.execute(
        "SELECT * FROM entries WHERE type='directory' AND name=?", ("data",)).fetchone()
    assert root_row is not None
    assert root_row["parent_path"] == ""


def test_build_then_storage_tree_and_space(tmp_path, data_root):
    from app.storage import Storage

    dbfile = str(tmp_path / "myfolder.db")
    build_index(dbfile, data_root)
    store = Storage(dbfile)
    tree = store.tree(None)
    assert [c["name"] for c in tree["children"]] != []
    assert all(c["path"].startswith("/data/") for c in tree["children"])
    assert store.space()["total"] > 0


def test_build_index_usa_nombres_del_host(tmp_path, monkeypatch):
    from app import db
    from app.config import settings
    from app.crawler.build import build_index

    root = tmp_path / "root"
    root.mkdir()
    (root / "Share").mkdir()
    (root / "Share" / "a.txt").write_text("x")
    passwd = tmp_path / "passwd"
    uid = os.getuid()
    passwd.write_text(f"nasuser:x:{uid}:{uid}::/:/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(settings, "host_passwd", str(passwd))
    monkeypatch.setattr(settings, "host_group", str(tmp_path / "no-group"))

    db_path = str(tmp_path / "idx.db")
    build_index(db_path, str(root))
    conn = db.open_ro(db_path)
    try:
        row = conn.execute("SELECT owner FROM entries WHERE name='a.txt'").fetchone()
    finally:
        conn.close()
    assert row["owner"] == "nasuser"
