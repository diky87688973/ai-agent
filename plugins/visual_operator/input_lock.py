# -*- coding: utf-8 -*-
"""输入动作串行锁。

鼠标与键盘共用一把进程内锁：两个会话同时操作桌面时，一个拖拽不会被
另一个会话的点击插进来，按下与松开始终成对。
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

from .errors import DesktopBusy

DEFAULT_TIMEOUT = 10.0

_LOCK = threading.Lock()


@contextmanager
def input_guard(timeout: float = DEFAULT_TIMEOUT) -> Iterator[None]:
    """持有输入锁执行一段动作；超时抛 `DesktopBusy`。"""
    if not _LOCK.acquire(timeout=timeout):
        raise DesktopBusy(f"桌面输入被另一个动作占用超过 {timeout:g} 秒")
    try:
        yield
    finally:
        _LOCK.release()
