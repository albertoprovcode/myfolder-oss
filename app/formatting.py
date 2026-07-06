from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_UNITS = ["B", "KB", "MB", "GB", "TB", "PB"]


def human_size(num_bytes: int) -> str:
    if num_bytes is None:
        return "0 B"
    size = float(num_bytes)
    for unit in _UNITS:
        if size < 1024 or unit == _UNITS[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def parse_iso(value: str | int | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    # ISO-8601 string, possibly with trailing 'Z'
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def human_date(value: str | int | None) -> str | None:
    dt = parse_iso(value)
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%d")


def human_datetime(value: str | int | None, tz_name: str = "Europe/Madrid") -> str | None:
    dt = parse_iso(value)
    if dt is None:
        return None
    # Treat naive datetimes as UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local_dt = dt.astimezone(ZoneInfo(tz_name))
    return local_dt.strftime("%Y-%m-%d %H:%M")
