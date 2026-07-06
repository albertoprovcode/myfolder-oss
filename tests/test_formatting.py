from app.formatting import human_size, human_date, human_datetime


def test_human_size_units():
    assert human_size(0) == "0 B"
    assert human_size(512) == "512 B"
    assert human_size(1536) == "1.5 KB"
    assert human_size(5 * 1024**3) == "5.0 GB"
    assert human_size(int(2.5 * 1024**4)) == "2.5 TB"


def test_human_date_from_iso():
    assert human_date("2026-06-29T12:34:56") == "2026-06-29"


def test_human_date_none():
    assert human_date(None) is None


def test_human_datetime_converts_utc_to_madrid():
    # 2026-06-29T16:32:17 UTC = 18:32 in Europe/Madrid (UTC+2 summer)
    assert human_datetime("2026-06-29T16:32:17") == "2026-06-29 18:32"


def test_human_datetime_none_returns_none():
    assert human_datetime(None) is None
