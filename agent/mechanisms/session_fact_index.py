# -*- coding: utf-8 -*-
"""Offset index for targeted lookups in an append-only session log.

The raw log remains authoritative. The index contains offsets and identifiers,
never message bodies. Each transaction publishes its rows with the raw offset
they cover, so recovery only parses the suffix written since the last commit.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from typing import Any, Callable

from agent.core.error_report import report_error
from agent.core.events import Event
from agent.core.input_attachments import attachment_id
from agent.core.session_log import SessionLog
from agent.mechanisms.session_lines import (
    KEY_DATA,
    KEY_TYPE,
    event_from_obj,
    event_seq,
    seq_from_obj,
)

_READ_BUDGET = 4 * 1024 * 1024
_SCHEMA = """
CREATE TABLE IF NOT EXISTS cursor (
    id INTEGER PRIMARY KEY CHECK(id=1), pos INTEGER, dev INTEGER, ino INTEGER,
    mtime INTEGER, signature BLOB, lines INTEGER
);
CREATE TABLE IF NOT EXISTS facts (
    pos INTEGER PRIMARY KEY, size INTEGER, seq INTEGER, kind TEXT, call BLOB, item BLOB
);
CREATE INDEX IF NOT EXISTS facts_seq ON facts(seq);
CREATE INDEX IF NOT EXISTS facts_kind ON facts(kind, pos);
CREATE INDEX IF NOT EXISTS facts_call ON facts(call, pos);
CREATE INDEX IF NOT EXISTS facts_item ON facts(item);
CREATE TABLE IF NOT EXISTS attachments (id BLOB, pos INTEGER, PRIMARY KEY(id,pos));
CREATE TABLE IF NOT EXISTS image_reads (id BLOB, pos INTEGER, PRIMARY KEY(id,pos));
CREATE TABLE IF NOT EXISTS title_material (kind TEXT, pos INTEGER, PRIMARY KEY(kind,pos));
CREATE TABLE IF NOT EXISTS model_checkpoints (seq INTEGER PRIMARY KEY, anchor INTEGER);
"""


class FactIndexPending(OSError):
    """The persisted index has yet to catch up with the raw log."""


class HistoryWindowTooLarge(OSError):
    """The newest round exceeds the history read budget."""


def _key(value: Any) -> bytes | None:
    return hashlib.sha256(str(value).encode("utf-8")).digest() if value else None


def _signature(raw: Any, pos: int) -> bytes:
    start = max(0, pos - 128)
    raw.seek(start)
    return hashlib.sha256(raw.read(pos - start)).digest()


class FactIndex:
    def __init__(self, path: Path, parse: Callable[[str], Any]) -> None:
        self.path = path
        self.index_path = path.with_suffix(".facts.sqlite3")
        self._parse = parse

    def _connect(self):
        db = sqlite3.connect(self.index_path, timeout=0.15)
        try:
            db.executescript(_SCHEMA)
            return db
        except Exception:
            db.close()
            raise

    def advance(self, *, background: bool = False) -> bool:
        """Index at most one chunk. The caller retries incomplete work separately."""
        try:
            with self.path.open("rb") as raw:
                stat = os.fstat(raw.fileno())
                with closing(self._connect()) as db, db:
                    db.execute("BEGIN IMMEDIATE")
                    saved = db.execute("SELECT pos,dev,ino,mtime,signature,lines FROM cursor").fetchone()
                    pos = self._resume(db, raw, stat, saved)
                    if saved is not None and pos == saved[0] == stat.st_size and stat.st_mtime_ns == saved[3]:
                        return True
                    lines = saved[5] if saved and pos else 0
                    rows, end, complete, lines = self._read_chunk(raw, pos, stat.st_size, background, lines)
                    self._insert_rows(db, rows)
                    db.execute("INSERT OR REPLACE INTO cursor VALUES (1,?,?,?,?,?,?)", (
                        end, f"d{stat.st_dev}", f"i{stat.st_ino}", stat.st_mtime_ns, _signature(raw, end), lines,
                    ))
                    # A partial final line will be retried after the next append.
                    return complete
        except FileNotFoundError:
            if self.index_path.is_file():
                with closing(self._connect()) as db, db:
                    self._reset(db)
                    db.execute("DELETE FROM cursor")
            return True
        except sqlite3.Error as exc:
            raise OSError("会话事实索引暂不可用") from exc

    def _resume(self, db: Any, raw: Any, stat: Any, saved: Any) -> int:
        if saved:
            pos, dev, ino, mtime, signature, _ = saved
            if ((dev, ino) == (f"d{stat.st_dev}", f"i{stat.st_ino}") and pos <= stat.st_size
                    and (pos < stat.st_size or mtime == stat.st_mtime_ns)
                    and _signature(raw, pos) == signature):
                return pos
            self._reset(db)
        return 0

    @staticmethod
    def _reset(db: Any) -> None:
        for table in ("facts", "attachments", "image_reads", "title_material", "model_checkpoints"):
            db.execute(f"DELETE FROM {table}")

    @staticmethod
    def _insert_rows(db: Any, rows: list) -> None:
        db.executemany("INSERT INTO facts VALUES (?,?,?,?,?,?)", (row[:6] for row in rows))
        db.executemany("INSERT OR IGNORE INTO attachments VALUES (?,?)",
                       ((ident, row[0]) for row in rows for ident in row[6]))
        db.executemany("INSERT OR IGNORE INTO image_reads VALUES (?,?)",
                       ((row[7], row[0]) for row in rows if row[7] is not None))
        db.executemany("INSERT INTO title_material VALUES (?,?)",
                       ((row[3], row[0]) for row in rows if row[8]))

    @staticmethod
    def _title_material(kind: str, data: dict) -> bool:
        content = data.get("content")
        return (isinstance(content, str) and bool(content.strip())
                and (kind == "model_message"
                     or kind == "input_claimed" and not content.lstrip().startswith("<<系统通知>>")))

    @staticmethod
    def _image_keys(kind: str, data: dict) -> tuple[list, bytes | None]:
        if kind == "input_claimed":
            return ([_key(row.get("attachment_id") or attachment_id(row["data_base64"], index))
                     for index, row in enumerate(data.get("attachments") or [])
                     if isinstance(row, dict) and isinstance(row.get("data_base64"), str)
                     and row["data_base64"]], None)
        payload = data.get("data")
        if kind == "tool_done" and data.get("name") == "read_image" and isinstance(payload, dict):
            return [], _key(payload.get("attachment_id"))
        return [], None

    def _read_chunk(self, raw: Any, pos: int, size: int, background: bool,
                    lines: int) -> tuple[list, int, bool, int]:
        raw.seek(pos)
        rows = []
        end = pos
        while end < size and end - pos < _READ_BUDGET:
            remaining = size - end
            allowance = min(remaining, _READ_BUDGET - (end - pos))
            if background and end == pos:
                allowance = remaining
            line = raw.readline(allowance)
            if not line.endswith(b"\n"):
                return rows, end, raw.tell() == size, lines
            row = self._metadata(line, end, lines)
            lines += bool(line.strip())
            if row is not None:
                rows.append(row)
            end += len(line)
        return rows, end, end == size, lines

    def _metadata(self, line: bytes, offset: int, number: int) -> tuple | None:
        obj = self._parse(line.decode("utf-8", errors="replace"))
        if not isinstance(obj, dict) or not obj.get(KEY_TYPE):
            return None
        data = obj.get(KEY_DATA)
        data = data if isinstance(data, dict) else {}
        seq = seq_from_obj(obj)
        kind = str(obj[KEY_TYPE])
        return (offset, len(line), number if seq is None else seq, kind,
                _key(data.get("call_id")), _key(data.get("_queue_item_id")),
                *self._image_keys(kind, data), self._title_material(kind, data))

    def read(self, positions: list[tuple[int, int]]) -> list[Event]:
        if not positions:
            return []
        events = []
        with self.path.open("rb") as raw:
            for pos, size in positions:
                raw.seek(pos)
                obj = self._parse(raw.read(size).decode("utf-8", errors="replace"))
                event = event_from_obj(obj, self.path.stem)
                if event is not None:
                    events.append(event)
        return events

    def lookup(self, *, kind: str = "", items: tuple[str, ...] = (),
               call_id: str = "", recent: bool = False, limit: int = 0,
               pending: bool = False, confirmation: bool = False, first: bool = False,
               resumable: bool = False, before_seq: int | None = None) -> list[tuple[int, int]]:
        if not self.index_path.is_file():
            return []
        where, args = [], []
        if kind:
            where.append("kind=?")
            args.append(kind)
        if before_seq is not None:
            where.append("seq<?")
            args.append(before_seq)
        if items:
            where.append("item IN (" + ",".join("?" for _ in items) + ")")
            args.extend(_key(item) for item in items)
        if call_id:
            where.append("call=?")
            args.append(_key(call_id))
        if recent or pending:
            where.append("pos >= COALESCE((SELECT MAX(pos) FROM facts WHERE kind='input_claimed'),0)")
        if recent or confirmation:
            where.append("kind IN ('tool_suspended','tool_done','tool_failed')")
        if resumable:
            where.extend((
                "kind IN ('tool_done','tool_failed')",
                "pos > COALESCE((SELECT MAX(pos) FROM facts "
                "WHERE kind IN ('turn_started','tool_suspended')), -1)",
            ))
            limit = 1
        if pending:
            where.extend((
                "kind='tool_suspended'",
                "NOT EXISTS (SELECT 1 FROM facts AS terminal WHERE terminal.call=facts.call "
                "AND terminal.pos>facts.pos AND terminal.kind IN ('tool_done','tool_failed'))",
            ))
            limit = 1
        clause = " WHERE " + " AND ".join(where) if where else ""
        order = " ORDER BY pos" if first or not limit else " ORDER BY pos DESC"
        if limit:
            order += " LIMIT ?"
            args.append(limit)
        with closing(self._connect()) as db:
            return db.execute("SELECT pos,size FROM facts" + clause + order, args).fetchall()

    def known_sequences(self, sequences: set[int]) -> set[int]:
        if not sequences or not self.index_path.is_file():
            return set()
        with closing(self._connect()) as db:
            return {seq for seq in sequences
                    if db.execute("SELECT 1 FROM facts WHERE seq=? LIMIT 1", (seq,)).fetchone()}

    def cursor(self) -> tuple[int, int]:
        """Return indexed maximum sequence and nonblank line count."""
        if not self.index_path.is_file():
            return -1, 0
        with closing(self._connect()) as db:
            saved = db.execute("SELECT lines FROM cursor").fetchone()
            highest = db.execute("SELECT MAX(seq) FROM facts").fetchone()[0]
        return (-1 if highest is None else highest, saved[0] if saved else 0)

    def replay(self, after: int, limit: int, exclude: frozenset[str]) -> list[tuple[int, int, int]]:
        if not self.index_path.is_file():
            return []
        sql = "SELECT seq,pos,size FROM facts WHERE seq>?"
        args: list[Any] = [after]
        if exclude:
            sql += " AND kind NOT IN (" + ",".join("?" for _ in exclude) + ")"
            args.extend(exclude)
        with closing(self._connect()) as db:
            return db.execute(sql + " ORDER BY seq,pos LIMIT ?", [*args, limit]).fetchall()

    def record_append(self, offset: int, lines: list[str], events: list) -> None:
        """Publish offsets for the just-written batch without re-reading its bodies."""
        with self.path.open("rb") as raw, closing(self._connect()) as db, db:
            stat = os.fstat(raw.fileno())
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute("SELECT pos,lines FROM cursor").fetchone()
            if (cursor[0] if cursor else 0) != offset:
                return
            rows = []
            end = offset
            for line, event in zip(lines, events, strict=True):
                size = len(line.encode("utf-8")) + 1
                rows.append((end, size, event_seq(event), event.type,
                             _key(event.data.get("call_id")), _key(event.data.get("_queue_item_id")),
                             *self._image_keys(event.type, event.data), self._title_material(event.type, event.data)))
                end += size
            if end != stat.st_size:
                return
            self._insert_rows(db, rows)
            db.execute("INSERT OR REPLACE INTO cursor VALUES (1,?,?,?,?,?,?)", (
                end, f"d{stat.st_dev}", f"i{stat.st_ino}", stat.st_mtime_ns, _signature(raw, end),
                (cursor[1] if cursor else 0) + len(rows),
            ))

    def history(self, before: int | None, rounds: int) -> tuple[list[tuple[int, int, int]], bool]:
        """Select complete recent rounds, bounded by row count and encoded bytes."""
        if not self.index_path.is_file():
            return [], False
        with closing(self._connect()) as db:
            end = None
            first_turn = db.execute(
                "SELECT MIN(pos) FROM facts WHERE kind='turn_started'",
            ).fetchone()[0]
            legacy_end = first_turn if first_turn is not None else 2**63 - 1
            if before is not None:
                end = db.execute(
                    """SELECT MIN(pos) FROM facts WHERE seq=?
                    AND (kind='turn_started' OR (kind='input_claimed' AND pos<?))""",
                    (before, legacy_end),
                ).fetchone()[0]
            if before is not None and end is None:
                return [], False
            end = end if end is not None else 2**63 - 1
            anchors = db.execute(
                """SELECT pos FROM facts WHERE kind='turn_started' AND pos<?
                    ORDER BY pos DESC LIMIT ?""", (end, rounds + 1),
            ).fetchall()
            if len(anchors) < rounds + 1:
                anchors += db.execute(
                    """SELECT pos FROM facts WHERE kind='input_claimed' AND pos<?
                        ORDER BY pos DESC LIMIT ?""",
                    (min(legacy_end, end), rounds + 1 - len(anchors)),
                ).fetchall()
            start = anchors[rounds - 1][0] if len(anchors) > rounds else 0
            rows = db.execute(
                "SELECT seq,pos,size FROM facts WHERE pos>=? AND pos<? ORDER BY pos DESC LIMIT 8193",
                (start, end),
            ).fetchall()
            kept, more = self._fit_history(rows, anchors)
        return list(reversed(kept)), bool(start or more)

    def history_slice(self, before: int | None) -> tuple[list[tuple[int, int, int]], int | None, int]:
        """Read a bounded slice when one host turn exceeds the normal page budget."""
        if not self.index_path.is_file():
            return [], None, 0
        with closing(self._connect()) as db:
            end = 2**63 - 1
            if before is not None:
                boundary = db.execute("SELECT pos FROM facts WHERE seq=?", (before,)).fetchone()
                if boundary is None:
                    return [], None, 0
                end = boundary[0]
            rows = db.execute(
                """SELECT seq,pos,size,kind FROM facts WHERE pos<?
                    ORDER BY pos DESC LIMIT 2049""", (end,),
            ).fetchall()
            selected = []
            size = skipped = 0
            next_before = None
            for index, (seq, pos, length, kind) in enumerate(rows):
                if index == 2048 or (selected and length <= 4 * 1024 * 1024
                                     and size + length > 4 * 1024 * 1024):
                    next_before = rows[index - 1][0]
                    break
                if length > 4 * 1024 * 1024:
                    skipped += 1
                else:
                    size += length
                    selected.append((seq, pos, length))
                if kind in ("turn_started", "input_claimed") and size >= 64 * 1024:
                    next_before = seq if index + 1 < len(rows) else None
                    break
        return list(reversed(selected)), next_before, skipped

    @staticmethod
    def _fit_history(rows: list, anchors: list) -> tuple[list, bool]:
        size = 0
        for index, (_, _, length) in enumerate(rows):
            size += length
            if index >= 8192 or size > 16 * 1024 * 1024:
                allowed = {pos for _, pos, _ in rows[:index]}
                start = min((pos for (pos,) in anchors if pos in allowed), default=None)
                if start is None:
                    raise HistoryWindowTooLarge("最新一轮历史超过读取上限")
                return [row for row in rows[:index] if row[1] >= start], True
        return rows, False

    def image_facts(self, ident: str) -> tuple[list[tuple[int, int]], bool]:
        if not self.index_path.is_file():
            return [], False
        key = _key(ident)
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT f.pos,f.size FROM attachments a JOIN facts f ON f.pos=a.pos "
                "WHERE a.id=? ORDER BY a.pos LIMIT 1", (key,),
            ).fetchall()
            already = db.execute(
                "SELECT 1 FROM image_reads WHERE id=? AND pos>=COALESCE("
                "(SELECT MAX(pos) FROM facts WHERE kind='turn_started'),0) LIMIT 1", (key,),
            ).fetchone()
        return rows, already is not None

    def model_checkpoint(self) -> tuple[int, int]:
        """Return a proven input boundary and the number of covered messages."""
        checkpoints = self.read(self.lookup(kind="context_compacted", limit=1))
        if not checkpoints:
            return 0, 0
        data = checkpoints[0].data
        covered = data.get("covered_end")
        if not isinstance(covered, int) or covered <= 0 or not data.get("summary"):
            return 0, 0
        with closing(self._connect()) as db:
            anchor = data.get("history_anchor_seq")
            if anchor is None:
                saved = db.execute("SELECT anchor FROM model_checkpoints WHERE seq=?",
                                   (data.get("_seq"),)).fetchone()
                anchor = saved[0] if saved else None
            if not isinstance(anchor, int):
                return 0, 0
            row = db.execute(
                "SELECT pos FROM facts WHERE seq=? AND kind='input_claimed' LIMIT 1", (anchor,),
            ).fetchone()
        return (row[0], covered) if row is not None else (0, 0)

    def remember_legacy_checkpoint(self, events: list[Event]) -> None:
        """Derive the anchor once from a legacy snapshot already loaded by the caller."""
        checkpoint = next((event for event in reversed(events) if event.type == "context_compacted"), None)
        if checkpoint is None:
            return
        covered = checkpoint.data.get("covered_end")
        seq = checkpoint.data.get("_seq")
        if not isinstance(covered, int) or covered <= 0 or not isinstance(seq, int) or not checkpoint.data.get("summary"):
            return
        with closing(self._connect()) as db, db:
            if db.execute("SELECT 1 FROM model_checkpoints WHERE seq=?", (seq,)).fetchone():
                return
            log = SessionLog(events=events).readonly()
            dialogue = log.derive_request_messages()
            anchor = None
            if covered < len(dialogue) and dialogue[covered].get("role") == "user":
                anchor = log.user_input_sequence(sum(row.get("role") == "user" for row in dialogue[:covered]))
            db.execute("INSERT OR IGNORE INTO model_checkpoints VALUES (?,?)", (seq, anchor))

    def title(self) -> list[tuple[int, int]]:
        if not self.index_path.is_file():
            return []
        with closing(self._connect()) as db:
            user = db.execute(
                "SELECT pos FROM title_material WHERE kind='input_claimed' ORDER BY pos LIMIT 1",
            ).fetchone()
            if user is None:
                return []
            assistant = db.execute(
                "SELECT pos FROM title_material WHERE kind='model_message' AND pos>? ORDER BY pos LIMIT 1",
                user,
            ).fetchone()
            return db.execute("SELECT pos,size FROM facts WHERE pos IN (?,?) ORDER BY pos",
                              (user[0], assistant[0] if assistant else -1)).fetchall()


class FactIndexes:
    """Bounded request catch-up and one background worker per store."""

    def __init__(self, parse: Callable[[str], Any]) -> None:
        self._parse = parse
        self._lock = threading.Lock()
        self._jobs: set[Path] = set()
        self._worker: threading.Thread | None = None

    def current(self, path: Path) -> FactIndex:
        index = FactIndex(path, self._parse)
        if index.advance():
            return index
        self.prepare([path])
        raise FactIndexPending("会话事实索引正在补建，请稍后重试")

    def prepare(self, paths) -> None:
        with self._lock:
            self._jobs.update(paths)
            if self._jobs and self._worker is None:
                self._worker = threading.Thread(target=self._catch_up, daemon=True)
                self._worker.start()

    def _catch_up(self) -> None:
        while True:
            with self._lock:
                if not self._jobs:
                    self._worker = None
                    return
                path = self._jobs.pop()
            try:
                complete = FactIndex(path, self._parse).advance(background=True)
            except OSError as exc:
                report_error("session_store.index", exc)
                continue
            if not complete:
                with self._lock:
                    self._jobs.add(path)
