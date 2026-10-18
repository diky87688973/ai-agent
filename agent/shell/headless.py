# -*- coding: utf-8 -*-
"""headless 壳：无 UI 跑一轮并打印事件流。

壳层不装配 app：`run(app, text)` 接收现成底座，入口在 `agent.entry.headless`。
"""
from __future__ import annotations

import sys
from typing import Any

_SUMMARY_KEYS = ("text", "content", "name", "call_id", "ok", "error", "detail", "step")


def _format(event) -> str:
    parts = [f"{k}={event.data.get(k)!r}" for k in _SUMMARY_KEYS if k in event.data]
    return f"[{event.type}] " + " ".join(parts)


def run(app: Any, text: str) -> int:
    """跑一轮并把事件流打到 stdout。"""
    for event in app.run_turn(text):
        print(_format(event))
    return 0


def main(argv: list[str] | None = None, *, app_factory: Any) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    text = args[0] if args else "你好，验证内核"
    return run(app_factory(), text)
