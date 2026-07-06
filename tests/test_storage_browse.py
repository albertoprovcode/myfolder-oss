from tests.helpers import DEFAULT_EPOCH, add_entry, make_store


def _seed(conn):
    add_entry(conn, "Music", "/data", type="directory", size=300,
              file_count=3, dir_count=1)
    add_entry(conn, "Video", "/data", type="directory", size=1000,
              file_count=1, dir_count=0)
    add_entry(conn, "sub", "/data/Music", type="directory", size=200,
              file_count=2, dir_count=0, mtime=DEFAULT_EPOCH)
    add_entry(conn, "a.mp3", "/data/Music", size=100, owner="alberto")
    add_entry(conn, "b.flac", "/data/Music/sub", size=200, owner="alberto")
    add_entry(conn, "c.mkv", "/data/Video", size=1000, owner="1000")


def test_tree_root_and_current(tmp_path):
    store, conn = make_store(tmp_path)
    _seed(conn)
    t = store.tree(None)
    assert t["path"] is None and t["current"] is None
    assert [c["name"] for c in t["children"]] == ["Video", "Music"]  # size desc
    assert t["children"][1] == {"name": "Music", "path": "/data/Music",
                                "size": 300, "size_h": "300 B", "items": 4}

    t2 = store.tree("/data/Music")
    assert t2["current"]["size"] == 300
    assert t2["current"]["files"] == 3 and t2["current"]["items"] == 4
    assert [c["name"] for c in t2["children"]] == ["sub"]

    assert store.tree("/data/NoExiste")["current"] is None


def test_children_sort_and_total(tmp_path):
    store, conn = make_store(tmp_path)
    _seed(conn)
    r = store.children("/data/Music", limit=1, offset=0, sort="name", order="asc")
    assert r["total"] == 2  # a.mp3 + sub (archivos Y carpetas)
    assert r["items"][0]["name"] == "a.mp3"
    assert r["items"][0]["owner"] == "alberto" and r["items"][0]["type"] == "file"
    r2 = store.children("/data/Music", limit=10, offset=0, sort="size", order="desc")
    assert [i["name"] for i in r2["items"]] == ["sub", "a.mp3"]
    assert r2["items"][0]["dirs"] == 0 and r2["items"][0]["files"] == 2


def test_top_dirs_and_files(tmp_path):
    store, conn = make_store(tmp_path)
    _seed(conn)
    d = store.top_dirs(path=None, limit=2)["items"]
    assert d[0] == {"path": "/data/Video", "name": "Video", "size": 1000,
                    "size_h": "1000 B", "count": 1}
    f = store.top_files(path="/data/Music", limit=10, offset=0)
    assert f["total"] == 2 and f["items"][0]["name"] == "b.flac"
    assert f["items"][0]["path"] == "/data/Music/sub"


def test_cold(tmp_path):
    store, conn = make_store(tmp_path)
    now = DEFAULT_EPOCH + 400 * 86400
    add_entry(conn, "frio.iso", "/data/Backup", size=500)
    add_entry(conn, "tibio.txt", "/data/Backup", size=50, mtime=now - 86400)
    r = store.cold(field="mtime", days=365, size_min=0, limit=10, offset=0,
                   sort="size", order="desc", now=now)
    assert r["total"] == 1 and r["total_size"] == 500
    assert r["items"][0]["name"] == "frio.iso"
    r2 = store.cold(field="mtime", days=365, size_min=1000, limit=10, offset=0,
                    sort="size", order="desc", now=now)
    assert r2["total"] == 0 and r2["items"] == []


def test_cold_con_path_filtra_por_subarbol(tmp_path):
    store, conn = make_store(tmp_path)
    now = DEFAULT_EPOCH + 400 * 86400
    add_entry(conn, "frio_video.iso", "/data/Video", size=500, mtime=now - 400 * 86400)
    add_entry(conn, "frio_music.mp3", "/data/Music", size=300, mtime=now - 400 * 86400)
    add_entry(conn, "frio_music_sub.flac", "/data/Music/sub", size=200,
              mtime=now - 400 * 86400)
    add_entry(conn, "tibio_video.txt", "/data/Video", size=50, mtime=now - 86400)

    r = store.cold(field="mtime", days=365, size_min=0, limit=10, offset=0,
                   sort="size", order="desc", now=now, path="/data/Music")
    assert r["total"] == 2 and r["total_size"] == 500
    nombres = {it["name"] for it in r["items"]}
    assert nombres == {"frio_music.mp3", "frio_music_sub.flac"}

    r_video = store.cold(field="mtime", days=365, size_min=0, limit=10, offset=0,
                         sort="size", order="desc", now=now, path="/data/Video")
    assert r_video["total"] == 1 and r_video["total_size"] == 500
    assert r_video["items"][0]["name"] == "frio_video.iso"


def test_cold_sin_path_no_cambia(tmp_path):
    store, conn = make_store(tmp_path)
    now = DEFAULT_EPOCH + 400 * 86400
    add_entry(conn, "frio.iso", "/data/Backup", size=500, mtime=now - 400 * 86400)
    add_entry(conn, "tibio.txt", "/data/Backup", size=50, mtime=now - 86400)
    r = store.cold(field="mtime", days=365, size_min=0, limit=10, offset=0,
                   sort="size", order="desc", now=now)
    assert r["total"] == 1 and r["total_size"] == 500
    assert r["items"][0]["name"] == "frio.iso"


def test_owners(tmp_path):
    store, conn = make_store(tmp_path)
    _seed(conn)
    r = store.owners(field="owner", limit=10)
    assert r["items"][0] == {"name": "1000", "files": 1, "size": 1000,
                             "size_h": "1000 B"}
    assert r["total_files"] == 3 and r["total_size"] == 1300
    g = store.owners(field="group", limit=10)
    assert g["items"][0]["name"] == "users"
