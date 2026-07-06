import threading
import time

from app.crawler.runner import CrawlRunner


def _mk_tree(tmp_path):
    root = tmp_path / "data"
    (root / "Music").mkdir(parents=True)
    (root / "Music" / "a.mp3").write_bytes(b"x" * 10)
    return str(root)


def test_start_runs_crawl_and_releases(tmp_path):
    dbfile = str(tmp_path / "m.db")
    runner = CrawlRunner(dbfile, _mk_tree(tmp_path))
    assert runner.is_stale(24) is True  # sin db aún
    assert runner.start() is True
    for _ in range(100):  # espera activa corta (el árbol es diminuto)
        if not runner.state.running:
            break
        time.sleep(0.05)
    assert runner.state.running is False
    assert runner.last_end_at() is not None
    assert runner.is_stale(24) is False


def test_start_rejects_concurrent(tmp_path):
    dbfile = str(tmp_path / "m.db")
    runner = CrawlRunner(dbfile, _mk_tree(tmp_path))
    gate = threading.Event()
    orig_run = runner._run

    def slow_run():
        gate.wait(timeout=5)
        orig_run()

    runner._run = slow_run
    assert runner.start() is True
    assert runner.start() is False  # cerrojo
    gate.set()


def test_is_stale_by_age(tmp_path):
    dbfile = str(tmp_path / "m.db")
    fake_now = [1_000_000.0]
    runner = CrawlRunner(dbfile, _mk_tree(tmp_path), now_fn=lambda: fake_now[0])
    runner.start()
    for _ in range(100):
        if not runner.state.running:
            break
        time.sleep(0.05)
    assert runner.is_stale(24) is False
    fake_now[0] += 25 * 3600
    assert runner.is_stale(24) is True
