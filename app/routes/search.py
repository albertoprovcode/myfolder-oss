from fastapi import APIRouter, Depends, Query

from ..storage import Storage, get_store

router = APIRouter(prefix="/api")


@router.get("/search")
def search(
    name: str | None = Query(default=None),
    ext: str | None = Query(default=None),
    type: str | None = Query(default=None),
    owner: str | None = Query(default=None),
    group: str | None = Query(default=None),
    size_min: int | None = Query(default=None),
    size_max: int | None = Query(default=None),
    mtime_from: str | None = Query(default=None),
    mtime_to: str | None = Query(default=None),
    atime_from: str | None = Query(default=None),
    atime_to: str | None = Query(default=None),
    path: str | None = Query(default=None),
    category: str | None = Query(default=None),
    dupes_only: bool = Query(default=False),
    sort: str = Query(default="size"),
    order: str = Query(default="desc"),
    limit: int = Query(default=25, le=200),
    offset: int = Query(default=0, ge=0),
    group_limit: int | None = Query(default=None, ge=1, le=50),
    group_offset: int = Query(default=0, ge=0),
    store: Storage = Depends(get_store),
):
    filters = {
        "name": name, "ext": ext, "type": type, "owner": owner, "group": group,
        "size_min": size_min, "size_max": size_max,
        "mtime_from": mtime_from, "mtime_to": mtime_to,
        "atime_from": atime_from, "atime_to": atime_to,
        "path": path, "category": category, "dupes_only": dupes_only,
        "sort": sort, "order": order,
    }
    return store.search(filters, limit, offset,
                        group_limit=group_limit, group_offset=group_offset)


@router.get("/dupes")
def dupes(
    path: str | None = Query(default=None),
    min_size: int = Query(default=1_000_000),
    limit: int = Query(default=50, le=200),
    store: Storage = Depends(get_store),
):
    return store.dupes(path, min_size, limit)
