"""Tests de la caché de hashes y (Task 2) del worker."""
import hashlib
import os

from app.hasher import HashCache, HashWorker


def _touch(path, content=b"hola"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return str(path)


def test_cache_miss_devuelve_none(tmp_path):
    cache = HashCache(str(tmp_path / "hashes.db"))
    real = _touch(tmp_path / "root" / "a.bin")
    assert cache.get_valid("/data/a.bin", real) is None


def test_cache_put_y_get_valid(tmp_path):
    cache = HashCache(str(tmp_path / "hashes.db"))
    real = _touch(tmp_path / "root" / "a.bin")
    st = os.stat(real)
    cache.put("/data/a.bin", st.st_size, int(st.st_mtime), "abc123")
    assert cache.get_valid("/data/a.bin", real) == "abc123"


def test_cache_invalida_si_cambia_el_fichero(tmp_path):
    """Si size o mtime del fichero real difieren de lo cacheado → None."""
    cache = HashCache(str(tmp_path / "hashes.db"))
    real = _touch(tmp_path / "root" / "a.bin")
    st = os.stat(real)
    cache.put("/data/a.bin", st.st_size, int(st.st_mtime), "abc123")
    # cambia el contenido (size distinto)
    _touch(tmp_path / "root" / "a.bin", b"contenido mas largo")
    assert cache.get_valid("/data/a.bin", real) is None
    # mtime distinto con mismo size
    st2 = os.stat(real)
    cache.put("/data/a.bin", st2.st_size, int(st2.st_mtime), "def456")
    os.utime(real, (st2.st_atime, st2.st_mtime + 100))
    assert cache.get_valid("/data/a.bin", real) is None


def test_cache_none_si_el_fichero_desaparece(tmp_path):
    cache = HashCache(str(tmp_path / "hashes.db"))
    real = _touch(tmp_path / "root" / "a.bin")
    st = os.stat(real)
    cache.put("/data/a.bin", st.st_size, int(st.st_mtime), "abc123")
    os.remove(real)
    assert cache.get_valid("/data/a.bin", real) is None


def test_cache_crea_directorio_padre(tmp_path):
    """El directorio del db se crea si no existe (primer arranque en prod)."""
    cache = HashCache(str(tmp_path / "sub" / "dir" / "hashes.db"))
    assert os.path.exists(str(tmp_path / "sub" / "dir" / "hashes.db"))


def _worker(tmp_path):
    cache = HashCache(str(tmp_path / "hashes.db"))
    root = tmp_path / "root"
    root.mkdir(parents=True, exist_ok=True)
    return HashWorker(cache, str(root)), root


def test_resolve_mapea_logica_a_real_y_rechaza_escapes(tmp_path):
    w, root = _worker(tmp_path)
    real = _touch(root / "Video" / "a.mkv")
    assert w.resolve("/data/Video/a.mkv") == os.path.realpath(real)
    assert w.resolve("/data/../etc/passwd") is None      # traversal
    assert w.resolve("/otro/a.mkv") is None              # fuera de /data
    assert w.resolve("/data/no-existe.bin") is None      # no existe
    assert w.resolve("/data/Video") is None              # directorio, no fichero


def test_resolve_rechaza_symlink_que_escapa(tmp_path):
    w, root = _worker(tmp_path)
    fuera = _touch(tmp_path / "fuera" / "secreto.txt")
    (root / "link.txt").symlink_to(fuera)
    assert w.resolve("/data/link.txt") is None


def test_worker_hashea_y_cachea(tmp_path):
    w, root = _worker(tmp_path)
    real = _touch(root / "a.bin", b"contenido de prueba")
    esperado = hashlib.sha256(b"contenido de prueba").hexdigest()
    w.enqueue("/data/a.bin", w.resolve("/data/a.bin"))
    w.wait_idle()
    s = w.status("/data/a.bin", real)
    assert s["status"] == "done" and s["sha256"] == esperado


def test_worker_dedupe_y_status_pendiente_o_unknown(tmp_path):
    w, root = _worker(tmp_path)
    real = _touch(root / "a.bin")
    # sin encolar ni cachear → unknown
    assert w.status("/data/a.bin", real)["status"] == "unknown"
    r = w.resolve("/data/a.bin")
    w.enqueue("/data/a.bin", r)
    w.enqueue("/data/a.bin", r)  # dedupe: no debe romper ni duplicar
    w.wait_idle()
    assert w.status("/data/a.bin", real)["status"] == "done"


def test_worker_error_de_lectura_no_rompe_la_cola(tmp_path):
    w, root = _worker(tmp_path)
    real_mal = _touch(root / "mal.bin")
    real_bien = _touch(root / "bien.bin", b"ok")
    r_mal = w.resolve("/data/mal.bin")
    os.remove(real_mal)  # desaparece antes de hashearse
    w.enqueue("/data/mal.bin", r_mal)
    w.enqueue("/data/bien.bin", w.resolve("/data/bien.bin"))
    w.wait_idle()
    assert w.status("/data/mal.bin", real_mal)["status"] == "error"
    assert w.status("/data/bien.bin", real_bien)["status"] == "done"


def test_worker_error_de_cache_no_mata_el_worker(tmp_path, monkeypatch):
    """Un sqlite3.Error al cachear deja error en esa ruta y el worker sigue vivo."""
    import sqlite3 as sq
    w, root = _worker(tmp_path)
    real_a = _touch(root / "a.bin", b"aaa")
    real_b = _touch(root / "b.bin", b"bbb")
    original = w.cache.put
    llamadas = {"n": 0}

    def put_falla_una_vez(*args, **kwargs):
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            raise sq.OperationalError("database is locked")
        return original(*args, **kwargs)

    monkeypatch.setattr(w.cache, "put", put_falla_una_vez)
    w.enqueue("/data/a.bin", w.resolve("/data/a.bin"))
    w.enqueue("/data/b.bin", w.resolve("/data/b.bin"))
    w.wait_idle()
    assert w.status("/data/a.bin", real_a)["status"] == "error"
    assert w.status("/data/b.bin", real_b)["status"] == "done"


def test_status_con_real_none_devuelve_error(tmp_path):
    w, _ = _worker(tmp_path)
    s = w.status("/data/lo-que-sea.bin", None)
    assert s["status"] == "error" and s["sha256"] is None
