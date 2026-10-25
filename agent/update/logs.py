# -*- coding: utf-8 -*-
"""更新链路日志：检查、下载、校验、切换、恢复。"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

from agent.core.error_report import report_error

LOG_NAME = "updates/update.log"
MAX_BYTES = 1024 * 1024


def log_event(root: Path, event: str, *, level: str = "info", **fields: Any) -> None:
    path = Path(root) / LOG_NAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file() and path.stat().st_size > MAX_BYTES:
            backup = path.with_suffix(".log.1")
            path.replace(backup)
        row: Dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "event": str(event),
            "level": str(level),
        }
        row.update({key: value for key, value in fields.items() if value is not None})
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:
        report_error("agent.update.logs.write", exc)


def tail(root: Path, limit: int = 100) -> List[Dict[str, Any]]:
    path = Path(root) / LOG_NAME
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        report_error("agent.update.logs.read", exc)
        return []
    rows: List[Dict[str, Any]] = []
    for line in lines[-max(1, min(int(limit), 500)):]:
        try:
            rows.append(json.loads(line))
        except ValueError as exc:
            report_error("agent.update.logs.parse", exc)
            rows.append({"level": "error", "event": "log_parse_error", "error": str(exc)})
    return rows
