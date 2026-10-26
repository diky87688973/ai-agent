# -*- coding: utf-8 -*-
"""鉴权路由策略：唯一决定公开路径与所需 scope。"""
from __future__ import annotations

from typing import FrozenSet, Optional

PUBLIC_GET = frozenset({"/login", "/desktop-login", "/healthz", "/auth/status"})
PUBLIC_POST = frozenset({"/auth/login", "/auth/desktop"})
ADMIN_PREFIXES = ("/api/settings", "/api/update", "/api/plugin/")
ADMIN_PATHS = frozenset({
    "/api/chat/user-confirm",
    "/api/chat/command-input",
})
WRITE_PREFIXES = ("/api/chat/",)
READ_SCOPE = "read"
WRITE_SCOPE = "write"
ADMIN_SCOPE = "admin"
PLUGIN_ASSET_SEGMENT = "/_asset/"


def is_public(method: str, path: str) -> bool:
    if method == "GET":
        return path in PUBLIC_GET
    if method == "POST":
        return path in PUBLIC_POST
    return False


def required_scope(method: str, path: str) -> Optional[str]:
    """返回 None 表示无需登录；否则返回所需 scope。"""
    if is_public(method, path):
        return None
    if (method in ("GET", "HEAD") and path.startswith("/api/plugin/")
            and PLUGIN_ASSET_SEGMENT in path):
        return READ_SCOPE
    if path in ADMIN_PATHS or any(path.startswith(item) for item in ADMIN_PREFIXES):
        return ADMIN_SCOPE
    if method in ("POST", "PUT", "PATCH", "DELETE"):
        if any(path.startswith(item) for item in WRITE_PREFIXES):
            return "chat"
        return WRITE_SCOPE
    return READ_SCOPE


def allows(principal_scopes: FrozenSet[str], scope: Optional[str]) -> bool:
    if scope is None:
        return True
    return "admin" in principal_scopes or scope in principal_scopes
