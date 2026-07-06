"""Utilidades para seedear una BD SQLite de prueba (sustituye al fake_es del MVP)."""
from __future__ import annotations

from app import db
from app.storage import Storage

DEFAULT_EPOCH = 1_700_000_000  # 2023-11-14 UTC


def make_store(tmp_path):
    path = str(tmp_path / "test.db")
    conn = db.open_rw(path)
    db.create_schema(conn)
    return Storage(path), conn


def add_entry(conn, name, parent_path, type="file", size=0, **kw):
    row = {
        "name": name, "parent_path": parent_path, "type": type, "size": size,
        "size_du": kw.get("size_du", size), "extension": kw.get("extension"),
        "mtime": kw.get("mtime", DEFAULT_EPOCH), "atime": kw.get("atime", DEFAULT_EPOCH),
        "ctime": kw.get("ctime", DEFAULT_EPOCH), "nlink": kw.get("nlink", 1),
        "ino": kw.get("ino", "1"), "owner": kw.get("owner", "1000"),
        "group": kw.get("group", "users"),
        "file_count": kw.get("file_count", 0), "dir_count": kw.get("dir_count", 0),
        "size_norecurs": kw.get("size_norecurs", 0),
        "file_count_norecurs": kw.get("file_count_norecurs", 0),
        "dir_count_norecurs": kw.get("dir_count_norecurs", 0),
    }
    cur = conn.execute(db.INSERT_ENTRY, row)
    conn.execute("INSERT INTO entries_fts(rowid, name) VALUES (?, ?)",
                 (cur.lastrowid, name))
    conn.commit()


def add_space(conn, path="/data", total=1000, used=600, free=400):
    conn.execute(
        "INSERT INTO spaceinfo VALUES (?,?,?,?,?,?,?)",
        (path, total, used, free, free, round(free / total * 100, 1),
         round(free / total * 100, 1)))
    conn.commit()


def add_indexinfo(conn, start_at, end_at=None, entries=None):
    conn.execute("INSERT INTO indexinfo(start_at, end_at, entries) VALUES (?,?,?)",
                 (start_at, end_at, entries))
    conn.commit()
