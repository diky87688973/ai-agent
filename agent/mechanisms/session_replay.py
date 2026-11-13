"""Bounded reads of indexed session facts for history and SSE."""
from __future__ import annotations

import heapq
from itertools import islice
from pathlib import Path
from typing import Iterable, List, Tuple

from agent.core.events import Event
from agent.mechanisms.session_lines import event_from_obj


class SessionReplay:
    """Index-backed read methods for the session store."""

    def history_window(self, conversation_id: str, before: int | None = None,
                       rounds: int = 16) -> tuple[list[tuple[int, Event]], bool]:
        path = self.raw_path(conversation_id)
        rows, older = self._indexes.current(path).history(before, rounds)
        return list(self._read_replay(path, rows)), older

    def history_slice(self, conversation_id: str, before: int | None = None):
        path = self.raw_path(conversation_id)
        rows, cursor, skipped = self._indexes.current(path).history_slice(before)
        return list(self._read_replay(path, rows)), cursor, skipped

    def _read_replay(self, path: Path, rows: Iterable[tuple[int, int, int]]):
        rows = list(rows)
        if not rows:
            return
        with path.open("rb") as raw:
            for seq, pos, size in rows:
                raw.seek(pos)
                obj = self._parse_obj(raw.read(size).decode("utf-8", errors="replace"))
                event = event_from_obj(obj, path.stem)
                if event is not None:
                    self._observe(seq)
                    yield seq, event

    def tail_from(self, conversation_id: str, after_seq: int) -> List[Tuple[int, Event]]:
        """Read a bounded batch of this session's events after the cursor."""
        path = self.raw_path(conversation_id)
        rows = self._indexes.current(path).replay(int(after_seq), 512, frozenset())
        return list(self._read_replay(path, rows))

    def tail_across(self, after_seq: int, limit: int = 512, *,
                    exclude_types: frozenset[str] = frozenset()) -> List[Tuple[int, str, Event]]:
        """Merge indexed positions before reading the bounded replay payload."""
        count = max(1, min(int(limit), 4096))
        batches = []
        for path in self._raw_files():
            rows = self._indexes.current(path).replay(int(after_seq), count, exclude_types)
            batches.append([(seq, str(path), pos, size) for seq, pos, size in rows])
        result = []
        for seq, path_text, pos, size in islice(heapq.merge(*batches), count):
            path = Path(path_text)
            result.extend((s, path.stem, event) for s, event in self._read_replay(path, [(seq, pos, size)]))
        return result
