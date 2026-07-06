# myfolder

A self-hosted, **read-only** disk explorer for your NAS — built to do storage
housekeeping from your phone. myfolder ships its own crawler that indexes the
folders you mount into a local SQLite database, then serves a responsive web UI
to browse, search, and find what's eating your space.

It never modifies your files. The only thing it ever writes is its own SQLite
index; every data mount is read-only.

> The UI is in Spanish (it was built for the author's own use). The code,
> configuration, and this README are in English. Contributions to internationalize
> the UI are welcome.

## What it does

- **Summary** — total files, size, free space, and breakdowns by type, extension, and age.
- **Explorer** — a resizable folder tree with rolled-up sizes, a sortable/paginated table, and per-folder stats.
- **Search** — by name/extension with advanced filters (size range, category, access date, owner/group), sortable columns, and handy presets (huge files, videos, not accessed in 2 years, empty, large duplicates).
- **Map** — a drill-down treemap of where your space goes.
- **Owners** — space usage aggregated by owner/group.
- **Recoverable** — cold data (not accessed in a configurable number of days), scoped to any subtree.
- **Duplicate confirmation** — same-size files are grouped instantly; an on-demand, per-group SHA-256 check confirms whether they're truly identical (single background worker, cached separately so it survives reindexing).
- **On-demand reindex** — a button in the UI, plus optional automatic reindexing on startup and on a daily schedule.

## Architecture

A single container:

- **FastAPI** backend serving a JSON API and static assets.
- A **crawler** that walks the mounted folders (post-order, rolled-up totals, one thread per share) and writes to **SQLite** with an atomic swap — you never see a half-written index.
- **SQLite + FTS5** (trigram) for fast substring search.

No external services: no Elasticsearch, no message queue, no database server to run.

The frontend is dependency-free vanilla JS (ES modules) plus a vendored copy of
ECharts for the charts.

## Quick start

### Run locally (development)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8017 --reload
```

Open http://localhost:8017. With no index yet, the UI loads and data views are
empty until the first crawl — hit the reindex button (or `POST /api/reindex`).

Run the tests (all mocked, no external services needed):

```bash
pytest tests/
```

### Run with Docker

```bash
cp docker-compose.example.yml docker-compose.yml
# edit docker-compose.yml: point the read-only volumes at the folders you want to index
docker compose up -d --build
curl http://localhost:8017/healthz   # -> {"status":"ok"}
```

Then open `http://<host>:8017`.

## Configuration

All configuration is via environment variables (see `docker-compose.example.yml`):

| Variable | Default | Description |
|---|---|---|
| `DATA_ROOT` | `/data` | Root under which the crawler looks for mounted shares. |
| `DB_PATH` | `/config/data/myfolder.db` | Path to the SQLite index (must live inside the writable `./data` volume). |
| `REINDEX_HOUR` | `13` | Local hour (0-23, per `TZ`) of the daily automatic reindex. |
| `REINDEX_MAX_AGE_H` | `24` | Max age (hours) of the index before it's considered stale. |
| `AUTO_REINDEX` | `1` | Set to `0` to disable automatic triggers (startup + daily); the manual button always works. |
| `CLEANLIST_DAYS` | `365` | Age threshold (days) for the "recoverable" / cold-data views. |

### Reindex triggers

1. **Manual** (`POST /api/reindex`): always available, regardless of `AUTO_REINDEX`.
2. **On container startup**: if `AUTO_REINDEX=1` and the last index is older than `REINDEX_MAX_AGE_H` (or missing).
3. **Daily**: if `AUTO_REINDEX=1`, at `REINDEX_HOUR` each day, only if the index is stale.

## Mounting your data

Mount whatever folders you want to index under `/data/<Name>` in read-only mode.
`<Name>` is what shows up in the UI; the host path can be anything:

```yaml
volumes:
  - /path/to/media:/data/Media:ro
  - /path/to/documents:/data/Documents:ro
  - ./data:/config/data            # SQLite index (writable)
```

To resolve numeric UIDs/GIDs to real user names in the Owners view, optionally
mount your host's `/etc/passwd` and `/etc/group` read-only (see the example compose).

## License

[MIT](LICENSE)
