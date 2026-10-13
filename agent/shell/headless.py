# -*- coding: utf-8 -*-
"""headless 壳：无 UI 跑一轮并打印事件流。"""
from __future__ import annotations

import sys

from agent.app import build_app

_SUMMARY_KEYS = ("text", "content", "name", "call_id", "ok", "error", "detail", "step")


def _format(event) -> str:
    parts = [f"{k}={event.data.get(k)!r}" for k in _SUMMARY_KEYS if k in event.data]
    return f"[{event.type}] " + " ".join(parts)


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    text = args[0] if args else "你好，验证内核"
    app = build_app()
    for event in app.run_turn(text):
        print(_format(event))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
