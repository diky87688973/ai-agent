"""Indexed session summaries and durable user organization."""
from __future__ import annotations

import os
import sqlite3
import threading
import time
import uuid
from contextlib import closing, contextmanager
from pathlib import Path

from agent.core.error_report import report_error
from agent.mechanisms.session_store import is_valid_conversation_id
from agent.mechanisms.session_title import UNKNOWN_TITLE, TitleStore, is_placeholder_title

PAGE_SIZE = 30
_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE);
CREATE INDEX IF NOT EXISTS project_order ON projects(name COLLATE NOCASE, id);
CREATE TABLE IF NOT EXISTS organization (
    cid TEXT PRIMARY KEY, project TEXT REFERENCES projects(id) ON DELETE SET NULL,
    pinned INTEGER);
CREATE INDEX IF NOT EXISTS pin_order ON organization(pinned DESC, cid DESC);
CREATE TABLE IF NOT EXISTS summaries (
    cid TEXT PRIMARY KEY, activity INTEGER NOT NULL, title TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS recent_order ON summaries(activity DESC, cid DESC);
CREATE INDEX IF NOT EXISTS project_page ON organization(project, cid DESC);
PRAGMA user_version=1;
"""


class SessionCatalog:
    """SQLite owns organization. Summaries are recoverable from file metadata."""

    def __init__(self, path: Path, raw_dir: Path, titles: TitleStore) -> None:
        self.path = path
        self.raw_dir = raw_dir
        self.titles = titles
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self.initialized = threading.Event()
        self._dirty: set[str] = set()
        self._worker: threading.Thread | None = None
        self._state = "preparing"

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @contextmanager
    def _database(self):
        with closing(sqlite3.connect(self.path, timeout=2.0)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db

    def start(self) -> None:
        with self._lock:
            if self._worker is None and not self._stop.is_set():
                self._worker = threading.Thread(target=self._work, daemon=True,
                                                name="session-catalog")
                self._worker.start()

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._worker is not None:
            self._worker.join(timeout=3)

    def touch(self, cid: str) -> None:
        if not is_valid_conversation_id(cid):
            return
        with self._lock:
            self._dirty.add(cid)
        self._wake.set()

    def _summary(self, cid: str) -> tuple[str, int, str] | None:
        path = self.raw_dir / f"{cid}.raw"
        try:
            stat = path.stat()
        except FileNotFoundError:
            return None
        if not stat.st_size:
            return None
        title = self.titles.load(cid)
        return cid, stat.st_mtime_ns, UNKNOWN_TITLE if is_placeholder_title(title) else title

    def _save(self, ids: list[str]) -> None:
        if not ids:
            return
        with self._database() as db:
            db.execute("BEGIN IMMEDIATE")
            for cid in ids:
                row = self._summary(cid)
                if row is None:
                    db.execute("DELETE FROM summaries WHERE cid=?", (cid,))
                else:
                    db.execute("""INSERT INTO summaries VALUES (?,?,?)
                        ON CONFLICT(cid) DO UPDATE SET activity=excluded.activity,
                        title=excluded.title WHERE excluded.activity<>activity OR excluded.title<>title""", row)

    def _scan(self) -> None:
        seen = set()
        batch = []
        if self.raw_dir.is_dir():
            with os.scandir(self.raw_dir) as entries:
                for entry in entries:
                    if self._stop.is_set():
                        return
                    if entry.name.endswith(".raw") and is_valid_conversation_id(entry.name[:-4]):
                        cid = entry.name[:-4]
                        seen.add(cid)
                        batch.append(cid)
                    if len(batch) >= 64:
                        self._save(batch)
                        batch.clear()
        self._save(batch)
        with self._database() as db:
            known = [row[0] for row in db.execute("SELECT cid FROM summaries")]
        missing = [cid for cid in known if cid not in seen]
        for start in range(0, len(missing), 64):
            self._save(missing[start:start + 64])

    def _work(self) -> None:
        next_scan = 0.0
        dirty: set[str] = set()
        while not self._stop.is_set():
            self._wake.clear()
            try:
                if not next_scan:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    with self._database() as db:
                        db.execute("PRAGMA journal_mode=WAL")
                        version = db.execute("PRAGMA user_version").fetchone()[0]
                        if version == 0:
                            db.executescript("BEGIN IMMEDIATE;" + _SCHEMA + "COMMIT;")
                        elif version != 1:
                            raise sqlite3.DatabaseError("不支持的会话目录版本")
                    self.initialized.set()
                with self._lock:
                    dirty.update(self._dirty)
                    self._dirty.clear()
                ordered = sorted(dirty)
                for offset in range(0, len(ordered), 64):
                    self._save(ordered[offset:offset + 64])
                dirty.clear()
                if time.monotonic() >= next_scan:
                    self._scan()
                    next_scan = time.monotonic() + 60
                with self._lock:
                    self._state = "ready"
                self._wake.wait(max(0.0, next_scan - time.monotonic()))
            except (OSError, sqlite3.Error) as exc:
                with self._lock:
                    self._state = "error"
                report_error("session_catalog.worker", exc)
                self._stop.wait(3)

    def page(self, section: str, before: tuple, project: str = "") -> list[dict]:
        with self._database() as db:
            if section == "projects":
                rows = db.execute("""SELECT id,name FROM projects
                    WHERE (name COLLATE NOCASE,id)>(?,?)
                    ORDER BY name COLLATE NOCASE,id LIMIT ?""", (*before, PAGE_SIZE + 1))
            elif section == "project":
                rows = db.execute("""SELECT s.*,o.project,o.pinned,s.cid AS cursor_key
                    FROM organization o JOIN summaries s USING(cid)
                    WHERE o.project=? AND o.cid<? ORDER BY o.cid DESC LIMIT ?""",
                                  (project, before[1], PAGE_SIZE + 1))
            elif section == "pinned":
                rows = db.execute("""SELECT s.*,o.project,o.pinned,o.pinned AS cursor_key
                    FROM organization o JOIN summaries s USING(cid)
                    WHERE (o.pinned,o.cid)<(?,?) ORDER BY o.pinned DESC,o.cid DESC LIMIT ?""",
                                  (*before, PAGE_SIZE + 1))
            else:
                rows = db.execute("""SELECT s.*,o.project,o.pinned,s.activity AS cursor_key
                    FROM summaries s LEFT JOIN organization o USING(cid)
                    WHERE (s.activity,s.cid)<(?,?) ORDER BY s.activity DESC,s.cid DESC LIMIT ?""",
                                  (*before, PAGE_SIZE + 1))
            return [dict(row) for row in rows]

    def change_project(self, operation: str, project: str, name: str) -> str:
        with self._database() as db:
            if operation == "create":
                project = uuid.uuid4().hex
                db.execute("INSERT INTO projects VALUES (?,?)", (project, name))
            elif operation == "rename":
                if not db.execute("UPDATE projects SET name=? WHERE id=?", (name, project)).rowcount:
                    raise LookupError("项目不存在")
            elif not db.execute("DELETE FROM projects WHERE id=?", (project,)).rowcount:
                raise LookupError("项目不存在")
            else:
                db.execute("DELETE FROM organization WHERE project IS NULL AND pinned IS NULL")
        return project

    def organize(self, cid: str, field: str, value: str | bool | None) -> None:
        row = self._summary(cid)
        if row is None:
            raise LookupError("会话不存在")
        with self._database() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO summaries VALUES (?,?,?)", row)
            db.execute("INSERT OR IGNORE INTO organization(cid) VALUES (?)", (cid,))
            if field == "project":
                if value is not None and not db.execute(
                        "SELECT 1 FROM projects WHERE id=?", (value,)).fetchone():
                    raise LookupError("项目不存在")
                db.execute("UPDATE organization SET project=? WHERE cid=?", (value, cid))
            elif value:
                db.execute("UPDATE organization SET pinned=COALESCE(pinned,?) WHERE cid=?",
                           (time.time_ns(), cid))
            else:
                db.execute("UPDATE organization SET pinned=NULL WHERE cid=?", (cid,))
            db.execute("DELETE FROM organization WHERE cid=? AND project IS NULL AND pinned IS NULL",
                       (cid,))
