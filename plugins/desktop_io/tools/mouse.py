# -*- coding: utf-8 -*-
"""`desktop_mouse`：移动、点击、拖拽、滚动与光标查询。"""
from __future__ import annotations

import sys
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
    as_bool,
    as_int,
    choice,
    point_argument,
    reject_unknown,
    require_range,
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
#: 落点原地没变时，再等一小会儿复采一次：页面跳转通常比 60ms 慢。
_LATE_SAMPLE_MS = 250
#: 小于它视为"落点没动"；`changed` 是三位小数，0.005 约等于 0。
_LOCAL_STILL = 0.005
#: 回执里最多列几个新出现/消失的窗口。
_WINDOW_LIST_LIMIT = 3


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
        "点击回执带三份证据：hit（落点所在窗口与控件类名）、"
        "changed（落点周围 200×200 的像素变化比例）与 window_changed"
        "（顶层窗口是否被替换、有没有新窗口出现）。"
        "changed=0 只说明落点原地没动，不代表没点中："
        "window_changed.navigated=true 才是「点进了详情/播放页」的正解。"
        "要给动作后的界面同时拍一张，加 shot=true："
        "同一调用内完成「点完就截」，省掉一次「再调 desktop_eye」的往返；"
        "回图默认拍落点实际所在的窗口（shot_of=hit），不是按标题重新解析的那个。"
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
        windows_before = self._window_digest() if measured else None

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
        ratio: Optional[float] = None
        if before is not None:
            ratio = self._change(before, anchor)
            if ratio is not None:
                result["changed"] = ratio
                result["changed_scope"] = "point_200"
        if focus is not None:
            result["focus"] = focus
        if measured:
            # `changed` 只说明落点周围 200×200 的像素动没动。跳转类点击
            # （卡片 → 详情页 / 新窗口）变化发生在窗口层，必须单独回执，
            # 否则 0.0 会被读成"没点中"。
            after_hit = self._probe(anchor) if hit is not None else None
            window_delta = self._window_delta(
                hit, after_hit, windows_before, self._window_digest(), ratio)
            result["window_changed"] = window_delta
            if ratio is not None and ratio < _LOCAL_STILL:
                late = self._change_after(before, anchor)
                if late is not None:
                    result["changed_late"] = late
                    result["changed_late_after_ms"] = _LATE_SAMPLE_MS
                    # 采第一次时页面可能还没重绘；后采到了就以后采为准。
                    if late > ratio:
                        result["changed"] = late
                        result["changed_note"] = "首次采样时画面尚未重绘，changed 取后采值"
        if not as_bool(arguments, "shot", False):
            return result

        request, shot_note = self._shot_request(arguments, anchor, result)
        summary, attachments = capture_payload(self._backend, self._config, request)
        summary["performed"] = result
        if shot_note:
            summary["note"] = f"{shot_note}；{summary['note']}" if summary.get("note") else shot_note
        return ToolResult.attach(summary, attachments)

    def _shot_request(self, arguments: Dict[str, Any], point: ScreenPoint,
                      performed: Dict[str, Any]):
        """动作后的取图请求：默认拍"动作实际落在的那个窗口"。

        只按 `window` 标题重新解析会拍错层：播放器画面是独立顶层窗口，
        而标题命中的往往是它上面的详情页壳。落点探测已经知道真正点中了谁，
        回图必须跟着它走，否则"点了并看见"看见的是另一个窗口。
        """
        region = _shot_region(arguments, self._backend.screen.geometry().rect)
        max_side = require_range(
            as_int(arguments, "shot_max_side", self._config.max_side),
            "shot_max_side", 0, 8192)
        window = _optional_text(arguments, "window")
        hwnd = as_int(arguments, "hwnd") if arguments.get("hwnd") else None
        source = "window" if window else ("hwnd" if hwnd else "")
        note = ""
        if not source:
            landed = _root_hwnd(performed.get("hit"))
            if landed:
                hwnd, source = landed, "hit"
            else:
                focus = performed.get("focus") or {}
                if focus.get("hwnd"):
                    hwnd, source = int(focus["hwnd"]), "focus"
        if source == "hit":
            focus = performed.get("focus") or {}
            if focus.get("hwnd") and int(focus["hwnd"]) != int(hwnd):
                hit_title = (performed.get("hit") or {}).get("title") or ""
                label = f"「{hit_title}」" if hit_title else ""
                note = (f"回图取的是落点所在窗口 hwnd={hwnd}{label}，"
                        f"不是置前窗口 hwnd={focus['hwnd']}；两者不是同一层")
        return CaptureRequest(
            window=window,
            hwnd=hwnd,
            region=region,
            grid=True,
            max_side=max_side,
            extra={"at": point.to_dict(), "shot_of": source or "screen"},
        ), note

    def _window_digest(self) -> Optional[Dict[int, str]]:
        """可见顶层窗口的 hwnd → 标题；后端不支持时返回 None。"""
        port = self._backend.windows
        lister = getattr(port, "list_visible", None) if port is not None else None
        if lister is None:
            return None
        try:
            listed = lister()
            if listed is None:
                return None
            return {info.hwnd: info.title for info in listed}
        except Exception as exc:
            print(f"[desktop_io] 窗口清单读取跳过：{exc}", file=sys.stderr, flush=True)
            return None

    def _window_delta(self, before_hit: Optional[Dict[str, Any]],
                      after_hit: Optional[Dict[str, Any]],
                      before_windows: Optional[Dict[int, str]],
                      after_windows: Optional[Dict[int, str]],
                      local_ratio: Optional[float]) -> Dict[str, Any]:
        """动作前后的窗口层对比：顶层内容是否被替换、有没有新窗口。"""
        delta: Dict[str, Any] = {"changed": False}
        before_brief = _hit_brief(before_hit)
        after_brief = _hit_brief(after_hit)
        if before_brief:
            delta["hit_before"] = before_brief
        if after_brief:
            delta["hit_after"] = after_brief

        opened: list = []
        closed: list = []
        if before_windows is not None and after_windows is not None:
            opened = [
                {"hwnd": hwnd, "title": after_windows[hwnd]}
                for hwnd in after_windows.keys() - before_windows.keys()
                if after_windows[hwnd]
            ]
            closed = [
                {"hwnd": hwnd, "title": before_windows[hwnd]}
                for hwnd in before_windows.keys() - after_windows.keys()
                if before_windows[hwnd]
            ]
            if opened:
                delta["opened"] = opened[:_WINDOW_LIST_LIMIT]
                if len(opened) > _WINDOW_LIST_LIMIT:
                    delta["opened_more"] = len(opened) - _WINDOW_LIST_LIMIT
            if closed:
                delta["closed"] = closed[:_WINDOW_LIST_LIMIT]
                if len(closed) > _WINDOW_LIST_LIMIT:
                    delta["closed_more"] = len(closed) - _WINDOW_LIST_LIMIT

        hit_changed = False
        if before_brief and after_brief:
            hit_changed = (before_brief.get("hwnd") != after_brief.get("hwnd")
                           or before_brief.get("title") != after_brief.get("title"))
        delta["changed"] = bool(opened or closed or hit_changed)
        if delta["changed"]:
            # 落点原地没动、窗口层却变了：这才是"点进了详情/播放页"的正解。
            delta["navigated"] = bool(opened or hit_changed) and (
                local_ratio is None or local_ratio < 0.01)
        return delta

    def _change_after(self, before: bytes, point: ScreenPoint) -> Optional[float]:
        """落点首次采样没动静时，等一次真实重绘再复采。"""
        time.sleep(_LATE_SAMPLE_MS / 1000.0)
        return self._change(before, point)

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


def _root_hwnd(hit: Optional[Dict[str, Any]]) -> Optional[int]:
    """落点所属的顶层窗口；`probe` 只在子窗口时才给 root。"""
    if not hit:
        return None
    value = hit.get("root") or hit.get("hwnd")
    try:
        return int(value) if value else None
    except (TypeError, ValueError):
        return None


def _hit_brief(hit: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """回执只留判断需要的窗口身份，不复制整个 probe。"""
    if not hit:
        return None
    root = _root_hwnd(hit)
    if root is None:
        return None
    brief: Dict[str, Any] = {"hwnd": root}
    title = hit.get("title")
    if title:
        brief["title"] = title
    return brief


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
