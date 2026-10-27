# -*- coding: utf-8 -*-
"""`desktop_find`：用 UIA 文本定位控件，不做 OCR。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from agent.capabilities.registry import ToolPlugin

from ..coords import ScreenRect
from ..errors import DesktopUnavailable
from ..ports import Backend
from ..titles import normalize_title
from ._params import as_int, choice, has, reject_unknown, require_range
from ._windows import window_target

_FIELDS = ("text", "window", "hwnd", "match", "limit",
           "x", "y", "width", "height")


class DesktopFindTool(ToolPlugin):
    name = "desktop_find"
    label = "查找控件"
    icon = "🔎"
    description = (
        "按文字查找窗口内的控件，走 UIA，不做 OCR。返回 name、control_type、"
        "rect、clickable、source 与 confidence。找不到时返回空 matches，"
        "不要用坐标猜一个替代结果。点击用 desktop_click_text，输入用 desktop_type_into。"
        "给 window / hwnd 限定窗口；不限定则从桌面根节点找。"
    )
    parameters = {
        "text": {"type": "string", "description": "要查找的控件文字"},
        "window": {"type": "string", "description": "限定窗口标题片段；与 hwnd 二选一"},
        "hwnd": {"type": "integer", "description": "限定窗口句柄；导航后优先用 hwnd"},
        "match": {"type": "string", "enum": ["contains", "exact", "regex"],
                  "description": "匹配方式（默认 contains）"},
        "limit": {"type": "integer", "description": "最多返回几条 1–50（默认 10）"},
        "x": {"type": "integer", "description": "可选：只在矩形区域内查找，左上角 x"},
        "y": {"type": "integer", "description": "可选：只在矩形区域内查找，左上角 y"},
        "width": {"type": "integer", "description": "可选：区域宽度"},
        "height": {"type": "integer", "description": "可选：区域高度"},
    }

    def __init__(self, backend: Backend) -> None:
        self._backend = backend

    def execute(self, arguments: Dict[str, Any]) -> Any:
        reject_unknown(arguments, set(_FIELDS), action=self.name)
        text = str(arguments.get("text") or "").strip()
        if not text:
            raise ValueError("text 不能为空")
        locator = self._backend.locator
        if locator is None:
            raise DesktopUnavailable("当前平台没有 UIA 文本定位；请用 desktop_eye + 坐标")
        target, _matched = window_target(self._backend, arguments)
        match = choice(arguments, "match", ("contains", "exact", "regex"), "contains")
        limit = require_range(as_int(arguments, "limit", 10), "limit", 1, 50)
        region = _region(arguments)
        rows = list(locator.find(target.hwnd if target is not None else None,
                                 text, match, limit))
        if region is not None:
            rows = [row for row in rows if region.intersect(row.rect) is not None]
        rows = rows[:limit]
        result = {
            "matches": [row.to_dict() for row in rows],
            "count": len(rows),
            "text": text,
            "match": match,
            "source": "uia",
        }
        if not rows:
            title = normalize_title(target.title) if target is not None else ""
            if any(browser in title for browser in ("chrome", "edge", "firefox")):
                result["note"] = (
                    "浏览器网页没有暴露 UIA 元素；不要重复 desktop_find。"
                    "已知网址优先用 desktop_open 直达，再用 desktop_eye 局部截图定位。"
                )
            else:
                result["note"] = (
                    "该窗口没有暴露可匹配的 UIA 控件；不要重复 desktop_find。"
                    "改用 desktop_eye 局部截图，已知步骤优先用 desktop_act。"
                )
        return result


def _region(arguments: Dict[str, Any]) -> Optional[ScreenRect]:
    keys = ("x", "y", "width", "height")
    present = [key for key in keys if has(arguments, key)]
    if not present:
        return None
    if len(present) != 4:
        raise ValueError("区域过滤需要同时给出 x / y / width / height")
    return ScreenRect(as_int(arguments, "x", 0) or 0,
                      as_int(arguments, "y", 0) or 0,
                      require_range(as_int(arguments, "width", 1), "width", 1, 8192),
                      require_range(as_int(arguments, "height", 1), "height", 1, 8192))
