# -*- coding: utf-8 -*-
"""线程启动时的执行上下文传播。"""
from __future__ import annotations

import contextvars
import threading
from typing import Any, Callable, Optional, Sequence


def thread_with_context(
    *,
    target: Callable[..., Any],
    name: Optional[str] = None,
    args: Sequence[Any] = (),
    kwargs: Optional[dict[str, Any]] = None,
    daemon: Optional[bool] = None,
) -> threading.Thread:
    """创建继承当前 ContextVar 的线程；调用方自行 start。"""
    context = contextvars.copy_context()
    payload = dict(kwargs or {})

    def run() -> None:
        context.run(target, *args, **payload)

    return threading.Thread(target=run, name=name, daemon=daemon)


__all__ = ["thread_with_context"]
