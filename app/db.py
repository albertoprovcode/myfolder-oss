"""Capa SQLite: apertura de conexiones y DDL. El esquema replica el índice
documentado en app/schema.py (dirs con totales rolled-up; ver spec §4)."""
from __future__ import annotations

import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    parent_path TEXT NOT NULL,
    type TEXT NOT NULL,
    size INTEGER NOT NULL DEFAULT 0,
    size_du INTEGER NOT NULL DEFAULT 0,
    extension TEXT,
    mtime INTEGER,
    atime INTEGER,
    ctime INTEGER,
    nlink INTEGER,
    ino TEXT,
    owner TEXT,
    "group" TEXT,
    file_count INTEGER NOT NULL DEFAULT 0,
    dir_count INTEGER NOT NULL DEFAULT 0,
    size_norecurs INTEGER NOT NULL DEFAULT 0,
    file_count_norecurs INTEGER NOT NULL DEFAULT 0,
    dir_count_norecurs INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_entries_type_parent ON entries(type, parent_path);
CREATE INDEX IF NOT EXISTS idx_entries_parent ON entries(parent_path);
CREATE INDEX IF NOT EXISTS idx_entries_type_size ON entries(type, size);
-- Índices CUBRIENTES (incluyen size): las agregaciones del dashboard
-- (age/extensions/types/owners/removable/cold) se resuelven solo con el
-- índice, sin saltar a la tabla por cada fila.
CREATE INDEX IF NOT EXISTS idx_entries_type_mtime ON entries(type, mtime, size);
CREATE INDEX IF NOT EXISTS idx_entries_type_atime ON entries(type, atime, size);
CREATE INDEX IF NOT EXISTS idx_entries_type_ext ON entries(type, extension, size);
CREATE INDEX IF NOT EXISTS idx_entries_type_owner ON entries(type, owner, size);
CREATE INDEX IF NOT EXISTS idx_entries_type_group ON entries(type, "group", size);

CREATE TABLE IF NOT EXISTS spaceinfo (
    path TEXT PRIMARY KEY,
    total INTEGER NOT NULL,
    used INTEGER NOT NULL,
    free INTEGER NOT NULL,
    available INTEGER NOT NULL,
    free_percent REAL NOT NULL,
    available_percent REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS indexinfo (
    id INTEGER PRIMARY KEY,
    start_at REAL NOT NULL,
    end_at REAL,
    entries INTEGER,
    errors INTEGER,
    version TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    name, content='entries', content_rowid='id', tokenize='trigram'
);

-- Agregaciones globales del Resumen precalculadas al final de cada crawl
-- (summary/types/extensions/age/removable), para que el dashboard responda
-- en milisegundos aunque la BD esté fría (ver spec de precálculo).
CREATE TABLE IF NOT EXISTS agg (key TEXT PRIMARY KEY, json TEXT NOT NULL);
"""

INSERT_ENTRY = """
INSERT INTO entries(name, parent_path, type, size, size_du, extension,
    mtime, atime, ctime, nlink, ino, owner, "group",
    file_count, dir_count, size_norecurs, file_count_norecurs, dir_count_norecurs)
VALUES (:name, :parent_path, :type, :size, :size_du, :extension,
    :mtime, :atime, :ctime, :nlink, :ino, :owner, :group,
    :file_count, :dir_count, :size_norecurs, :file_count_norecurs, :dir_count_norecurs)
"""


def open_rw(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def open_ro(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Afinado de lectura: mmap del fichero + caché de páginas generosa.
    conn.execute("PRAGMA mmap_size=268435456")
    conn.execute("PRAGMA cache_size=-64000")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()
