# -*- coding: utf-8 -*-
"""stderr 兜底：日志系统自身失败时使用。"""
from __future__ import annotations

import os


def write_stderr(message: str) -> None:
    """写一行到 stderr；写失败时放弃，不向外抛异常。"""
    try:
        os.write(2, (message + "\n").encode("utf-8", "replace"))
    except OSError:
        return
