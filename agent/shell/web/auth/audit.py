# -*- coding: utf-8 -*-
"""鉴权审计日志：只记录事件与来源，不记录密码、Cookie 或 Token。"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from agent.core.error_report import report_error
from agent.shell.web.auth.security import AuthSecurityError, append_line


class AuthAudit:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def write(self, event: str, *, level: str = "info", **fields: Any) -> None:
        row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "event": str(event), "level": str(level)}
        row.update({key: value for key, value in fields.items() if value is not None})
        try:
            with self._lock:
                append_line(self.path, json.dumps(row, ensure_ascii=False) + "\n")
        except (OSError, AuthSecurityError) as exc:
            report_error("agent.shell.web.auth.audit", exc)
