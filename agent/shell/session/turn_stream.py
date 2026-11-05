"""终端回合事件流：固定插件代后再创建提示词与引擎。"""
from __future__ import annotations

from contextlib import nullcontext
from typing import Any


def turn_events(app: Any, cid: str, text: str, *, cancel: Any = None):
    lifecycle = getattr(getattr(app, "context", None), "slot_lifecycle", None)
    with lifecycle.turn() if lifecycle is not None else nullcontext():
        yield from app.runner.build_engine(cid, cancel=cancel).start_turn(text)
