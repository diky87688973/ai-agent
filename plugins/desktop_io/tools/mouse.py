# -*- coding: utf-8 -*-
"""`desktop_mouse`：移动、点击、拖拽、滚动与光标查询。"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from agent.capabilities.registry import ToolPlugin

from ..config import DesktopConfig
from ..coords import ScreenPoint, ScreenRect
from ..guard import reject_in_plan
from ..input_lock import input_guard
from ..ports import Backend
from ._params import as_bool, as_int, choice, point_argument, reject_unknown, require_range

BUTTONS = ("left", "right", "middle")

_ACTIONS = {
    "move": ("x", "y", "duration_ms"),
    "click": ("x", "y", "button", "count"),
    "drag": ("x", "y", "to_x", "to_y", "button", "duration_ms"),
    "scroll": ("amount", "x", "y", "horizontal"),
    "cursor": (),
}


class DesktopMouseTool(ToolPlugin):
    """投递鼠标动作。"""

    name = "desktop_mouse"
    label = "鼠标"
    icon = "🖱"
    description = (
        "操作鼠标。坐标是屏幕坐标，与 desktop_eye 的网格刻度同一坐标系。"
        "click / scroll 省略 x、y 时作用在当前光标位置。"
        "action=cursor 只读查询，Plan 模式可用；其余动作在 Plan 模式被拒绝。"
    )
    parameters = {
        "action": {"type": "string", "enum": list(_ACTIONS),
                   "description": "move 移动 / click 点击 / drag 拖拽 / scroll 滚动 / cursor 查询光标"},
        "x": {"type": "integer", "description": "屏幕坐标 x"},
        "y": {"type": "integer", "description": "屏幕坐标 y"},
        "to_x": {"type": "integer", "description": "拖拽终点 x"},
        "to_y": {"type": "integer", "description": "拖拽终点 y"},
        "button": {"type": "string", "enum": list(BUTTONS), "description": "按键（默认 left）"},
        "count": {"type": "integer", "description": "点击次数 1–3（默认 1）"},
        "amount": {"type": "integer",
                   "description": "滚动量 -50 ~ 50，正数向下 / 向右（scroll 必填）"},
        "horizontal": {"type": "boolean", "description": "横向滚动（默认 false）"},
        "duration_ms": {"type": "integer", "description": "移动 / 拖拽时长 0–5000 毫秒（默认 0）"},
    }

    def __init__(self, backend: Backend, config: DesktopConfig,
                 live_state: Any = None) -> None:
        self._backend = backend
        self._config = config
        self._live_state = live_state

    def execute(self, arguments: Dict[str, Any]) -> Any:
        action = choice(arguments, "action", _ACTIONS)
        reject_unknown(arguments, set(_ACTIONS[action]) | {"action"}, action=action)
        if action == "cursor":
            return self._snapshot(action)

        reject_in_plan(self._live_state, "桌面鼠标输入")
        point = point_argument(arguments)
        port = self._backend.mouse

        if action == "move":
            target = _require_point(point, "move 需要 x、y")
            duration = require_range(as_int(arguments, "duration_ms", 0), "duration_ms", 0, 5000)
            self._ensure_inside(target)
            with input_guard():
                port.move(target, duration)
        elif action == "click":
            button = choice(arguments, "button", BUTTONS, "left")
            count = require_range(as_int(arguments, "count", 1), "count", 1, 3)
            self._ensure_inside(point)
            with input_guard():
                port.click(point, button, count)
        elif action == "drag":
            start = _require_point(point, "drag 需要起点 x、y")
            end = _require_point(
                point_argument(arguments, "to_x", "to_y"), "drag 需要终点 to_x、to_y")
            button = choice(arguments, "button", BUTTONS, "left")
            duration = require_range(as_int(arguments, "duration_ms", 300), "duration_ms", 0, 5000)
            self._ensure_inside(start, end)
            with input_guard():
                port.drag(start, end, button, duration)
        else:
            amount = require_range(as_int(arguments, "amount"), "amount", -50, 50)
            if amount == 0:
                raise ValueError("amount 不能为 0")
            horizontal = as_bool(arguments, "horizontal", False)
            self._ensure_inside(point)
            with input_guard():
                port.scroll(point, amount, horizontal)

        self._settle()
        return self._snapshot(action)

    def _settle(self) -> None:
        if self._config.settle_ms:
            time.sleep(self._config.settle_ms / 1000.0)

    def _ensure_inside(self, *points: Optional[ScreenPoint]) -> None:
        bounds: ScreenRect = self._backend.screen.geometry().rect
        for point in points:
            if point is not None and not bounds.contains(point):
                raise ValueError(
                    f"坐标 {point.to_dict()} 不在屏幕 {bounds.to_dict()} 内"
                )

    def _snapshot(self, action: str) -> Dict[str, Any]:
        cursor = self._backend.mouse.cursor()
        return {
            "action": action,
            "cursor": cursor.to_dict(),
            "screen": self._backend.screen.geometry().rect.to_dict(),
        }


def _require_point(point: Optional[ScreenPoint], message: str) -> ScreenPoint:
    if point is None:
        raise ValueError(message)
    return point
