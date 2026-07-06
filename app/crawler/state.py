"""Estado en memoria del crawl en curso. El crawl escribe en un fichero
.building que el resto de la app no ve, así que 'está indexando' y el
progreso viven en el proceso, no en la BD (spec §6)."""
from __future__ import annotations


class CrawlState:
    def __init__(self) -> None:
        self.running: bool = False
        self.entries: int = 0
        self.started_at: float | None = None
