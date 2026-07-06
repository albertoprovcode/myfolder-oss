"""Disparadores automáticos (spec §6): arranque y diario, ambos con la regla
de frescura — solo si el último indexado tiene más de max_age_h horas."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta


def seconds_until_hour(now: datetime, hour: int) -> float:
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def daily_loop(runner, hour: int, max_age_h: int, sleep=asyncio.sleep) -> None:
    while True:
        await sleep(seconds_until_hour(datetime.now(), hour))
        if runner.is_stale(max_age_h):
            runner.start()
        await sleep(61)  # colchón para no re-disparar en el mismo minuto
