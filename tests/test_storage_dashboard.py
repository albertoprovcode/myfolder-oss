from tests.helpers import DEFAULT_EPOCH, add_entry, add_indexinfo, add_space, make_store


def test_summary_counts_and_size(tmp_path):
    store, conn = make_store(tmp_path)
    add_entry(conn, "a.mp3", "/data/Music", size=100, extension="mp3")
    add_entry(conn, "b.mkv", "/data/Video", size=1000, extension="mkv")
    add_entry(conn, "Music", "/data", type="directory", size=100)
    s = store.summary()
    assert s == {"files": 2, "dirs": 1, "total_size": 1100, "total_size_h": "1.1 KB"}


def test_summary_empty_when_db_missing(tmp_path):
    from app.storage import Storage
    store = Storage(str(tmp_path / "nope.db"))
    assert store.available() is False
    assert store.summary()["files"] == 0


def test_indexed_at(tmp_path):
    from app.formatting import human_datetime

    store, conn = make_store(tmp_path)
    assert store.indexed_at() is None
    add_indexinfo(conn, start_at=1_750_000_000, end_at=1_750_000_600)
    assert store.indexed_at() == human_datetime(1_750_000_600)  # "YYYY-MM-DD HH:MM"


def test_removable(tmp_path):
    store, conn = make_store(tmp_path)
    now = DEFAULT_EPOCH + 400 * 86400
    add_entry(conn, "viejo.iso", "/data/Backup", size=500)          # 400 días
    add_entry(conn, "nuevo.txt", "/data/Backup", size=50, mtime=now - 10)
    r = store.removable(days=365, now=now)
    assert r == {"count": 1, "size": 500, "size_h": "500 B"}


def test_extensions_and_types(tmp_path):
    store, conn = make_store(tmp_path)
    add_entry(conn, "a.mp3", "/data/Music", size=100, extension="mp3")
    add_entry(conn, "b.mp3", "/data/Music", size=200, extension="mp3")
    add_entry(conn, "c.pdf", "/data/Documents", size=50, extension="pdf")
    add_entry(conn, "raro", "/data/Backup", size=10, extension=None)

    ext = store.extensions(path=None, by="size", limit=10)["items"]
    assert ext[0] == {"ext": "mp3", "size": 300, "size_h": "300 B", "count": 2}
    assert any(i["ext"] == "(sin ext)" for i in ext)

    only_music = store.extensions(path="/data/Music", by="size", limit=10)["items"]
    assert [i["ext"] for i in only_music] == ["mp3"]

    t = store.types(path=None)["items"]
    assert t[0]["category"] == "audio" and t[0]["pct"] > 0


def test_space(tmp_path):
    store, conn = make_store(tmp_path)
    add_space(conn, "/data", total=1000, used=600, free=400)
    s = store.space()
    assert s["total"] == 1000 and s["free_percent"] == 40.0 and s["used_h"] == "600 B"


def test_age_buckets_all_present(tmp_path):
    store, conn = make_store(tmp_path)
    now = DEFAULT_EPOCH
    add_entry(conn, "reciente.txt", "/data/Docs", size=10, mtime=now - 5 * 86400)
    add_entry(conn, "antiguo.txt", "/data/Docs", size=99, mtime=now - 800 * 86400)
    buckets = store.age(path=None, field="mtime", now=now)["buckets"]
    assert [b["label"] for b in buckets] == ["0-30d", "30-90d", "90d-1a", "1-2a", ">2a"]
    assert buckets[0]["count"] == 1 and buckets[-1]["size"] == 99
