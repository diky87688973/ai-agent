# -*- coding: utf-8 -*-
"""错误上报门面：core / 机制经此回调，不直接写盘。

装配点（`build_app`）把 `ErrorLog.report` 绑进来；未绑定时退化为 stderr。
"""
from __future__ import annotations

import sys
import threading
from typing import Any, Callable, Optional, Union

_ExcLike = Union[BaseException, str]
ErrorSink = Callable[..., None]

_lock = threading.Lock()
_sink: Optional[ErrorSink] = None


def bind_error_sink(sink: Optional[ErrorSink]) -> Callable[[], None]:
    """绑定进程级 sink；返回幂等 disposer（解绑当前这份）。"""
    global _sink
    with _lock:
        _sink = sink

    def _dispose() -> None:
        global _sink
        with _lock:
            if _sink is sink:
                _sink = None

    return _dispose


def report_error(
    tag: str,
    exc: _ExcLike,
    *,
    conversation_id: str = "",
    **fields: Any,
) -> None:
    """上报错误；sink 抛错时回退 stderr，本函数永不向外抛。"""
    sink: Optional[ErrorSink]
    with _lock:
        sink = _sink
    if callable(sink):
        try:
            sink(tag, exc, conversation_id=conversation_id, **fields)
            return
        except Exception as sink_exc:
            try:
                print(
                    f"[error_report] sink 失败：{type(sink_exc).__name__}: {sink_exc}",
                    file=sys.stderr,
                    flush=True,
                )
            except Exception:
                pass
    # 未装配或 sink 失败：stderr 兜底
    try:
        tag_s = str(tag or "unknown").strip() or "unknown"
        cid = str(conversation_id or "").strip()
        if isinstance(exc, BaseException):
            body = f"{type(exc).__name__}: {exc}"
        else:
            body = str(exc or "")
        prefix = f"[{tag_s}]"
        if cid:
            prefix += f" cid={cid}"
        print(f"{prefix} {body}", file=sys.stderr, flush=True)
    except Exception:
        pass
