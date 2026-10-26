# -*- coding: utf-8 -*-
"""API Token：只保存 hash、名称与 scope，支持撤销。"""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from agent.core.error_report import report_error
from agent.mechanisms.session_locking import cross_process_lock
from agent.shell.web.auth.models import ALL_SCOPES, Principal
from agent.shell.web.auth.security import atomic_write_text, ensure_auth_dir, read_text, secure_path

_VALID_SCOPES = set(ALL_SCOPES)


def _hash(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


class TokenStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def _read(self) -> Dict[str, Dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(read_text(self.path))
        except ValueError as exc:
            report_error("agent.shell.web.auth.tokens.parse", exc)
            return {}
        if not isinstance(raw, dict):
            return {}
        return {str(k): v for k, v in raw.items() if isinstance(v, dict)}

    def _write(self, rows: Dict[str, Dict[str, Any]]) -> None:
        atomic_write_text(
            self.path,
            json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        )

    def _secure_lock(self) -> None:
        secure_path(self.path.with_suffix(self.path.suffix + ".lock"))

    def issue(self, name: str, scopes: Iterable[str]) -> str:
        label = str(name or "").strip()
        if not label:
            raise ValueError("token 名称不能为空")
        wanted = {str(item).strip() for item in scopes if str(item).strip()}
        unknown = wanted - _VALID_SCOPES
        if unknown:
            raise ValueError(f"未知 scope：{','.join(sorted(unknown))}")
        token = "ai_" + secrets.token_urlsafe(32)
        ensure_auth_dir(self.path.parent)
        with self._lock:
            with cross_process_lock(self.path) as locked:
                if not locked:
                    raise RuntimeError("跨进程锁不可用，拒绝写入 Token")
                self._secure_lock()
                rows = self._read()
                if label in rows:
                    raise ValueError(f"Token 名称已存在：{label}")
                rows[label] = {
                    "hash": _hash(token),
                    "name": label,
                    "scopes": sorted(wanted or {"read"}),
                    "created_at": int(time.time()),
                }
                self._write(rows)
        return token

    def revoke(self, name: str) -> bool:
        label = str(name or "").strip()
        ensure_auth_dir(self.path.parent)
        with self._lock:
            with cross_process_lock(self.path) as locked:
                if not locked:
                    raise RuntimeError("跨进程锁不可用，拒绝撤销 Token")
                self._secure_lock()
                rows = self._read()
                if label not in rows:
                    return False
                rows.pop(label, None)
                self._write(rows)
        return True

    def verify(self, token: str) -> Optional[Principal]:
        key = _hash(token)
        for name, row in self._read().items():
            if str(row.get("hash") or "") != key:
                continue
            scopes = {str(item) for item in row.get("scopes") or []}
            scopes &= _VALID_SCOPES
            return Principal(subject=str(name), kind="token", scopes=frozenset(scopes))
        return None
