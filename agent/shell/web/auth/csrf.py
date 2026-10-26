# -*- coding: utf-8 -*-
"""CSRF：只对 Cookie 会话的写请求校验会话绑定的 token。"""
from __future__ import annotations

import hmac
from typing import Optional

from agent.shell.web.auth.models import Session

CSRF_HEADER = "X-CSRF-Token"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def required(method: str, session: Optional[Session]) -> bool:
    return session is not None and method.upper() in UNSAFE_METHODS


def verify(session: Optional[Session], token: str) -> bool:
    if session is None:
        return True
    return hmac.compare_digest(str(session.csrf), str(token or ""))
