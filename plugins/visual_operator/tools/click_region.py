# -*- coding: utf-8 -*-
"""`desktop_click_region`：用视觉矩形中心点击，避免模型估中心点。"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from agent.capabilities.registry import ToolPlugin
from agent.core.error_report import report_error
from agent.core.session_scope import current_session_id

from ..capture_store import CaptureStore
from ..coords import ScreenPoint, ScreenRect
from ..guard import reject_in_plan
from ..input_lock import input_guard
from ..ports import Backend
from ._evidence import begin, finish
from ._params import as_int, choice, reject_unknown, require_range
from ._windows import focus_target, require_active


class DesktopClickRegionTool(ToolPlugin):
    name = "desktop_click_region"
    label = "按区域点击"
    icon = "▭"
    description = (
        "点击一个视觉矩形的中心。没有 UIA 时，精确点击必须按此协议："
        "① 用 desktop_eye annotated + grid_step=20 量外框，绝对不要用 raw 量；"
        "② 矩形来自截图时必须带 capture_id + space=image，禁止把图内坐标当屏幕坐标；"
        "③ 本工具计算中心并点击；④ 用 changed / title_changed / verified 核验。"
        "模型只提供矩形，不直接提供中心点。changed=0 不能单独判失败。Plan 模式下拒绝。"
    )
    parameters = {
        "x": {"type": "integer", "description": "矩形左上角 x"},
        "y": {"type": "integer", "description": "矩形左上角 y"},
        "width": {"type": "integer", "description": "矩形宽度"},
        "height": {"type": "integer", "description": "矩形高度"},
        "window": {"type": "string", "description": "目标窗口标题片段"},
        "hwnd": {"type": "integer", "description": "目标窗口句柄"},
        "button": {"type": "string", "enum": ["left", "right", "middle"],
                   "description": "鼠标键（默认 left）"},
        "count": {"type": "integer", "description": "点击次数 1–3（默认 1）"},
        "space": {"type": "string", "enum": ["screen", "image"],
                  "description": "screen 屏幕坐标（默认）/ image 图内坐标（需 capture_id）"},
        "capture_id": {"type": "string", "description": "desktop_eye 返回的 capture_id"},
    }
    _FIELDS = ("x", "y", "width", "height", "window", "hwnd", "button", "count",
               "space", "capture_id")

    def __init__(self, backend: Backend, live_state: Any = None,
                 captures: Optional[CaptureStore] = None) -> None:
        self._backend = backend
        self._live_state = live_state
        self._captures = captures

    def execute(self, arguments: Dict[str, Any]) -> Any:
        reject_unknown(arguments, set(self._FIELDS), action=self.name)
        reject_in_plan(self._live_state, "桌面按区域点击")
        capture_id = str(arguments.get("capture_id") or "").strip()
        space = choice(arguments, "space", ("screen", "image"), "image" if capture_id else "screen")
        raw = ScreenRect(
            as_int(arguments, "x", 0) or 0, as_int(arguments, "y", 0) or 0,
            require_range(as_int(arguments, "width", 1), "width", 1, 8192),
            require_range(as_int(arguments, "height", 1), "height", 1, 8192))
        if space == "image":
            if not capture_id:
                raise ValueError("space=image 需要 capture_id")
            ref = self._captures.resolve(current_session_id(), capture_id) if self._captures else None
            if ref is None:
                raise ValueError("capture_id 不存在、过期或不属于当前会话")
            left = ref.to_screen(raw.x, raw.y)
            right = ref.to_screen(raw.x + raw.width - 1,
                                  raw.y + raw.height - 1)
            region = ScreenRect(left.x, left.y,
                                right.x - left.x + 1, right.y - left.y + 1)
        else:
            if capture_id:
                raise ValueError("capture_id 只能与 space=image 一起使用")
            region = raw
        point = ScreenPoint(region.x + region.width // 2,
                            region.y + region.height // 2)
        focus = focus_target(self._backend, arguments)
        require_active(focus, "按区域点击")
        button = choice(arguments, "button", ("left", "right", "middle"), "left")
        count = require_range(as_int(arguments, "count", 1), "count", 1, 3)
        evidence = begin(self._backend, point)
        with input_guard():
            self._backend.mouse.click(point, button, count)
        time.sleep(0.05)
        changed = finish(self._backend, evidence)
        title_changed = _title_changed(self._backend, focus)
        result: Dict[str, Any] = {
            "clicked": True, "rect": region.to_dict(), "point": point.to_dict(),
            "button": button, "count": count, "changed": changed,
            "title_changed": title_changed,
            "verified": (changed is not None and changed > 0) or title_changed,
        }
        if focus is not None:
            result["focus"] = focus
        hit = getattr(self._backend, "hit", None)
        if hit is not None:
            probe = hit.probe(point)
            if probe:
                result["hit"] = probe
        return result


def _title_changed(backend: Any, focus: Any) -> bool:
    if not focus or not focus.get("hwnd"):
        return False
    try:
        before = str(focus.get("title") or "")
        current = backend.windows.get(int(focus["hwnd"]))
        return current.title != before
    except Exception as exc:
        report_error("plugin.visual_operator.title_changed", exc)
        return False
