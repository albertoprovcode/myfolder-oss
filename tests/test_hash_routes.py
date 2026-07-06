"""Tests de POST /api/hash y GET /api/hash/status."""
import hashlib

import pytest
from fastapi.testclient import TestClient

from app.hasher import HashCache, HashWorker
from app.main import app
from app.storage import get_store
from tests.helpers import make_store


@pytest.fixture
def hash_client(tmp_path):
    store, _ = make_store(tmp_path)
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as c:
        root = tmp_path / "root"
        root.mkdir(exist_ok=True)
        app.state.hasher = HashWorker(
            HashCache(str(tmp_path / "hashes.db")), str(root))
        yield c, root
    app.dependency_overrides.clear()


def _touch(path, content=b"hola"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_post_hash_encola_y_status_termina_en_done(hash_client):
    c, root = hash_client
    _touch(root / "Video" / "a.mkv", b"contenido")
    _touch(root / "Backup" / "b.mkv", b"contenido")
    r = c.post("/api/hash", json={"paths": ["/data/Video/a.mkv", "/data/Backup/b.mkv"]})
    assert r.status_code == 202
    body = r.json()
    assert body["queued"] == 2 and body["cached"] == 0 and body["rejected"] == []
    app.state.hasher.wait_idle()
    r2 = c.get("/api/hash/status",
               params={"paths": "/data/Video/a.mkv|/data/Backup/b.mkv"})
    res = r2.json()["results"]
    esperado = hashlib.sha256(b"contenido").hexdigest()
    assert res["/data/Video/a.mkv"] == {"status": "done", "sha256": esperado, "error": None}
    assert res["/data/Backup/b.mkv"]["sha256"] == esperado


def test_post_hash_repetido_cuenta_como_cached(hash_client):
    c, root = hash_client
    _touch(root / "a.bin")
    c.post("/api/hash", json={"paths": ["/data/a.bin"]})
    app.state.hasher.wait_idle()
    r = c.post("/api/hash", json={"paths": ["/data/a.bin"]})
    assert r.json() == {"queued": 0, "cached": 1, "rejected": []}


def test_post_hash_rechaza_rutas_invalidas(hash_client):
    c, root = hash_client
    r = c.post("/api/hash", json={"paths": [
        "/data/../etc/passwd", "/otro/x.bin", "/data/no-existe.bin"]})
    assert r.status_code == 202
    assert sorted(r.json()["rejected"]) == [
        "/data/../etc/passwd", "/data/no-existe.bin", "/otro/x.bin"]


def test_post_hash_tope_50_rutas(hash_client):
    c, _ = hash_client
    r = c.post("/api/hash", json={"paths": [f"/data/f{i}.bin" for i in range(51)]})
    assert r.status_code == 422


def test_status_de_ruta_desaparecida_es_error(hash_client):
    c, _ = hash_client
    r = c.get("/api/hash/status", params={"paths": "/data/no-existe.bin"})
    s = r.json()["results"]["/data/no-existe.bin"]
    assert s["status"] == "error" and "reindexa" in s["error"]


def test_status_sin_cache_ni_cola_es_unknown(hash_client):
    c, root = hash_client
    _touch(root / "a.bin")
    r = c.get("/api/hash/status", params={"paths": "/data/a.bin"})
    assert r.json()["results"]["/data/a.bin"]["status"] == "unknown"
