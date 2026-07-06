"""Capa de lectura SQL. Devuelve el MISMO JSON que devolvían los parsers de ES
(contrato de los 16 endpoints, spec §7). Una conexión ro por petición: barata y
se reabre sola tras el swap atómico del crawler."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from . import db
from .config import settings
from .formatting import human_date, human_datetime, human_size
from .schema import (
    ALL_CATEGORIZED_EXTS, ROOT_PATH, TYPE_DIR, TYPE_FILE,
    category_for_extension, extensions_for_category,
)

_AGE_LABELS = ["0-30d", "30-90d", "90d-1a", "1-2a", ">2a"]
# Filtro de subárbol como RANGO sobre parent_path (sargable → usa el índice
# idx_entries_type_parent), en vez de substr() que forzaba escaneo completo.
# El límite superior pfx+'￿' cubre pfx y todos sus descendientes.
_PREFIX = "parent_path >= :pfx AND parent_path < :pfx_hi"
_PREFIX_HI = "￿"


def _prefix_params(path: str) -> dict:
    return {"pfx": path, "pfx_hi": path + _PREFIX_HI}


def _date_to_epoch(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp())


# ------------------------------------------------ agregaciones globales
# Cuerpo de cómputo compartido entre el camino en vivo (Storage, caso
# global/sin path) y el precálculo al final del crawl (precompute_dashboard).
# Misma SQL en ambos sitios: cero divergencia entre el JSON cacheado y el
# que devolvería la consulta en vivo.

def agg_summary(conn) -> dict:
    row = conn.execute(
        "SELECT (SELECT COUNT(*) FROM entries WHERE type=:f) AS files,"
        " (SELECT COUNT(*) FROM entries WHERE type=:d) AS dirs,"
        " (SELECT COALESCE(SUM(size),0) FROM entries WHERE type=:f) AS total",
        {"f": TYPE_FILE, "d": TYPE_DIR}).fetchone()
    return {"files": row["files"], "dirs": row["dirs"],
            "total_size": row["total"], "total_size_h": human_size(row["total"])}


def agg_extensions_size(conn) -> dict:
    """Equivale a extensions(path=None, by='size') pero SIN límite: lista
    completa ordenada por size desc. El que llama recorta con [:limit]."""
    rows = conn.execute(
        "SELECT COALESCE(extension,'') AS ext, COALESCE(SUM(size),0) AS s,"
        " COUNT(*) AS c FROM entries WHERE type = :f"
        " GROUP BY COALESCE(extension,'') ORDER BY s DESC", {"f": TYPE_FILE}).fetchall()
    return {"items": [{"ext": r["ext"] or "(sin ext)", "size": r["s"],
                       "size_h": human_size(r["s"]), "count": r["c"]} for r in rows]}


def agg_types(conn) -> dict:
    """Equivale a types(path=None): rollup por categoría sobre el top-500
    de extensiones por size (mismo comportamiento que hoy)."""
    ext_items = agg_extensions_size(conn)["items"][:500]
    rollup: dict[str, dict] = {}
    for it in ext_items:
        cat = category_for_extension(it["ext"] if it["ext"] != "(sin ext)" else None)
        agg = rollup.setdefault(cat, {"category": cat, "size": 0, "count": 0})
        agg["size"] += it["size"]
        agg["count"] += it["count"]
    total = sum(a["size"] for a in rollup.values()) or 1
    items = sorted(rollup.values(), key=lambda a: a["size"], reverse=True)
    for a in items:
        a["size_h"] = human_size(a["size"])
        a["pct"] = round(a["size"] / total * 100, 1)
    return {"items": items}


def agg_age(conn, field: str, now: float) -> dict:
    col = "atime" if field == "atime" else "mtime"
    params: dict = {"f": TYPE_FILE,
                    "d30": now - 30 * 86400, "d90": now - 90 * 86400,
                    "d365": now - 365 * 86400, "d730": now - 730 * 86400}
    rows = conn.execute(
        f"SELECT CASE WHEN {col} >= :d30 THEN '0-30d'"
        f" WHEN {col} >= :d90 THEN '30-90d'"
        f" WHEN {col} >= :d365 THEN '90d-1a'"
        f" WHEN {col} >= :d730 THEN '1-2a' ELSE '>2a' END AS label,"
        f" COUNT(*) AS c, COALESCE(SUM(size),0) AS s"
        f" FROM entries WHERE type = :f AND {col} IS NOT NULL GROUP BY label",
        params).fetchall()
    found = {r["label"]: r for r in rows}
    return {"buckets": [{
        "label": l,
        "count": found[l]["c"] if l in found else 0,
        "size": found[l]["s"] if l in found else 0,
        "size_h": human_size(found[l]["s"] if l in found else 0),
    } for l in _AGE_LABELS]}


def agg_removable(conn, days: int, now: float) -> dict:
    cutoff = now - days * 86400
    row = conn.execute(
        "SELECT COUNT(*) AS c, COALESCE(SUM(size),0) AS s FROM entries"
        " WHERE type=:f AND mtime IS NOT NULL AND mtime < :cutoff",
        {"f": TYPE_FILE, "cutoff": cutoff}).fetchone()
    return {"count": row["c"], "size": row["s"], "size_h": human_size(row["s"])}


def precompute_dashboard(conn, now: float, cleanlist_days: int) -> None:
    """Calcula las agregaciones globales del Resumen sobre `conn` (la BD
    recién construida, aún sin swap) y las guarda en la tabla agg como JSON.
    Se llama al final del crawl. `now` = fin del crawl (age/removable
    relativos a él)."""
    import json

    blobs = {
        "summary": agg_summary(conn),
        "types": agg_types(conn),
        "extensions_size": agg_extensions_size(conn),
        "age_mtime": agg_age(conn, "mtime", now),
        "age_atime": agg_age(conn, "atime", now),
        "removable": {**agg_removable(conn, cleanlist_days, now), "days": cleanlist_days},
    }
    conn.executemany("INSERT OR REPLACE INTO agg(key, json) VALUES (?, ?)",
                     [(k, json.dumps(v)) for k, v in blobs.items()])


class Storage:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def available(self) -> bool:
        return os.path.exists(self.db_path)

    def _q(self, sql: str, params: dict | None = None) -> list:
        conn = db.open_ro(self.db_path)
        try:
            return conn.execute(sql, params or {}).fetchall()
        finally:
            conn.close()

    def _read_agg(self, key: str) -> dict | None:
        """Devuelve el dict cacheado o None (None si la tabla no existe
        -BD vieja- o la clave falta)."""
        import json
        import sqlite3

        conn = db.open_ro(self.db_path)
        try:
            row = conn.execute("SELECT json FROM agg WHERE key=:k", {"k": key}).fetchone()
            return json.loads(row["json"]) if row else None
        except sqlite3.OperationalError:
            return None  # BD antigua sin tabla agg
        finally:
            conn.close()

    # ------------------------------------------------ dashboard
    def summary(self) -> dict:
        if not self.available():
            return {"files": 0, "dirs": 0, "total_size": 0, "total_size_h": human_size(0)}
        cached = self._read_agg("summary")
        if cached is not None:
            return cached
        conn = db.open_ro(self.db_path)
        try:
            return agg_summary(conn)
        finally:
            conn.close()

    def indexed_at(self) -> str | None:
        if not self.available():
            return None
        row = self._q("SELECT MAX(end_at) AS v FROM indexinfo WHERE end_at IS NOT NULL")[0]
        return human_datetime(row["v"]) if row["v"] is not None else None

    def removable(self, days: int, now: float | None = None) -> dict:
        if not self.available():
            return {"count": 0, "size": 0, "size_h": human_size(0)}
        cached = self._read_agg("removable")
        if cached is not None and cached.get("days") == days:
            return {"count": cached["count"], "size": cached["size"],
                    "size_h": cached["size_h"]}
        conn = db.open_ro(self.db_path)
        try:
            return agg_removable(conn, days, now or time.time())
        finally:
            conn.close()

    def extensions(self, path: str | None, by: str, limit: int) -> dict:
        if not self.available():
            return {"items": []}
        if path is None and by == "size":
            cached = self._read_agg("extensions_size")
            items = cached["items"] if cached is not None else None
            if items is None:
                conn = db.open_ro(self.db_path)
                try:
                    items = agg_extensions_size(conn)["items"]
                finally:
                    conn.close()
            return {"items": items[:limit]}
        where = "type = :f"
        params: dict = {"f": TYPE_FILE, "limit": limit}
        if path:
            where += f" AND {_PREFIX}"
            params.update(_prefix_params(path))
        order = "s DESC" if by == "size" else "c DESC"
        rows = self._q(
            f"SELECT COALESCE(extension,'') AS ext, COALESCE(SUM(size),0) AS s,"
            f" COUNT(*) AS c FROM entries WHERE {where}"
            f" GROUP BY COALESCE(extension,'') ORDER BY {order} LIMIT :limit", params)
        return {"items": [{"ext": r["ext"] or "(sin ext)", "size": r["s"],
                           "size_h": human_size(r["s"]), "count": r["c"]} for r in rows]}

    def types(self, path: str | None) -> dict:
        if path is None:
            cached = self._read_agg("types")
            if cached is not None:
                return cached
            conn = db.open_ro(self.db_path)
            try:
                return agg_types(conn)
            finally:
                conn.close()
        ext_items = self.extensions(path, by="size", limit=500)["items"]
        rollup: dict[str, dict] = {}
        for it in ext_items:
            cat = category_for_extension(it["ext"] if it["ext"] != "(sin ext)" else None)
            agg = rollup.setdefault(cat, {"category": cat, "size": 0, "count": 0})
            agg["size"] += it["size"]
            agg["count"] += it["count"]
        total = sum(a["size"] for a in rollup.values()) or 1
        items = sorted(rollup.values(), key=lambda a: a["size"], reverse=True)
        for a in items:
            a["size_h"] = human_size(a["size"])
            a["pct"] = round(a["size"] / total * 100, 1)
        return {"items": items}

    def space(self) -> dict:
        empty = {"total": 0, "used": 0, "free": 0,
                 "total_h": human_size(0), "used_h": human_size(0),
                 "free_h": human_size(0), "free_percent": 0.0}
        if not self.available():
            return empty
        rows = self._q("SELECT * FROM spaceinfo WHERE path = :p", {"p": ROOT_PATH})
        if not rows:
            return empty
        r = rows[0]
        return {"total": r["total"], "used": r["used"], "free": r["free"],
                "total_h": human_size(r["total"]), "used_h": human_size(r["used"]),
                "free_h": human_size(r["free"]),
                "free_percent": round(float(r["free_percent"]), 1)}

    def age(self, path: str | None, field: str, now: float | None = None) -> dict:
        if not self.available():
            return {"buckets": [{"label": l, "count": 0, "size": 0,
                                 "size_h": human_size(0)} for l in _AGE_LABELS]}
        if path is None:
            cached = self._read_agg(f"age_{field}")
            if cached is not None:
                return cached
            conn = db.open_ro(self.db_path)
            try:
                return agg_age(conn, field, now or time.time())
            finally:
                conn.close()
        col = "atime" if field == "atime" else "mtime"
        ts = now or time.time()
        where = f"type = :f AND {col} IS NOT NULL"
        params: dict = {"f": TYPE_FILE,
                        "d30": ts - 30 * 86400, "d90": ts - 90 * 86400,
                        "d365": ts - 365 * 86400, "d730": ts - 730 * 86400}
        if path:
            where += f" AND {_PREFIX}"
            params.update(_prefix_params(path))
        rows = self._q(
            f"SELECT CASE WHEN {col} >= :d30 THEN '0-30d'"
            f" WHEN {col} >= :d90 THEN '30-90d'"
            f" WHEN {col} >= :d365 THEN '90d-1a'"
            f" WHEN {col} >= :d730 THEN '1-2a' ELSE '>2a' END AS label,"
            f" COUNT(*) AS c, COALESCE(SUM(size),0) AS s"
            f" FROM entries WHERE {where} GROUP BY label", params)
        found = {r["label"]: r for r in rows}
        return {"buckets": [{
            "label": l,
            "count": found[l]["c"] if l in found else 0,
            "size": found[l]["s"] if l in found else 0,
            "size_h": human_size(found[l]["s"] if l in found else 0),
        } for l in _AGE_LABELS]}

    # ------------------------------------------------ explorador
    _CHILD_SORT = {"name": "name", "size": "size", "mtime": "mtime",
                   "atime": "atime", "files": "file_count", "dirs": "dir_count"}
    _COLD_SORT = {"size": "size", "mtime": "mtime", "atime": "atime", "name": "name"}

    def tree(self, path: str | None) -> dict:
        if not self.available():
            return {"path": path, "children": [], "current": None}
        base = (path or ROOT_PATH).rstrip("/")
        rows = self._q(
            "SELECT name, size, file_count, dir_count FROM entries"
            " WHERE type=:d AND parent_path=:p ORDER BY size DESC LIMIT 2000",
            {"d": TYPE_DIR, "p": base})
        children = [{"name": r["name"], "path": base + "/" + r["name"],
                     "size": r["size"], "size_h": human_size(r["size"]),
                     "items": r["file_count"] + r["dir_count"]} for r in rows]
        current = None
        if path is not None and path != ROOT_PATH:
            parent, _, name = path.rpartition("/")
            cur = self._q(
                "SELECT size, file_count, dir_count, mtime FROM entries"
                " WHERE type=:d AND parent_path=:p AND name=:n LIMIT 1",
                {"d": TYPE_DIR, "p": parent, "n": name})
            if cur:
                c = cur[0]
                current = {"size": c["size"], "size_h": human_size(c["size"]),
                           "items": c["file_count"] + c["dir_count"],
                           "files": c["file_count"], "dirs": c["dir_count"],
                           "mtime": human_date(c["mtime"])}
        return {"path": path, "children": children, "current": current}

    def children(self, path: str, limit: int, offset: int,
                 sort: str, order: str) -> dict:
        if not self.available():
            return {"items": [], "total": 0}
        col = self._CHILD_SORT.get(sort, "size")
        direction = order if order in ("asc", "desc") else "desc"
        total = self._q("SELECT COUNT(*) AS c FROM entries WHERE parent_path=:p",
                        {"p": path})[0]["c"]
        rows = self._q(
            f'SELECT name, parent_path, type, size, mtime, atime, owner, "group",'
            f" file_count, dir_count FROM entries WHERE parent_path=:p"
            f" ORDER BY {col} {direction} LIMIT :limit OFFSET :offset",
            {"p": path, "limit": limit, "offset": offset})
        items = [{"name": r["name"],
                  "path": r["parent_path"].rstrip("/") + "/" + r["name"],
                  "size": r["size"], "size_h": human_size(r["size"]),
                  "mtime": human_date(r["mtime"]), "atime": human_date(r["atime"]),
                  "files": r["file_count"], "dirs": r["dir_count"],
                  "owner": str(r["owner"] or ""), "group": str(r["group"] or ""),
                  "type": r["type"]} for r in rows]
        return {"items": items, "total": total}

    def top_dirs(self, path: str | None, limit: int) -> dict:
        if not self.available():
            return {"items": []}
        where = "type = :d"
        params: dict = {"d": TYPE_DIR, "limit": limit}
        if path:
            where += f" AND {_PREFIX}"
            params.update(_prefix_params(path))
        rows = self._q(
            f"SELECT name, parent_path, size, file_count FROM entries"
            f" WHERE {where} ORDER BY size DESC LIMIT :limit", params)
        return {"items": [{
            "path": r["parent_path"].rstrip("/") + "/" + r["name"],
            "name": r["name"], "size": r["size"], "size_h": human_size(r["size"]),
            "count": r["file_count"]} for r in rows]}

    def top_files(self, path: str | None, limit: int, offset: int) -> dict:
        if not self.available():
            return {"items": [], "total": 0}
        where = "type = :f"
        params: dict = {"f": TYPE_FILE}
        if path:
            where += f" AND {_PREFIX}"
            params.update(_prefix_params(path))
        total = self._q(f"SELECT COUNT(*) AS c FROM entries WHERE {where}",
                        params)[0]["c"]
        rows = self._q(
            f"SELECT name, parent_path, size, mtime, atime FROM entries"
            f" WHERE {where} ORDER BY size DESC LIMIT :limit OFFSET :offset",
            {**params, "limit": limit, "offset": offset})
        items = [{"name": r["name"], "path": r["parent_path"], "size": r["size"],
                  "size_h": human_size(r["size"]), "mtime": human_date(r["mtime"]),
                  "atime": human_date(r["atime"])} for r in rows]
        return {"items": items, "total": total}

    def cold(self, field: str, days: int, size_min: int, limit: int, offset: int,
             sort: str, order: str, now: float | None = None,
             path: str | None = None) -> dict:
        if not self.available():
            return {"items": [], "total": 0, "total_size": 0,
                    "total_size_h": human_size(0)}
        col = "atime" if field == "atime" else "mtime"
        cutoff = (now or time.time()) - days * 86400
        where = f"type = :f AND {col} IS NOT NULL AND {col} < :cutoff"
        params: dict = {"f": TYPE_FILE, "cutoff": cutoff}
        if size_min and size_min > 0:
            where += " AND size >= :size_min"
            params["size_min"] = size_min
        if path:
            where += f" AND {_PREFIX}"
            params.update(_prefix_params(path))
        agg = self._q(f"SELECT COUNT(*) AS c, COALESCE(SUM(size),0) AS s"
                      f" FROM entries WHERE {where}", params)[0]
        sort_col = self._COLD_SORT.get(sort, "size")
        direction = order if order in ("asc", "desc") else "desc"
        rows = self._q(
            f"SELECT name, parent_path, size, mtime, atime FROM entries"
            f" WHERE {where} ORDER BY {sort_col} {direction}"
            f" LIMIT :limit OFFSET :offset",
            {**params, "limit": limit, "offset": offset})
        items = [{"name": r["name"], "path": r["parent_path"], "size": r["size"],
                  "size_h": human_size(r["size"]), "mtime": human_date(r["mtime"]),
                  "atime": human_date(r["atime"])} for r in rows]
        return {"items": items, "total": agg["c"], "total_size": agg["s"],
                "total_size_h": human_size(agg["s"])}

    def owners(self, field: str, limit: int) -> dict:
        if not self.available():
            return {"items": [], "total_size": 0,
                    "total_size_h": human_size(0), "total_files": 0}
        col = '"group"' if field == "group" else "owner"
        rows = self._q(
            f"SELECT {col} AS k, COUNT(*) AS c, COALESCE(SUM(size),0) AS s"
            f" FROM entries WHERE type=:f GROUP BY {col}"
            f" ORDER BY s DESC LIMIT :limit", {"f": TYPE_FILE, "limit": limit})
        items, total_size, total_files = [], 0, 0
        for r in rows:
            total_size += r["s"]
            total_files += r["c"]
            items.append({"name": str(r["k"] or ""), "files": r["c"],
                          "size": r["s"], "size_h": human_size(r["s"])})
        return {"items": items, "total_size": total_size,
                "total_size_h": human_size(total_size), "total_files": total_files}

    # ------------------------------------------------ búsqueda
    _SEARCH_SORT = {"name": "name", "size": "size", "mtime": "mtime", "atime": "atime"}

    def search(self, filters: dict, limit: int, offset: int,
               group_limit: int | None = None, group_offset: int = 0) -> dict:
        if not self.available():
            return {"items": [], "total": 0}
        where = ["type = :type"]
        params: dict = {"type": filters.get("type") or TYPE_FILE}
        name = filters.get("name")
        if name:
            pat = "%" + name + "%"
            if len(name) >= 3:
                where.append("id IN (SELECT rowid FROM entries_fts WHERE name LIKE :pat)")
            else:
                where.append("name LIKE :pat")
            params["pat"] = pat
        if filters.get("ext"):
            where.append("extension = :ext")
            params["ext"] = filters["ext"].lower().lstrip(".")
        if filters.get("owner"):
            where.append("owner = :owner")
            params["owner"] = filters["owner"]
        if filters.get("group"):
            where.append('"group" = :grp')
            params["grp"] = filters["group"]
        if filters.get("size_min") is not None:
            where.append("size >= :size_min")
            params["size_min"] = filters["size_min"]
        if filters.get("size_max") is not None:
            where.append("size <= :size_max")
            params["size_max"] = filters["size_max"]
        for fld in ("mtime", "atime"):
            if filters.get(f"{fld}_from"):
                where.append(f"{fld} >= :{fld}_from")
                params[f"{fld}_from"] = _date_to_epoch(filters[f"{fld}_from"])
            if filters.get(f"{fld}_to"):
                where.append(f"{fld} < :{fld}_to")
                params[f"{fld}_to"] = _date_to_epoch(filters[f"{fld}_to"])
        if filters.get("path"):
            where.append(_PREFIX)
            params.update(_prefix_params(filters["path"]))
        category = filters.get("category")
        if category:
            cat_exts = extensions_for_category(category)
            if cat_exts:
                cols = []
                for idx, e in enumerate(sorted(cat_exts)):
                    key = f"cat{idx}"
                    cols.append(f":{key}")
                    params[key] = e
                where.append(f"lower(extension) IN ({', '.join(cols)})")
            elif category == "other":
                cols = []
                for idx, e in enumerate(sorted(ALL_CATEGORIZED_EXTS)):
                    key = f"allcat{idx}"
                    cols.append(f":{key}")
                    params[key] = e
                where.append(
                    f"(extension IS NULL OR lower(extension) NOT IN ({', '.join(cols)}))"
                )
            # categoría desconocida: se ignora, sin cláusula
        if filters.get("dupes_only"):
            # Solo archivos cuyo tamaño EXACTO comparte al menos otro archivo
            # (candidatos a duplicado, mismo criterio que /api/dupes). "Mismo
            # tamaño ≠ idéntico", pero descarta los tamaños únicos.
            where.append(
                "size IN (SELECT size FROM entries WHERE type=:type"
                " GROUP BY size HAVING COUNT(*) >= 2)"
            )
        cond = " AND ".join(where)
        col = self._SEARCH_SORT.get(filters.get("sort"), "size")
        direction = filters.get("order") if filters.get("order") in ("asc", "desc") else "desc"
        total = self._q(f"SELECT COUNT(*) AS c FROM entries WHERE {cond}",
                        params)[0]["c"]

        def _items(rows) -> list[dict]:
            return [{"name": r["name"], "path": r["parent_path"], "size": r["size"],
                     "size_h": human_size(r["size"]), "mtime": human_date(r["mtime"]),
                     "atime": human_date(r["atime"]), "owner": r["owner"],
                     "group": r["group"], "type": r["type"]} for r in rows]

        if filters.get("dupes_only") and group_limit is not None:
            # Paginación por GRUPOS de tamaño: la página trae TODAS las filas de
            # sus grupos, así un grupo de posibles duplicados nunca queda partido
            # entre páginas. Ordenación fija por tamaño (agrupar por nombre o
            # fecha desperdigaría los grupos).
            total_groups = self._q(
                f"SELECT COUNT(DISTINCT size) AS c FROM entries WHERE {cond}",
                params)[0]["c"]
            sizes = self._q(
                f"SELECT size FROM entries WHERE {cond} GROUP BY size"
                f" ORDER BY size {direction} LIMIT :glim OFFSET :goff",
                {**params, "glim": group_limit, "goff": group_offset})
            if not sizes:
                return {"items": [], "total": total, "total_groups": total_groups}
            marks = ", ".join(f":gs{i}" for i in range(len(sizes)))
            rows = self._q(
                f'SELECT name, parent_path, type, size, mtime, atime, owner, "group"'
                f" FROM entries WHERE {cond} AND size IN ({marks})"
                f" ORDER BY size {direction}, name ASC",
                {**params, **{f"gs{i}": r["size"] for i, r in enumerate(sizes)}})
            return {"items": _items(rows), "total": total,
                    "total_groups": total_groups}

        rows = self._q(
            f'SELECT name, parent_path, type, size, mtime, atime, owner, "group"'
            f" FROM entries WHERE {cond} ORDER BY {col} {direction}"
            f" LIMIT :limit OFFSET :offset",
            {**params, "limit": limit, "offset": offset})
        return {"items": _items(rows), "total": total}

    def dupes(self, path: str | None, min_size: int, limit: int) -> dict:
        if not self.available():
            return {"groups": []}
        where = "type = :f AND size >= :min_size"
        params: dict = {"f": TYPE_FILE, "min_size": min_size, "limit": limit}
        if path:
            where += f" AND {_PREFIX}"
            params.update(_prefix_params(path))
        rows = self._q(
            f"SELECT size, COUNT(*) AS c FROM entries WHERE {where}"
            f" GROUP BY size HAVING c >= 2 ORDER BY c DESC LIMIT :limit", params)
        return {"groups": [{"size": r["size"], "size_h": human_size(r["size"]),
                            "count": r["c"]} for r in rows]}


def get_store() -> Storage:
    """Dependencia FastAPI. Se sobreescribe en tests."""
    return Storage(settings.db_path)
