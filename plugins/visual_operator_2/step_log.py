# -*- coding: utf-8 -*-
"""视觉操作步骤日志：JSONL，追加写，失败只忽略。"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.core.error_report import report_error

_lock = threading.Lock()
_path: Path | None = None
_MAX_FILE_BYTES = 2 * 1024 * 1024


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
            if path.is_file() and path.stat().st_size >= _MAX_FILE_BYTES:
                backup = path.with_name(path.name + ".1")
                if backup.exists():
                    backup.unlink()
                path.rename(backup)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        report_error(
            "plugins.visual_operator_2.step_log", exc,
            path=str(path), event=str(event or ""))
