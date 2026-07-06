import asyncio
import contextlib
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from app.config import settings
from app.crawler.runner import CrawlRunner
from app.crawler.schedule import daily_loop
from app.hasher import HashCache, HashWorker


@asynccontextmanager
async def lifespan(app):
    runner = CrawlRunner(settings.db_path, settings.data_root)
    app.state.runner = runner
    app.state.hasher = HashWorker(HashCache(settings.hash_db_path),
                                  settings.data_root)
    task = None
    if settings.auto_reindex:
        if runner.is_stale(settings.reindex_max_age_h):
            runner.start()
        task = asyncio.create_task(daily_loop(
            runner, settings.reindex_hour, settings.reindex_max_age_h))
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="myfolder", docs_url=None, redoc_url=None, lifespan=lifespan)


@app.middleware("http")
async def cache_control(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/api/") or path == "/healthz":
        response.headers["Cache-Control"] = "no-store"
    elif path.startswith("/static/vendor/"):
        # Librerías de terceros (echarts, ~1MB): no cambian nunca → caché
        # inmutable de 1 año. Evita rebajar 1MB en cada recarga.
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path == "/" or path.startswith("/static/"):
        # HTML/JS/CSS propios: revalidar siempre (304 si no cambió).
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(os.path.dirname(__file__), "..", "static", "index.html"))


@app.get("/healthz")
def healthz() -> JSONResponse:
    return JSONResponse({"status": "ok"})


from app.routes import dashboard as dashboard_routes  # noqa: E402
from app.routes import browse as browse_routes  # noqa: E402
from app.routes import search as search_routes  # noqa: E402
from app.routes import hash as hash_routes  # noqa: E402

app.include_router(dashboard_routes.router)
app.include_router(browse_routes.router)
app.include_router(search_routes.router)
app.include_router(hash_routes.router)


# Static mount is added in Task 10 (directory must exist first).
def _mount_static() -> None:
    static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")


_mount_static()
