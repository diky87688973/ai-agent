# -*- coding: utf-8 -*-
"""`desktop_click_text`：定位文字控件并点击。"""
from __future__ import annotations

import time
from typing import Any, Dict

from agent.capabilities.registry import ToolPlugin

from ..errors import DesktopUnavailable
from ..guard import reject_in_plan
from ..input_lock import input_guard
from ..ports import Backend
from ._evidence import begin, finish
from ._params import as_int, choice, reject_unknown, require_range
from ._windows import focus_target, require_active, window_target

_FIELDS = ("text", "window", "hwnd", "match", "index", "button", "count")


class DesktopClickTextTool(ToolPlugin):
    name = "desktop_click_text"
    label = "按文字点击"
    icon = "🖱"
    description = (
        "用 UIA 找到文字控件并点击它的可点击点或矩形中心；不做 OCR。"
        "多个命中时用 index 指定，找不到直接报错，不回退盲点。"
        "先定位再点击，一次往返完成；点击后回执 match、point、focus、hit。"
        "Plan 模式下拒绝。"
    )
    parameters = {
        "text": {"type": "string", "description": "要点击的控件文字"},
        "window": {"type": "string", "description": "限定窗口标题片段；与 hwnd 二选一"},
        "hwnd": {"type": "integer", "description": "限定窗口句柄；优先使用稳定 hwnd"},
        "match": {"type": "string", "enum": ["contains", "exact", "regex"],
                  "description": "匹配方式（默认 contains）"},
        "index": {"type": "integer", "description": "第几个命中 0–49（默认 0）"},
        "button": {"type": "string", "enum": ["left", "right", "middle"],
                   "description": "鼠标键（默认 left）"},
        "count": {"type": "integer", "description": "点击次数 1–3（默认 1）"},
    }

    def __init__(self, backend: Backend, live_state: Any = None) -> None:
        self._backend = backend
        self._live_state = live_state

    def execute(self, arguments: Dict[str, Any]) -> Any:
        reject_unknown(arguments, set(_FIELDS), action=self.name)
        reject_in_plan(self._live_state, "桌面按文字点击")
        locator = self._backend.locator
        if locator is None:
            raise DesktopUnavailable("当前平台没有 UIA 文本定位；请用 desktop_eye + 坐标")
        text = str(arguments.get("text") or "").strip()
        if not text:
            raise ValueError("text 不能为空")
        target, _matched = window_target(self._backend, arguments)
        match = choice(arguments, "match", ("contains", "exact", "regex"), "contains")
        index = require_range(as_int(arguments, "index", 0), "index", 0, 49)
        moves = list(locator.find(target.hwnd if target is not None else None,
                                  text, match, index + 1))
        if index >= len(moves):
            raise ValueError(f"没有第 {index} 个文字命中「{text}」")
        row = moves[index]
        point = row.clickable or _center(row.rect)
        focus = focus_target(self._backend, arguments)
        require_active(focus, "按文字点击")
        button = choice(arguments, "button", ("left", "right", "middle"), "left")
        count = require_range(as_int(arguments, "count", 1), "count", 1, 3)
        evidence = begin(self._backend, point)
        with input_guard():
            self._backend.mouse.click(point, button, count)
        time.sleep(0.05)
        changed = finish(self._backend, evidence)
        result: Dict[str, Any] = {
            "clicked": True, "match": row.to_dict(), "point": point.to_dict(),
            "count": count, "button": button,
            "changed": changed, "verified": changed is not None and changed > 0,
        }
        if focus is not None:
            result["focus"] = focus
        hit = getattr(self._backend, "hit", None)
        if hit is not None:
            probe = hit.probe(point)
            if probe:
                result["hit"] = probe
        return result


def _center(rect: Any) -> Any:
    from ..coords import ScreenPoint
    return ScreenPoint(rect.x + rect.width // 2, rect.y + rect.height // 2)
