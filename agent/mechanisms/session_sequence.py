# -*- coding: utf-8 -*-
"""Shared sequence allocation for session and child facts."""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Callable

from agent.core.error_report import report_error

#: 同一 data_root 下的序列库由所有 `SessionStore` 实例共享，进程内用一把锁
#: 串行初始化；已完成的路径记在这里，后续实例直接跳过。
_INIT_LOCK = threading.Lock()
_READY_PATHS: set[str] = set()

#: `PRAGMA journal_mode` 需要排他访问：别的连接持锁时它立刻返回 busy，
#: 不吃 `connect(timeout=)` 的 busy handler，所以只能自己退避重试。
_WAL_ATTEMPTS = 5
_WAL_BACKOFF_SECONDS = 0.05


class SessionSequence:
    def __init__(self, path: Path, bootstrap: Callable[[], int]) -> None:
        self.path = path
        self._bootstrap = bootstrap

    def reserve(self, count: int, observed: int) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            self._ensure_ready(db)
            with db:
                row = db.execute(
                    "UPDATE watermark SET next=MAX(next,?)+? WHERE id=1 RETURNING next",
                    (observed + 1, count),
                ).fetchone()
                return int(row[0]) - count

    def _ensure_ready(self, db: sqlite3.Connection) -> None:
        key = str(self.path)
        if key in _READY_PATHS:
            return
        with _INIT_LOCK:
            if key in _READY_PATHS:
                return
            self._initialize(db)
            _READY_PATHS.add(key)

    def _initialize(self, db: sqlite3.Connection) -> None:
        """建水位表并切 WAL；并发首用由 `_INIT_LOCK` 串行。"""
        db.execute(
            "CREATE TABLE IF NOT EXISTS watermark (id INTEGER PRIMARY KEY, next INTEGER)")
        if db.execute("SELECT 1 FROM watermark WHERE id=1").fetchone() is None:
            start = self._bootstrap() + 1
            with db:
                db.execute("INSERT OR IGNORE INTO watermark VALUES (1,?)", (start,))
        self._enable_wal(db)

    @staticmethod
    def _enable_wal(db: sqlite3.Connection) -> None:
        """切 WAL；拿不到排他锁时保留默认日志模式。

        WAL 只影响并发读写性能，不是正确性前提：切不过去仍可正常取号，
        因此重试到上限后留痕放行，不阻断调用方。最后一次异常随记录上报。
        """
        failure: Exception = RuntimeError("journal_mode 未能切到 WAL，保留默认日志模式")
        for attempt in range(_WAL_ATTEMPTS):
            try:
                row = db.execute("PRAGMA journal_mode=WAL").fetchone()
                if row and str(row[0]).lower() == "wal":
                    return
            except sqlite3.OperationalError as exc:
                failure = exc
            time.sleep(_WAL_BACKOFF_SECONDS * (attempt + 1))
        report_error("agent.mechanisms.session_sequence.enable_wal", failure)
