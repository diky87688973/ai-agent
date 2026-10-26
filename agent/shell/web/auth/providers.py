# -*- coding: utf-8 -*-
"""认证方式扩展点：Provider 只负责把外部身份翻译成 Principal。"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Optional, Protocol

from agent.core.error_report import report_error
from agent.shell.web.auth.models import Principal


class AuthProvider(Protocol):
    name: str

    def authenticate(self, headers: Any, remote_ip: str) -> Optional[Principal]:
        ...


def load_provider(module_path: str, data_root: Path, config: Any) -> Optional[AuthProvider]:
    """按配置加载 provider 模块。

    模块必须提供 build_provider(data_root, config) -> AuthProvider。
    加载失败返回 None，由 Runtime 决定是否拒绝公开启动。
    """
    name = str(module_path or "").strip()
    if not name:
        return None
    try:
        module = importlib.import_module(name)
        build = getattr(module, "build_provider", None)
        provider = build(Path(data_root), config) if callable(build) else None
        if provider is None or not callable(getattr(provider, "authenticate", None)):
            return None
        return provider
    except Exception as exc:
        report_error("agent.shell.web.auth.providers.load", exc)
        return None
