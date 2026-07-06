"""Verificación de duplicados: caché persistente de hashes y worker de hasheo.

La caché vive en un SQLite PROPIO (no en la BD del índice: esa se reemplaza
entera con os.replace en cada crawl y los hashes deben sobrevivir).
Clave = ruta lógica (/data/...); validez = size+mtime del fichero real.
"""
from __future__ import annotations

import hashlib
import os
import queue
import sqlite3
import threading
import time

from .schema import ROOT_PATH

CHUNK = 1024 * 1024  # bloques de lectura de 1 MiB

_SCHEMA = """
CREATE TABLE IF NOT EXISTS hashes (
    path TEXT PRIMARY KEY,
    size INTEGER NOT NULL,
    mtime INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    hashed_at REAL NOT NULL
);
"""


class HashCache:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        conn = self._open()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def get_valid(self, logical: str, real: str) -> str | None:
        """sha256 cacheado si el fichero real no cambió (size+mtime); si no, None."""
        conn = self._open()
        try:
            row = conn.execute(
                "SELECT size, mtime, sha256 FROM hashes WHERE path=?",
                (logical,)).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        try:
            st = os.stat(real)
        except OSError:
            return None
        if st.st_size != row["size"] or int(st.st_mtime) != row["mtime"]:
            return None
        return row["sha256"]

    def put(self, logical: str, size: int, mtime: int, sha256: str) -> None:
        conn = self._open()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO hashes(path, size, mtime, sha256, hashed_at)"
                " VALUES (?,?,?,?,?)",
                (logical, size, mtime, sha256, time.time()))
            conn.commit()
        finally:
            conn.close()


class HashWorker:
    """Hashea ficheros de UNO en uno (el disco del NAS es el recurso escaso;
    Syncthing ya compite por I/O). El hilo muere en reposo y se recrea al encolar."""

    def __init__(self, cache: HashCache, data_root: str) -> None:
        self.cache = cache
        self.data_root = os.path.realpath(data_root)
        self._q: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._pending: set[str] = set()  # rutas lógicas encoladas o en curso
        self._errors: dict[str, str] = {}
        self._thread: threading.Thread | None = None

    # -------------------------------------------------- rutas
    def resolve(self, logical: str) -> str | None:
        """Ruta real si `logical` es un fichero regular bajo data_root; None si no.
        Rechaza traversal y symlinks que escapen (realpath + prefijo)."""
        if not logical.startswith(ROOT_PATH + "/"):
            return None
        rel = logical[len(ROOT_PATH):].lstrip("/")
        real = os.path.realpath(os.path.join(self.data_root, rel))
        if not real.startswith(self.data_root + os.sep):
            return None
        if not os.path.isfile(real):
            return None
        return real

    # -------------------------------------------------- cola
    def enqueue(self, logical: str, real: str) -> None:
        with self._lock:
            if logical in self._pending:
                return
            self._pending.add(logical)
            self._errors.pop(logical, None)
        self._q.put((logical, real))
        # Asegurar hilo vivo DESPUÉS del put: si el hilo estaba muriendo,
        # su salida (bajo lock, re-comprobando la cola) y este arranque no
        # pueden perder el item.
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, daemon=True)
                self._thread.start()

    def _run(self) -> None:
        while True:
            try:
                logical, real = self._q.get(timeout=5)
            except queue.Empty:
                # Salir SOLO si la cola sigue vacía bajo el lock: cierra la
                # carrera con un enqueue simultáneo (o él ve el hilo muerto y
                # arranca otro, o este hilo ve el item y sigue).
                with self._lock:
                    if self._q.empty():
                        self._thread = None
                        return
                continue
            try:
                st = os.stat(real)  # stat ANTES de leer: si cambia durante la
                # lectura, el mtime nuevo invalidará la entrada en la caché
                h = hashlib.sha256()
                with open(real, "rb") as f:
                    while chunk := f.read(CHUNK):
                        h.update(chunk)
                self.cache.put(logical, st.st_size, int(st.st_mtime), h.hexdigest())
            except (OSError, sqlite3.Error) as e:
                with self._lock:
                    self._errors[logical] = str(e)
            finally:
                with self._lock:
                    self._pending.discard(logical)

    # -------------------------------------------------- estado
    def status(self, logical: str, real: str) -> dict:
        if real is None:
            return {"status": "error", "sha256": None, "error": "ruta no disponible"}
        sha = self.cache.get_valid(logical, real)
        if sha:
            return {"status": "done", "sha256": sha, "error": None}
        with self._lock:
            if logical in self._pending:
                return {"status": "pending", "sha256": None, "error": None}
            err = self._errors.get(logical)
        if err:
            return {"status": "error", "sha256": None, "error": err}
        return {"status": "unknown", "sha256": None, "error": None}

    def wait_idle(self, timeout: float = 5.0) -> None:
        """Solo para tests: espera a que no quede nada pendiente."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if not self._pending:
                    return
            time.sleep(0.02)
