# -*- coding: utf-8 -*-
"""`desktop_mouse`：移动、点击、拖拽、滚动与光标查询。"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from agent.capabilities.registry import ToolPlugin
from agent.core.tool_call import ToolResult

from ..config import DesktopConfig
from ..coords import ScreenPoint, ScreenRect
from ..diff import change_ratio, probe_region
from ..guard import reject_in_plan
from ..input_lock import input_guard
from ..ports import Backend
from ._capture import CaptureRequest, capture_payload
from ._params import (
    as_bool, as_int, choice, point_argument, reject_unknown, require_range,
)
from ._windows import WINDOW_FIELDS, focus_target, require_active

BUTTONS = ("left", "right", "middle")

_ACTIONS = {
    "move": ("x", "y", "duration_ms"),
    "click": ("x", "y", "button", "count"),
    "drag": ("x", "y", "to_x", "to_y", "button", "duration_ms"),
    "scroll": ("amount", "x", "y", "horizontal"),
    "cursor": (),
}

#: 会改变界面的动作：只有它们才值得比前后差异。
_MEASURED = ("click", "drag", "scroll")
#: `shot` 只对有落点的动作开放：`cursor` 是只读查询，没有落点可拍。
_SHOT_FIELDS = ("shot", "shot_region", "shot_max_side")


class DesktopMouseTool(ToolPlugin):
    """投递鼠标动作。"""

    name = "desktop_mouse"
    label = "鼠标"
    icon = "🖱"
    description = (
        "操作鼠标。坐标是屏幕坐标，与 desktop_eye 的网格刻度同一坐标系。"
        "click / scroll 省略 x、y 时作用在当前光标位置。"
        "给 window（标题片段）或 hwnd 时先把该窗口恢复并置前，再动作，回执带 focus；"
        "置前失败时不会盲点，直接报错，避免点到遮挡物。"
        "点击回执带两份证据：hit（落点所在窗口与控件类名）与 changed"
        "（落点周围画面的变化比例，0 表示这一下没有任何变化）。"
        "要给动作后的界面同时拍一张，加 shot=true："
        "同一调用内完成「点完就截」，省掉一次「再调 desktop_eye」的往返。"
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
        "window": {"type": "string", "description": "目标窗口标题片段；先置前再动作"},
        "hwnd": {"type": "integer", "description": "目标窗口句柄；与 window 二选一，hwnd 更精确"},
        "shot": {"type": "boolean",
                 "description": "动作完成后在本次调用内截图并作为图片附件返回（默认 false）"},
        "shot_region": {"type": "array", "items": {"type": "integer"}, "minItems": 4,
                        "maxItems": 4,
                        "description": "截图区域 [x, y, width, height]（屏幕坐标）；省略则取整屏或目标窗口"},
        "shot_max_side": {"type": "integer",
                          "description": "shot 的长边上限；缺省取插件配置"},
    }

    def __init__(self, backend: Backend, config: DesktopConfig,
                 live_state: Any = None) -> None:
        self._backend = backend
        self._config = config
        self._live_state = live_state

    def execute(self, arguments: Dict[str, Any]) -> Any:
        action = choice(arguments, "action", _ACTIONS)
        allowed = set(_ACTIONS[action]) | {"action"} | set(WINDOW_FIELDS)
        if action != "cursor":
            allowed |= set(_SHOT_FIELDS)
        reject_unknown(arguments, allowed, action=action)
        if action == "cursor":
            return self._snapshot(action)

        reject_in_plan(self._live_state, "桌面鼠标输入")
        # 人点目标应用之前会先把它弄到前台；置前失败就不能落点，否则点到的是遮挡物。
        focus = focus_target(self._backend, arguments)
        require_active(focus, "鼠标动作")
        point = point_argument(arguments)
        port = self._backend.mouse
        measured = action in _MEASURED
        anchor = point or port.cursor()
        hit = self._probe(anchor) if measured else None
        before = self._sample(anchor) if measured else None

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
        result = self._snapshot(action)
        if hit:
            result["hit"] = hit
        if before is not None:
            ratio = self._change(before, anchor)
            if ratio is not None:
                result["changed"] = ratio
        if focus is not None:
            result["focus"] = focus
        if not as_bool(arguments, "shot", False):
            return result

        request = self._shot_request(arguments, anchor)
        summary, attachments = capture_payload(self._backend, self._config, request)
        summary["performed"] = result
        return ToolResult.attach(summary, attachments)

    def _shot_request(self, arguments: Dict[str, Any], point: ScreenPoint) -> CaptureRequest:
        """动作后的取图请求：默认取目标窗口（没给窗口就取整屏）。"""
        region = _shot_region(arguments, self._backend.screen.geometry().rect)
        max_side = require_range(
            as_int(arguments, "shot_max_side", self._config.max_side),
            "shot_max_side", 0, 8192)
        return CaptureRequest(
            window=_optional_text(arguments, "window"),
            hwnd=as_int(arguments, "hwnd") if arguments.get("hwnd") else None,
            region=region,
            grid=True,
            max_side=max_side,
            extra={"at": point.to_dict()},
        )

    def _probe(self, point: ScreenPoint) -> Optional[Dict[str, Any]]:
        port = self._backend.hit
        if port is None:
            return None
        return port.probe(point) or None

    def _sample(self, point: ScreenPoint) -> Optional[bytes]:
        """落点周围的一小块；取不到就跳过差异比较，不影响动作本身。"""
        region = probe_region(point, self._backend.screen.geometry().rect)
        if region is None:
            return None
        return self._backend.screen.capture(region).png

    def _change(self, before: bytes, point: ScreenPoint) -> Optional[float]:
        region = probe_region(point, self._backend.screen.geometry().rect)
        if region is None:
            return None
        return change_ratio(before, self._backend.screen.capture(region).png)

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


def _optional_text(arguments: Dict[str, Any], key: str) -> Optional[str]:
    value = arguments.get(key)
    return str(value) if value not in (None, "") else None


def _shot_region(arguments: Dict[str, Any],
                 bounds: ScreenRect) -> Optional[ScreenRect]:
    """`shot_region=[x, y, width, height]`；越界部分裁到屏幕内。"""
    raw = arguments.get("shot_region")
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        raise ValueError("shot_region 要给四个整数 [x, y, width, height]")
    for number in raw:
        if isinstance(number, bool) or not isinstance(number, int):
            raise ValueError(f"shot_region 的每一项都必须是整数，实际 {number!r}")
    region = ScreenRect(int(raw[0]), int(raw[1]), int(raw[2]), int(raw[3]))
    clamped = region.intersect(bounds)
    if clamped is None:
        raise ValueError(f"shot_region 与屏幕没有交集；屏幕是 {bounds.to_dict()}")
    return clamped
