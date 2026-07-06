import asyncio
from datetime import datetime

from app.crawler.schedule import daily_loop, seconds_until_hour


def test_seconds_until_hour_same_day():
    now = datetime(2026, 7, 1, 9, 0, 0)
    assert seconds_until_hour(now, 13) == 4 * 3600


def test_seconds_until_hour_next_day():
    now = datetime(2026, 7, 1, 14, 30, 0)
    assert seconds_until_hour(now, 13) == 22.5 * 3600


def test_daily_loop_fires_only_if_stale():
    calls = {"start": 0, "stale": True}

    class FakeRunner:
        def is_stale(self, h):
            return calls["stale"]

        def start(self):
            calls["start"] += 1
            return True

    sleeps = []

    async def fake_sleep(secs):
        sleeps.append(secs)
        if len(sleeps) >= 4:  # 2 iteraciones (espera + colchón)
            raise asyncio.CancelledError

    async def run():
        try:
            await daily_loop(FakeRunner(), hour=13, max_age_h=24, sleep=fake_sleep)
        except asyncio.CancelledError:
            pass

    asyncio.run(run())
    assert calls["start"] == 2
    calls["start"] = 0
    calls["stale"] = False
    sleeps.clear()
    asyncio.run(run())
    assert calls["start"] == 0  # fresco: no dispara
