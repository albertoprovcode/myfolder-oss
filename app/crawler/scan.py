"""Recorrido post-orden de un árbol de ficheros → filas del esquema entries.

Post-orden porque los totales rolled-up de una carpeta (spec §4/§5) solo se
conocen al terminar su subárbol. La recursión sigue la profundidad del árbol
(en el NAS <50 niveles; el límite de Python es 1000)."""
from __future__ import annotations

import grp as grp_mod
import os
import pwd
from dataclasses import dataclass
from typing import Callable

from ..schema import TYPE_DIR, TYPE_FILE


@dataclass
class WalkStats:
    errors: int = 0


@dataclass
class DirTotals:
    size: int = 0
    size_du: int = 0
    files: int = 0
    dirs: int = 0


_uid_cache: dict[int, str] = {}
_gid_cache: dict[int, str] = {}


def load_ids(path: str) -> dict[int, str]:
    """Parsea formato passwd/group (`nombre:x:ID:...`) → {ID: nombre}.
    Fichero inexistente/ilegible → {}. Líneas malformadas o comentarios se
    ignoran. Sirve para los /etc/passwd|group del HOST montados ro."""
    ids: dict[int, str] = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.strip().split(":")
                if len(parts) < 3 or not parts[0] or parts[0].startswith("#"):
                    continue
                try:
                    ids[int(parts[2])] = parts[0]
                except ValueError:
                    continue
    except OSError:
        return {}
    return ids


def preseed_id_caches(passwd_path: str, group_path: str) -> None:
    """Recarga los caches uid/gid con los usuarios del NAS. Se llama al inicio
    de CADA crawl (no una vez por proceso) para recoger usuarios nuevos.
    Prioridad resultante: host → pwd/grp del contenedor → str(id)."""
    _uid_cache.clear()
    _gid_cache.clear()
    _uid_cache.update(load_ids(passwd_path))
    _gid_cache.update(load_ids(group_path))


def _owner(uid: int) -> str:
    if uid not in _uid_cache:
        try:
            _uid_cache[uid] = pwd.getpwuid(uid).pw_name
        except KeyError:
            _uid_cache[uid] = str(uid)
    return _uid_cache[uid]


def _group(gid: int) -> str:
    if gid not in _gid_cache:
        try:
            _gid_cache[gid] = grp_mod.getgrgid(gid).gr_name
        except KeyError:
            _gid_cache[gid] = str(gid)
    return _gid_cache[gid]


def _extension(name: str) -> str | None:
    stem = name.strip(".")
    if "." not in stem:
        return None
    return stem.rsplit(".", 1)[-1].lower()


def _stat_fields(st: os.stat_result) -> dict:
    return {
        "size_du": st.st_blocks * 512,
        "mtime": int(st.st_mtime),
        "atime": int(st.st_atime),
        "ctime": int(st.st_ctime),
        "nlink": st.st_nlink,
        "ino": str(st.st_ino),
        "owner": _owner(st.st_uid),
        "group": _group(st.st_gid),
    }


def file_row(name: str, parent_index_path: str, st: os.stat_result) -> dict:
    return {
        "name": name, "parent_path": parent_index_path, "type": TYPE_FILE,
        "size": st.st_size, "extension": _extension(name),
        "file_count": 0, "dir_count": 0, "size_norecurs": 0,
        "file_count_norecurs": 0, "dir_count_norecurs": 0,
        **_stat_fields(st),
    }


def dir_row(name: str, parent_index_path: str, st: os.stat_result,
            totals: DirTotals, direct: DirTotals) -> dict:
    row = {
        "name": name, "parent_path": parent_index_path, "type": TYPE_DIR,
        "size": totals.size, "extension": None,
        "file_count": totals.files, "dir_count": totals.dirs,
        "size_norecurs": direct.size,
        "file_count_norecurs": direct.files, "dir_count_norecurs": direct.dirs,
        **_stat_fields(st),
    }
    row["size_du"] = totals.size_du
    return row


def walk_dir(fs_path: str, name: str, parent_index_path: str,
             emit: Callable[[dict], None], stats: WalkStats) -> DirTotals:
    my_index_path = parent_index_path + "/" + name
    totals = DirTotals()
    direct = DirTotals()
    try:
        with os.scandir(fs_path) as it:
            children = list(it)
    except OSError:
        stats.errors += 1
        children = []
    for entry in children:
        try:
            if entry.is_symlink():
                continue
            if entry.is_dir(follow_symlinks=False):
                sub = walk_dir(entry.path, entry.name, my_index_path, emit, stats)
                totals.size += sub.size
                totals.size_du += sub.size_du
                totals.files += sub.files
                totals.dirs += 1 + sub.dirs
                direct.dirs += 1
            else:
                st = entry.stat(follow_symlinks=False)
                emit(file_row(entry.name, my_index_path, st))
                totals.size += st.st_size
                totals.size_du += st.st_blocks * 512
                totals.files += 1
                direct.size += st.st_size
                direct.files += 1
        except OSError:
            stats.errors += 1
    try:
        emit(dir_row(name, parent_index_path, os.stat(fs_path), totals, direct))
    except OSError:
        stats.errors += 1
    return totals
