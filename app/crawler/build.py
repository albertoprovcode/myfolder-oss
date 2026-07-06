from __future__ import annotations

import os
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .. import db, storage
from ..config import settings
from ..schema import ROOT_PATH
from .scan import DirTotals, WalkStats, dir_row, preseed_id_caches, walk_dir
from .state import CrawlState

BATCH = 5000
VERSION = "myfolder-fase2"


class _BuildAborted(Exception):
    """Señal interna para que un share corte su recorrido cuando el escritor falló."""


def _spaceinfo_row(fs_path: str, logical_path: str) -> dict:
    sv = os.statvfs(fs_path)
    total = sv.f_blocks * sv.f_frsize
    free = sv.f_bfree * sv.f_frsize
    available = sv.f_bavail * sv.f_frsize
    return {
        "path": logical_path, "total": total, "used": total - free, "free": free,
        "available": available,
        "free_percent": round(free / total * 100, 1) if total else 0.0,
        "available_percent": round(available / total * 100, 1) if total else 0.0,
    }


def build_index(db_path: str, data_root: str,
                state: CrawlState | None = None, now_fn=time.time) -> dict:
    if not os.path.isdir(data_root):
        raise FileNotFoundError(data_root)
    building = db_path + ".building"
    if os.path.exists(building):
        os.remove(building)
    # Nombres reales del NAS para owner/group (spec 2026-07-04); en dev los
    # ficheros del host no existen y la resolución queda como estaba.
    preseed_id_caches(settings.host_passwd, settings.host_group)
    started = now_fn()
    conn = db.open_rw(building)
    try:
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        db.create_schema(conn)
        conn.execute("INSERT INTO indexinfo(start_at, version) VALUES (?, ?)",
                     (started, VERSION))

        shares = sorted((e for e in os.scandir(data_root)
                         if e.is_dir(follow_symlinks=False)), key=lambda e: e.name)
        stats = WalkStats()
        q: queue.Queue = queue.Queue(maxsize=50)
        stop = threading.Event()

        def run_share(entry: os.DirEntry) -> DirTotals:
            batch: list[dict] = []

            def emit(row: dict) -> None:
                if stop.is_set():
                    raise _BuildAborted()
                batch.append(row)
                if len(batch) >= BATCH:
                    q.put(list(batch))
                    batch.clear()

            try:
                return walk_dir(entry.path, entry.name, ROOT_PATH, emit, stats)
            except _BuildAborted:
                return DirTotals()
            finally:
                if batch:
                    q.put(list(batch))
                q.put(None)  # centinela: este share terminó

        total = 0
        with ThreadPoolExecutor(max_workers=min(8, len(shares) or 1)) as pool:
            futures = [pool.submit(run_share, s) for s in shares]
            done = 0
            try:
                while done < len(shares):
                    rows = q.get()
                    if rows is None:
                        done += 1
                        continue
                    conn.executemany(db.INSERT_ENTRY, rows)
                    total += len(rows)
                    if state:
                        state.entries = total
            except BaseException:
                stop.set()
                while done < len(shares):  # drena hasta ver todos los centinelas: desbloquea productores
                    if q.get() is None:
                        done += 1
                raise
            share_totals = [f.result() for f in futures]

        root = DirTotals()
        for t in share_totals:
            root.size += t.size
            root.size_du += t.size_du
            root.files += t.files
            root.dirs += 1 + t.dirs
        root_name = os.path.basename(ROOT_PATH.rstrip("/"))
        # La fila raíz es la cima del árbol indexado: su parent_path es siempre ""
        # sin importar dónde esté montado data_root en el filesystem real (nadie
        # la consulta por parent_path, así que no hace falta os.path.dirname aquí).
        conn.execute(db.INSERT_ENTRY, dir_row(
            root_name, "", os.stat(data_root), root, DirTotals()))
        total += 1
        if state:
            state.entries = total

        # In the container /data is an overlay directory, not a mount (only the
        # /data/<Share> paths are bind mounts of the real host folders): measuring
        # data_root on the root row would report the Docker system disk, not the
        # data volume. So, if there are shares, the root is measured with the
        # filesystem of the first one; only if there are no shares do we fall back
        # to data_root.
        root_fs_path = shares[0].path if shares else data_root
        space_targets = [(root_fs_path, ROOT_PATH)] + [
            (s.path, f"{ROOT_PATH}/{s.name}") for s in shares]
        for fs_path, logical_path in space_targets:
            conn.execute(
                "INSERT OR REPLACE INTO spaceinfo(path, total, used, free, available,"
                " free_percent, available_percent) VALUES (:path, :total, :used, :free,"
                " :available, :free_percent, :available_percent)",
                _spaceinfo_row(fs_path, logical_path))

        conn.execute("INSERT INTO entries_fts(rowid, name) SELECT id, name FROM entries")
        ended = now_fn()
        conn.execute("UPDATE indexinfo SET end_at=?, entries=?, errors=?",
                     (ended, total, stats.errors))
        storage.precompute_dashboard(conn, ended, settings.cleanlist_days)
        conn.commit()
        conn.execute("ANALYZE")
        conn.close()
        os.replace(building, db_path)
        return {"entries": total, "errors": stats.errors,
                "seconds": round(now_fn() - started, 1)}
    except BaseException:
        conn.close()
        if os.path.exists(building):
            os.remove(building)
        raise
