# -*- coding: utf-8 -*-
"""HTTP 鉴权（壳层）：密码、会话、Token、策略与登录页。"""
from __future__ import annotations

import importlib
from typing import Any

__all__ = ["AuthRuntime"]


def __getattr__(name: str) -> Any:
    if name == "AuthRuntime":
        return importlib.import_module("agent.shell.web.auth.runtime").AuthRuntime
    raise AttributeError(name)
