import sqlite3

from app import db


def test_create_schema_creates_tables(tmp_path):
    conn = db.open_rw(str(tmp_path / "x.db"))
    db.create_schema(conn)
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','index')")}
    assert {"entries", "spaceinfo", "indexinfo", "entries_fts"} <= names
    assert "idx_entries_type_parent" in names


def test_entries_accepts_row_and_group_column(tmp_path):
    conn = db.open_rw(str(tmp_path / "x.db"))
    db.create_schema(conn)
    conn.execute(db.INSERT_ENTRY, {
        "name": "a.txt", "parent_path": "/data/Music", "type": "file",
        "size": 10, "size_du": 10, "extension": "txt",
        "mtime": 1700000000, "atime": 1700000000, "ctime": 1700000000,
        "nlink": 1, "ino": "1", "owner": "1000", "group": "users",
        "file_count": 0, "dir_count": 0, "size_norecurs": 0,
        "file_count_norecurs": 0, "dir_count_norecurs": 0,
    })
    row = conn.execute('SELECT name, "group" FROM entries').fetchone()
    assert (row["name"], row["group"]) == ("a.txt", "users")


def test_fts_trigram_substring(tmp_path):
    conn = db.open_rw(str(tmp_path / "x.db"))
    db.create_schema(conn)
    conn.execute("INSERT INTO entries(id, name, parent_path, type) "
                 "VALUES (1, 'IMG_20240612.jpg', '/data/Photo', 'file')")
    conn.execute("INSERT INTO entries_fts(rowid, name) VALUES (1, 'IMG_20240612.jpg')")
    hit = conn.execute(
        "SELECT rowid FROM entries_fts WHERE name LIKE '%40612%'").fetchone()
    assert hit[0] == 1


def test_open_ro_rejects_writes(tmp_path):
    p = str(tmp_path / "x.db")
    db.create_schema(db.open_rw(p))
    ro = db.open_ro(p)
    try:
        ro.execute("INSERT INTO indexinfo(start_at) VALUES (1)")
        assert False, "escritura permitida en modo ro"
    except sqlite3.OperationalError:
        pass
