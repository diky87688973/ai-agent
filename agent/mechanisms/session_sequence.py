# -*- coding: utf-8 -*-
"""Shared sequence allocation for session and child facts."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Callable


class SessionSequence:
    def __init__(self, path: Path, bootstrap: Callable[[], int]) -> None:
        self.path = path
        self._bootstrap = bootstrap
        self._ready = False

    def reserve(self, count: int, observed: int) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            if not self._ready:
                self._initialize(db)
            with db:
                row = db.execute(
                    "UPDATE watermark SET next=MAX(next,?)+? WHERE id=1 RETURNING next",
                    (observed + 1, count),
                ).fetchone()
                return int(row[0]) - count

    def _initialize(self, db: sqlite3.Connection) -> None:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE IF NOT EXISTS watermark (id INTEGER PRIMARY KEY, next INTEGER)")
        if db.execute("SELECT 1 FROM watermark WHERE id=1").fetchone() is None:
            start = self._bootstrap() + 1
            with db:
                db.execute("INSERT OR IGNORE INTO watermark VALUES (1,?)", (start,))
        self._ready = True
