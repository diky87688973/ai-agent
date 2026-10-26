# -*- coding: utf-8 -*-
"""进程内会话：Cookie 只保存随机 token，服务端只保存 hash。"""
from __future__ import annotations

import hashlib
import secrets
import threading
import time
from typing import Dict, Optional, Tuple

from agent.shell.web.auth.models import Session


def _hash(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


class LoginSessionStore:
    def __init__(self, ttl_seconds: int = 12 * 3600, max_sessions: int = 128) -> None:
        self._ttl = max(1, int(ttl_seconds))
        self._max = max(1, int(max_sessions))
        self._lock = threading.Lock()
        self._items: Dict[str, Session] = {}

    def create(self) -> Tuple[str, Session]:
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        record = Session(
            token_hash=_hash(token),
            csrf=csrf,
            expires_at=time.time() + self._ttl,
        )
        with self._lock:
            self._prune_locked()
            if len(self._items) >= self._max:
                oldest = min(self._items.items(), key=lambda item: item[1].expires_at)[0]
                self._items.pop(oldest, None)
            self._items[record.token_hash] = record
        return token, record

    def get(self, token: str) -> Optional[Session]:
        if not token:
            return None
        key = _hash(token)
        with self._lock:
            record = self._items.get(key)
            if record is None:
                return None
            if record.expires_at <= time.time():
                self._items.pop(key, None)
                return None
            refreshed = Session(
                token_hash=record.token_hash,
                csrf=record.csrf,
                expires_at=time.time() + self._ttl,
            )
            self._items[key] = refreshed
            return refreshed

    def revoke(self, token: str) -> None:
        if not token:
            return
        with self._lock:
            self._items.pop(_hash(token), None)

    def _prune_locked(self) -> None:
        now = time.time()
        expired = [key for key, value in self._items.items() if value.expires_at <= now]
        for key in expired:
            self._items.pop(key, None)
