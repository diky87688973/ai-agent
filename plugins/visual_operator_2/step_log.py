# -*- coding: utf-8 -*-
"""视觉操作步骤日志：JSONL，追加写，失败只忽略。"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_lock = threading.Lock()
_path: Path | None = None


def configure(path: Path | None) -> None:
    global _path
    _path = Path(path) if path is not None else None


def write(event: str, **fields: Any) -> None:
    path = _path
    if path is None:
        return
    record = {
        "ts": datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds"),
        "event": str(event or ""),
    }
    for key, value in fields.items():
        if value is None:
            continue
        text = value if isinstance(value, (str, int, float, bool)) else str(value)
        record[str(key)] = str(text)[:4000]
    try:
        with _lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        return
