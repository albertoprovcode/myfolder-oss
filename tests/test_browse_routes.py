import time

from tests.helpers import add_entry

GiB = 1024 ** 3
NOW = int(time.time())
OLD = NOW - 3 * 365 * 86400  # >2 años: siempre frío


def test_children_endpoint(client, store_conn):
    _, conn = store_conn
    add_entry(conn, "Movies", "/data/Video", type="directory", size=3_000_000_000,
              owner="root", group="users", file_count=90, dir_count=10)
    add_entry(conn, "Series", "/data/Video", type="directory", size=1_500_000_000,
              owner="1001", group="media", file_count=60, dir_count=5)
    for i in range(3):
        add_entry(conn, f"small{i}.bin", "/data/Video", size=100 + i)
    r = client.get("/api/children", params={"path": "/data/Video", "limit": 2})
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["items"][0]["name"] == "Movies"
    assert body["items"][0]["path"] == "/data/Video/Movies"
    assert body["items"][0]["files"] == 90
    assert body["items"][1]["owner"] == "1001"
    assert r.headers["Cache-Control"] == "no-store"


def test_children_endpoint_sort_and_offset(client, store_conn):
    _, conn = store_conn
    base = 1_577_836_800  # 2020-01-01
    names = ["m0", "m1", "m2", "OldStuff", "m4", "m5", "m6", "m7", "m8", "m9"]
    for i, name in enumerate(names):
        add_entry(conn, name, "/data", type="directory", size=512,
                  mtime=base + i * 86400)
    r = client.get("/api/children", params={"path": "/data", "limit": 1, "offset": 3,
                                            "sort": "mtime", "order": "asc"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 10
    assert body["items"][0]["name"] == "OldStuff"
    assert r.headers["Cache-Control"] == "no-store"


def test_top_dirs_endpoint(client, store_conn):
    _, conn = store_conn
    add_entry(conn, "A", "/data", type="directory", size=1024, file_count=1)
    add_entry(conn, "f.bin", "/data", size=99999)  # los ficheros no salen aquí
    r = client.get("/api/top/dirs", params={"limit": 5})
    assert r.status_code == 200
    assert r.json()["items"][0]["name"] == "A"
    assert r.json()["items"][0]["path"] == "/data/A"
    assert r.headers["Cache-Control"] == "no-store"


def test_top_files_endpoint(client, store_conn):
    _, conn = store_conn
    add_entry(conn, "f.bin", "/d", size=1024)
    add_entry(conn, "D", "/d", type="directory", size=99999)  # los dirs no salen aquí
    r = client.get("/api/top/files", params={"limit": 5, "offset": 0})
    assert r.status_code == 200
    assert r.json()["items"][0]["name"] == "f.bin"
    assert r.json()["total"] == 1
    assert r.headers["Cache-Control"] == "no-store"


def test_tree_endpoint_root_has_no_current(client, store_conn):
    _, conn = store_conn
    add_entry(conn, "Video", "/data", type="directory", size=2048,
              file_count=2, dir_count=0)
    r = client.get("/api/tree")
    assert r.status_code == 200
    body = r.json()
    assert body["children"][0]["name"] == "Video"
    assert body["current"] is None
    assert r.headers["Cache-Control"] == "no-store"


def test_tree_endpoint_non_root_has_current(client, store_conn):
    _, conn = store_conn
    add_entry(conn, "Video", "/data", type="directory", size=5_000_000_000,
              file_count=90, dir_count=10)
    add_entry(conn, "Movies", "/data/Video", type="directory", size=2048,
              file_count=2, dir_count=0)
    r = client.get("/api/tree", params={"path": "/data/Video"})
    assert r.status_code == 200
    body = r.json()
    assert body["children"][0]["name"] == "Movies"
    assert body["current"]["items"] == 100  # 90+10
    assert r.headers["Cache-Control"] == "no-store"


def test_cold_endpoint(client, store_conn):
    _, conn = store_conn
    add_entry(conn, "old_movie.mkv", "/data/Video", size=5 * GiB, mtime=OLD, atime=OLD)
    add_entry(conn, "archive.tar.gz", "/data/Backups", size=2 * GiB, mtime=OLD, atime=OLD)
    for i in range(5):
        add_entry(conn, f"c{i}.bin", "/data/Misc", size=1024, mtime=OLD)
    add_entry(conn, "hot.bin", "/data", size=123, mtime=NOW)  # reciente: fuera
    r = client.get("/api/cold", params={"field": "mtime", "days": 365, "limit": 2})
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body
    assert "total_size_h" in body
    assert body["total"] == 7
    assert len(body["items"]) == 2
    assert body["items"][0]["name"] == "old_movie.mkv"
    assert body["items"][0]["path"] == "/data/Video"
    assert body["items"][0]["size_h"] == "5.0 GB"
    assert body["items"][1]["name"] == "archive.tar.gz"
    assert body["total_size_h"].endswith(("GB", "TB"))
    assert r.headers["Cache-Control"] == "no-store"


def test_owners_endpoint(client, store_conn):
    _, conn = store_conn
    for i in range(3):
        add_entry(conn, f"u{i}.bin", "/data", size=10 * GiB, owner="1000")
    for i in range(2):
        add_entry(conn, f"r{i}.bin", "/data", size=1 * GiB, owner="root")
    r = client.get("/api/owners", params={"field": "owner"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 2
    assert body["items"][0]["name"] == "1000"
    assert body["items"][0]["files"] == 3
    assert body["total_files"] == 5
    assert body["total_size_h"].endswith(("GB", "TB"))
    assert r.headers["Cache-Control"] == "no-store"


def test_owners_endpoint_group(client, store_conn):
    # field=group debe agregar por grupo (no por owner)
    _, conn = store_conn
    add_entry(conn, "a.bin", "/data", size=100, owner="1000", group="media")
    add_entry(conn, "b.bin", "/data", size=50, owner="2000", group="media")
    r = client.get("/api/owners", params={"field": "group"})
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == [{"name": "media", "files": 2, "size": 150,
                              "size_h": "150 B"}]
