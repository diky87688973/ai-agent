# -*- coding: utf-8 -*-
"""HTTP 鉴权的数据形状与常量。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Optional

COOKIE_NAME = "ai_agent_session"
ALL_SCOPES: FrozenSet[str] = frozenset({"read", "chat", "write", "admin"})


@dataclass(frozen=True)
class Principal:
    """一次请求已经确认的身份；不包含密码或 token 明文。"""

    subject: str
    kind: str
    scopes: FrozenSet[str]


@dataclass(frozen=True)
class Session:
    """服务端会话记录；token 只保存在客户端 Cookie。"""

    token_hash: str
    csrf: str
    expires_at: float


@dataclass(frozen=True)
class AuthIdentity:
    """请求认证结果：Principal 与可选的会话。"""

    principal: Principal
    session: Optional[Session] = None
    api_token: bool = False


@dataclass(frozen=True)
class AuthDecision:
    allowed: bool
    status: int = 200
    error: str = ""
