# -*- coding: utf-8 -*-
"""按平台选择后端。

平台模块按需导入：Linux 上没有 `ctypes.WinDLL`，Windows 上没有 Quartz。
装配失败（缺系统库等）退到不可用后端，只留一条诊断 —— 工具仍注册，
执行时才报出准确原因。
"""
from __future__ import annotations

import sys

from ..ports import Backend
from ._unavailable import unavailable_backend


def load_backend() -> Backend:
    try:
        if sys.platform == "win32":
            from .win32 import Win32Backend
            return Win32Backend()
        if sys.platform == "darwin":
            from .macos import MacOSBackend
            return MacOSBackend()
    except Exception as exc:  # 降级到不可用后端：注册面不随系统库缺失而漂移
        print(
            f"[plugin:desktop_io] 后端装配失败：{type(exc).__name__}: {exc}",
            file=sys.stderr,
            flush=True,
        )
    return unavailable_backend()
