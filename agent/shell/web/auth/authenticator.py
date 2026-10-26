# -*- coding: utf-8 -*-
"""请求认证：Cookie 会话、Bearer Token、可选外部 Provider。"""
from __future__ import annotations

import ipaddress
from http.cookies import SimpleCookie
from typing import Any, Iterable, Optional

from agent.core.error_report import report_error
from agent.shell.web.auth.models import ALL_SCOPES, COOKIE_NAME, AuthIdentity, Principal
from agent.shell.web.auth.sessions import LoginSessionStore
from agent.shell.web.auth.tokens import TokenStore


def is_loopback(remote_ip: str) -> bool:
    try:
        return ipaddress.ip_address(str(remote_ip)).is_loopback
    except ValueError:
        return False


def cookie_token(headers: Any, name: str = COOKIE_NAME) -> str:
    raw = str(headers.get("Cookie") or "")
    if not raw:
        return ""
    try:
        jar = SimpleCookie()
        jar.load(raw)
        morsel = jar.get(name)
        return str(morsel.value) if morsel is not None else ""
    except Exception as exc:
        report_error("agent.shell.web.auth.authenticator.cookie", exc)
        return ""


class Authenticator:
    def __init__(
        self,
        sessions: LoginSessionStore,
        tokens: TokenStore,
        *,
        local_bypass: bool = False,
        providers: Optional[Iterable[Any]] = None,
    ) -> None:
        self.sessions = sessions
        self.tokens = tokens
        self.local_bypass = bool(local_bypass)
        self.providers = list(providers or [])

    def authenticate(self, headers: Any, remote_ip: str) -> Optional[AuthIdentity]:
        if self.local_bypass and is_loopback(remote_ip):
            return AuthIdentity(
                principal=Principal(subject="local", kind="local", scopes=ALL_SCOPES),
            )
        for provider in self.providers:
            try:
                principal = provider.authenticate(headers, remote_ip)
            except Exception as exc:
                report_error("agent.shell.web.auth.authenticator.provider", exc)
                continue
            if principal is not None:
                return AuthIdentity(principal=principal, api_token=True)
        auth = str(headers.get("Authorization") or "").strip()
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
            principal = self.tokens.verify(token) if token else None
            return AuthIdentity(principal=principal, api_token=True) if principal else None
        cookie = cookie_token(headers)
        session = self.sessions.get(cookie) if cookie else None
        if session is None:
            return None
        return AuthIdentity(
            principal=Principal(subject="owner", kind="session", scopes=ALL_SCOPES),
            session=session,
        )
