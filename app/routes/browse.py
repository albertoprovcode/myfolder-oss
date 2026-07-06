from fastapi import APIRouter, Depends, Query

from ..config import settings
from ..schema import ROOT_PATH
from ..storage import Storage, get_store

router = APIRouter(prefix="/api")

DEFAULT_COLD_DAYS = settings.cleanlist_days


@router.get("/tree")
def tree(path: str | None = Query(default=None), store: Storage = Depends(get_store)):
    return store.tree(path)


@router.get("/top/dirs")
def top_dirs(path: str | None = Query(default=None), limit: int = Query(default=20, le=200),
             store: Storage = Depends(get_store)):
    return store.top_dirs(path, limit)


@router.get("/top/files")
def top_files(path: str | None = Query(default=None), limit: int = Query(default=20, le=200),
              offset: int = Query(default=0, ge=0), store: Storage = Depends(get_store)):
    return store.top_files(path, limit, offset)


@router.get("/children")
def children(path: str | None = Query(default=None), limit: int = Query(default=50, le=500),
             offset: int = Query(default=0), sort: str = Query(default="size"),
             order: str = Query(default="desc"), store: Storage = Depends(get_store)):
    return store.children(path or ROOT_PATH, limit, offset, sort, order)


@router.get("/cold")
def cold(
    field: str = Query(default="mtime"),
    days: int = Query(default=DEFAULT_COLD_DAYS),
    size_min: int = Query(default=0),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0),
    sort: str = Query(default="size"),
    order: str = Query(default="desc"),
    path: str | None = Query(default=None),
    store: Storage = Depends(get_store),
):
    return store.cold(field, days, size_min, limit, offset, sort, order, path=path)


@router.get("/owners")
def owners(
    field: str = Query(default="owner"),
    limit: int = Query(default=50, le=500),
    store: Storage = Depends(get_store),
):
    return store.owners(field, limit)
