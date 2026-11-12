# -*- coding: utf-8 -*-
"""Bounded cache of exact session event snapshots for repeated model turns."""
from __future__ import annotations

import os
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from agent.core.events import Event
from agent.mechanisms.session_lines import event_from_obj, seq_from_obj

_CACHE_BYTES = 128 * 1024 * 1024
_CACHE_SESSIONS = 8


@dataclass(frozen=True)
class _Snapshot:
    identity: tuple[int, int]
    start: int
    end: int
    lines: int
    mtime: int
    signature: bytes
    events: tuple[Event, ...]


class SessionSnapshots:
    def __init__(self) -> None:
        self._entries: OrderedDict[Path, _Snapshot] = OrderedDict()
        self._lock = Lock()

    def load(self, path: Path,
             read: Callable[[int, int, int], tuple[list[Event], int, int]], *, start: int = 0) -> list[Event]:
        try:
            with path.open("rb") as raw:
                stat = os.fstat(raw.fileno())
                identity = (stat.st_dev, stat.st_ino)
                with self._lock:
                    old = self._entries.get(path)
                if old and (old.identity != identity or old.start != start or old.end > stat.st_size
                            or (old.end == stat.st_size and old.mtime != stat.st_mtime_ns)
                            or self._signature(raw, old.end) != old.signature):
                    old = None
                fresh, end, lines = read(old.end if old else start, stat.st_size, old.lines if old else 0)
                events = ((*old.events, *fresh) if fresh else old.events) if old else tuple(fresh)
                signature = self._signature(raw, end)
        except FileNotFoundError:
            with self._lock:
                self._entries.pop(path, None)
            return []
        self._remember(path, _Snapshot(identity, start, end, lines, stat.st_mtime_ns, signature, events))
        return list(events)

    @staticmethod
    def _signature(raw, end: int) -> bytes:
        start = max(0, end - 128)
        raw.seek(start)
        return raw.read(end - start)

    def _remember(self, path: Path, snapshot: _Snapshot) -> None:
        with self._lock:
            self._entries.pop(path, None)
            if snapshot.end - snapshot.start <= _CACHE_BYTES:
                self._entries[path] = snapshot
            while (len(self._entries) > _CACHE_SESSIONS
                   or sum(item.end - item.start for item in self._entries.values()) > _CACHE_BYTES):
                self._entries.popitem(last=False)


def read_turn_delta(path: Path, cid: str, start: int, end: int, lines: int,
                    parse: Callable[[str], Any], observe: Callable[[int], None]) -> tuple[list[Event], int, int]:
    if start == end:
        return [], end, lines
    events = []
    with path.open("rb") as raw:
        raw.seek(start)
        position = start
        while position < end:
            line = raw.readline(end - position)
            if not line.endswith(b"\n"):
                break
            position += len(line)
            if not line.strip():
                continue
            obj = parse(line.decode("utf-8", errors="replace"))
            event = event_from_obj(obj, cid)
            if event is not None:
                seq = seq_from_obj(obj)
                observe(lines if seq is None else seq)
                events.append(event)
            lines += 1
    return events, position, lines
