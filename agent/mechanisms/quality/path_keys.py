# -*- coding: utf-8 -*-
"""写目标路径解析：只认调用方传入的参数键序，不维护进程全局键表。"""
from __future__ import annotations

from typing import Any, Dict, Iterable


def norm_path(p: str) -> str:
    """路径规范化：统一斜杠、去首尾空白。"""
    return str(p or "").replace("\\", "/").strip()


def resolve_write_path(args: Dict[str, Any], keys: Iterable[str]) -> str:
    """按键序取首个非空参数作为写目标路径。

    `keys` 为空或不命中时返回空串——不默认猜 `path`。
    键序来自工具声明的 `write_path_keys`（经注册表查找），不经全局旁路表。
    """
    for key in keys:
        name = str(key or "").strip()
        if not name:
            continue
        value = str((args or {}).get(name) or "").strip()
        if value:
            return norm_path(value)
    return ""
