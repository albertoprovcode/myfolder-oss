import re
import time

from tests.helpers import add_entry, add_indexinfo, add_space

TiB = 1024 ** 4
NOW = int(time.time())
OLD = NOW - 3 * 365 * 86400  # >2 años: siempre frío/removable


def test_summary_endpoint(client, store_conn):
    from app.formatting import human_datetime

    _, conn = store_conn
    add_entry(conn, "a.mp3", "/data/Music", size=2048)
    add_indexinfo(conn, start_at=1_750_000_000, end_at=1_750_000_600)
    r = client.get("/api/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["files"] == 1
    assert body["total_size"] == 2048
    assert body["total_size_h"] == "2.0 KB"
    assert r.headers["cache-control"] == "no-store"
    # indexed_at must be day+time format "YYYY-MM-DD HH:MM"
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", body["indexed_at"])
    assert body["indexed_at"] == human_datetime(1_750_000_600)
    # En esta fase crawling es False fijo; Task 8 lo conecta al CrawlRunner.
    assert body["crawling"] is False


def test_summary_without_index_yet(client):
    r = client.get("/api/summary")
    assert r.status_code == 200
    assert r.json() == {"files": 0, "dirs": 0, "total_size": 0, "total_size_h": "0 B",
                        "indexed_at": None, "crawling": False}


def test_removable_endpoint(client, store_conn):
    _, conn = store_conn
    for i in range(5):
        add_entry(conn, f"old{i}.bin", "/data/Backups", size=1024, mtime=OLD)
    add_entry(conn, "fresh.bin", "/data/Backups", size=999, mtime=NOW)
    r = client.get("/api/removable")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 5
    assert body["size"] == 5 * 1024
    assert r.headers["cache-control"] == "no-store"


def test_age_endpoint(client, store_conn):
    _, conn = store_conn
    add_entry(conn, "recent.bin", "/data", size=1024, mtime=NOW - 86400)
    add_entry(conn, "ancient.bin", "/data", size=10, mtime=OLD)
    r = client.get("/api/age", params={"field": "mtime"})
    assert r.status_code == 200
    buckets = r.json()["buckets"]
    assert buckets[0]["label"] == "0-30d"
    assert buckets[0]["count"] == 1
    assert buckets[0]["size"] == 1024
    assert buckets[-1]["label"] == ">2a"
    assert buckets[-1]["count"] == 1
    assert r.headers["Cache-Control"] == "no-store"


def test_space_endpoint(client, store_conn):
    _, conn = store_conn
    add_space(conn, path="/data", total=4 * TiB, used=3 * TiB, free=1 * TiB)
    r = client.get("/api/space")
    assert r.status_code == 200
    body = r.json()
    assert body["free_h"].endswith("TB")
    assert body["free_percent"] == 25.0
    assert r.headers["Cache-Control"] == "no-store"


def test_extensions_and_types_endpoints(client, store_conn):
    _, conn = store_conn
    add_entry(conn, "movie.mp4", "/data/Video", size=2048, extension="mp4")
    add_entry(conn, "song.mp3", "/data/Music", size=100, extension="mp3")

    r1 = client.get("/api/extensions", params={"by": "size"})
    assert r1.status_code == 200
    assert r1.json()["items"][0]["ext"] == "mp4"
    assert r1.json()["items"][0]["size_h"] == "2.0 KB"
    assert r1.headers["Cache-Control"] == "no-store"

    r2 = client.get("/api/types")
    assert r2.status_code == 200
    assert r2.json()["items"][0]["category"] == "video"
    assert r2.headers["Cache-Control"] == "no-store"


def test_reindex_endpoint(client):
    class FakeRunner:
        def __init__(self):
            self.calls = 0

        def start(self):
            self.calls += 1
            return self.calls == 1

        class state:
            running = False
            entries = 0

    from app.main import app
    orig_runner = app.state.runner
    try:
        app.state.runner = FakeRunner()
        assert client.post("/api/reindex").status_code == 202
        assert client.post("/api/reindex").status_code == 409
    finally:
        app.state.runner = orig_runner


def test_summary_reports_crawling_progress(client):
    class FakeState:
        running = True
        entries = 1234

    class FakeRunner:
        state = FakeState()

    from app.main import app
    orig_runner = app.state.runner
    try:
        app.state.runner = FakeRunner()
        body = client.get("/api/summary").json()
        assert body["crawling"] is True
        assert body["crawl_entries"] == 1234
    finally:
        app.state.runner = orig_runner
