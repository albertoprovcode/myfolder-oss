"""Orquestación del crawl: cerrojo, hilo de fondo y regla de frescura (spec §6)."""
from __future__ import annotations

import logging
import os
import threading
import time

from .. import db
from .build import build_index
from .state import CrawlState

logger = logging.getLogger("myfolder.crawler")


class CrawlRunner:
    def __init__(self, db_path: str, data_root: str, now_fn=time.time) -> None:
        self.db_path = db_path
        self.data_root = data_root
        self.now_fn = now_fn
        self.state = CrawlState()
        self._lock = threading.Lock()

    def start(self) -> bool:
        with self._lock:
            if self.state.running:
                return False
            self.state.running = True
            self.state.entries = 0
            self.state.started_at = self.now_fn()
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def _run(self) -> None:
        try:
            result = build_index(self.db_path, self.data_root,
                                 state=self.state, now_fn=self.now_fn)
            logger.info("crawl OK: %s", result)
        except Exception:
            logger.exception("crawl FALLIDO (se conserva el índice anterior)")
        finally:
            self.state.running = False

    def last_end_at(self) -> float | None:
        if not os.path.exists(self.db_path):
            return None
        conn = db.open_ro(self.db_path)
        try:
            row = conn.execute(
                "SELECT MAX(end_at) AS v FROM indexinfo WHERE end_at IS NOT NULL"
            ).fetchone()
            return row["v"]
        finally:
            conn.close()

    def is_stale(self, max_age_h: int) -> bool:
        last = self.last_end_at()
        if last is None:
            return True
        return self.now_fn() - last > max_age_h * 3600
