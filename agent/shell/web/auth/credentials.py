# -*- coding: utf-8 -*-
"""密码凭据文件：唯一权威是 data/auth/credentials.json。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from agent.core.error_report import report_error
from agent.shell.web.auth.password import hash_password
from agent.shell.web.auth.security import atomic_write_text, read_text


class CredentialStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def exists(self) -> bool:
        return self.path.is_file()

    def read(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(read_text(self.path))
        except ValueError as exc:
            report_error("agent.shell.web.auth.credentials.parse", exc)
            return {}
        return value if isinstance(value, dict) else {}

    def set_password(self, password: str) -> None:
        record = {
            "version": 1,
            "password": hash_password(password),
        }
        atomic_write_text(
            self.path,
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        )

    def password_record(self) -> Optional[Dict[str, Any]]:
        record = self.read().get("password")
        return record if isinstance(record, dict) else None
