# -*- coding: utf-8 -*-
"""headless 壳：无 UI 运行一个回合，使用与 Web 相同的提示词与上下文装配。

壳层不装配 app：`run(app, text)` 接收现成底座，入口在 `agent.entry.headless`。
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from typing import Any

from agent.core.event_name import ERROR, TURN_ENDED
from agent.mechanisms.session_store import (
    is_valid_conversation_id,
    new_conversation_id,
)

_SUMMARY_KEYS = ("text", "content", "name", "call_id", "ok", "error", "detail", "step")

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_NEEDS_INPUT = 2
EXIT_TIMEOUT = 3


def _format(event) -> str:
    parts = [f"{k}={event.data.get(k)!r}" for k in _SUMMARY_KEYS if k in event.data]
    return f"[{event.type}] " + " ".join(parts)


def _prepare(app: Any, text: str, conversation_id: str,
             cancel: Any = None) -> tuple[str, Any]:
    """返回 (cid, 本回合事件流)：真实 app 走完整提示词；测试替身保留 run_turn 入口。"""
    runner = getattr(app, "runner", None)
    if runner is None:
        return str(conversation_id or "default"), app.run_turn(text)
    cid = str(conversation_id or "").strip() or new_conversation_id()
    if not is_valid_conversation_id(cid):
        raise ValueError("会话 ID 不合法：需 8–128 个字母、数字、下划线或短横")
    events = runner.build_engine(cid, cancel=cancel).start_turn(text)
    return cid, events


def run_session(app: Any, text: str, *, conversation_id: str = "",
                timeout: float | None = None) -> tuple[str, int]:
    """跑一个回合并打印事件流；返回实际使用的 cid 与退出码。"""
    cid = str(conversation_id or "").strip()
    cancel = threading.Event()
    deadline = time.monotonic() + timeout if timeout and timeout > 0 else None
    code = EXIT_OK
    saw_end = False
    events = None
    try:
        cid, events = _prepare(app, text, conversation_id, cancel.is_set)
        for event in events:
            print(_format(event))
            if event.type == ERROR:
                code = EXIT_FAIL
            elif event.type == TURN_ENDED:
                saw_end = True
                data = event.data or {}
                if data.get("halted") or data.get("stopped"):
                    code = EXIT_FAIL
                elif data.get("paused"):
                    code = EXIT_NEEDS_INPUT
            if deadline is not None and time.monotonic() >= deadline:
                cancel.set()
                code = EXIT_TIMEOUT
                break
        if not saw_end and code == EXIT_OK:
            code = EXIT_FAIL
    except Exception as exc:
        print(f"[headless] {type(exc).__name__}: {exc}", file=sys.stderr)
        code = EXIT_FAIL
    finally:
        if code == EXIT_TIMEOUT and events is not None:
            close = getattr(events, "close", None)
            if callable(close):
                close()
    return cid, code


def run(app: Any, text: str, *, conversation_id: str = "",
        timeout: float | None = None) -> int:
    """兼容入口：只返回退出码。"""
    return run_session(app, text, conversation_id=conversation_id, timeout=timeout)[1]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="agent.entry.headless")
    parser.add_argument("text", nargs="?", default="你好，验证内核")
    parser.add_argument("--session", default="", help="恢复/指定会话 ID")
    parser.add_argument("--timeout", type=float, default=None,
                        help="会话超时秒数；超时请求取消")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, app_factory: Any) -> int:
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    app = app_factory()
    if app is None:
        return EXIT_FAIL
    try:
        cid, code = run_session(
            app, args.text, conversation_id=args.session, timeout=args.timeout
        )
        print(f"[session] {cid}")
        return code
    finally:
        dispose = getattr(app, "dispose", None)
        if callable(dispose):
            dispose()
