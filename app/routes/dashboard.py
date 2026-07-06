from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from fastapi import HTTPException

from ..config import settings
from ..storage import Storage, get_store

router = APIRouter(prefix="/api")


@router.get("/summary")
def summary(request: Request, store: Storage = Depends(get_store)):
    out = store.summary()
    out["indexed_at"] = store.indexed_at()
    runner = getattr(request.app.state, "runner", None)
    out["crawling"] = bool(runner and runner.state.running)
    if out["crawling"]:
        out["crawl_entries"] = runner.state.entries
    return out


@router.post("/reindex")
def reindex(request: Request):
    runner = request.app.state.runner
    if not runner.start():
        raise HTTPException(status_code=409, detail="Ya hay un indexado en curso")
    return JSONResponse({"started": True}, status_code=202)


@router.get("/removable")
def removable(store: Storage = Depends(get_store)):
    return store.removable(settings.cleanlist_days)


@router.get("/extensions")
def extensions(path: str | None = Query(default=None), by: str = Query(default="size"),
               limit: int = Query(default=15, le=100),
               store: Storage = Depends(get_store)):
    by = by if by in ("size", "count") else "size"
    return store.extensions(path, by, limit)


@router.get("/types")
def types(path: str | None = Query(default=None), store: Storage = Depends(get_store)):
    return store.types(path)


@router.get("/space")
def space(store: Storage = Depends(get_store)):
    return store.space()


@router.get("/age")
def age(path: str | None = Query(default=None), field: str = Query(default="mtime"),
        store: Storage = Depends(get_store)):
    field = field if field in ("mtime", "atime") else "mtime"
    return store.age(path, field)
