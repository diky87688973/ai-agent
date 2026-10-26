# -*- coding: utf-8 -*-
"""GUI 桌面会话一次性引导令牌；只保存进程内状态。"""
from __future__ import annotations

import hmac
import os
import threading


class DesktopBootstrap:
    def __init__(self, token: str = "") -> None:
        self._token = str(token or "")
        self._used = False
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls, enabled: bool) -> "DesktopBootstrap":
        token = ""
        if enabled and os.environ.get("AI_AGENT_GUI") == "1":
            token = str(os.environ.get("AI_AGENT_GUI_BOOTSTRAP") or "")
        return cls(token)

    def consume(self, token: str) -> bool:
        if not token or not self._token:
            return False
        with self._lock:
            if self._used:
                return False
            if not hmac.compare_digest(self._token, str(token)):
                return False
            self._used = True
            return True
