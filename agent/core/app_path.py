# -*- coding: utf-8 -*-
"""插口树路径的唯一根与拼接。"""
from __future__ import annotations

from typing import Any

APP_ROOT = "app"


def app_path(*segments: Any) -> str:
    """按段拼出插口树路径；空段跳过，首尾斜杠归一。"""
    parts = [APP_ROOT]
    for segment in segments:
        text = str(segment or "").strip("/")
        if text:
            parts.append(text)
    return "/".join(parts)


__all__ = ["APP_ROOT", "app_path"]
