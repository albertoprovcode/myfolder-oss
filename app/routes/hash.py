"""Verificación de duplicados por hash (spec 2026-07-03). La app sigue siendo
solo lectura: estos endpoints únicamente LEEN ficheros para hashearlos."""
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api")

MAX_PATHS = 50
_ERROR_NO_DISPONIBLE = "cambiado o no disponible — reindexa"


class HashRequest(BaseModel):
    paths: list[str]


@router.post("/hash", status_code=202)
def hash_group(body: HashRequest, request: Request):
    if len(body.paths) > MAX_PATHS:
        raise HTTPException(status_code=422, detail=f"máximo {MAX_PATHS} rutas")
    hasher = request.app.state.hasher
    queued, cached, rejected = 0, 0, []
    for logical in body.paths:
        real = hasher.resolve(logical)
        if real is None:
            rejected.append(logical)
            continue
        if hasher.cache.get_valid(logical, real):
            cached += 1
            continue
        hasher.enqueue(logical, real)
        queued += 1
    return {"queued": queued, "cached": cached, "rejected": rejected}


@router.get("/hash/status")
def hash_status(request: Request, paths: str = Query(default="")):
    hasher = request.app.state.hasher
    results = {}
    for logical in paths.split("|"):
        if not logical:
            continue
        real = hasher.resolve(logical)
        if real is None:
            results[logical] = {"status": "error", "sha256": None,
                                "error": _ERROR_NO_DISPONIBLE}
        else:
            results[logical] = hasher.status(logical, real)
    return {"results": results}
