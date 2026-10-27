# -*- coding: utf-8 -*-
"""`desktop_type_into`：按文字定位输入框并输入。"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from agent.capabilities.registry import ToolPlugin
from agent.core.error_report import report_error
from agent.core.session_scope import current_session_id

from ..capture_store import CaptureStore
from ..config import DesktopConfig
from ..coords import ScreenRect
from ..errors import DesktopUnavailable
from ..guard import reject_in_plan
from ..input_lock import input_guard
from ..ports import Backend
from ._evidence import begin, finish
from ._params import as_bool, as_int, as_text, choice, reject_unknown, require_range
from ._windows import focus_target, require_active, window_target


class DesktopTypeIntoTool(ToolPlugin):
    name = "desktop_type_into"
    label = "按文字输入"
    icon = "⌨"
    description = (
        "输入文本：target 用 UIA 找控件，或 x/y/width/height 给视觉定位的矩形（取中心）。"
        "自绘控件（例如 EVO_WidgetWin_0）不得用 desktop_keyboard type 盲打；"
        "必须先用 desktop_eye annotated + grid_step=20 量输入区外框，"
        "矩形来自截图时带 capture_id + space=image。"
        "clear=true 先 ctrl+a，submit=true 最后回车。"
        "矩形模式仍做像素 diff，输入后必须看 verified；不盲打。Plan 模式下拒绝。"
    )
    parameters = {
        "target": {"type": "string", "description": "目标控件的文字；与矩形二选一"},
        "x": {"type": "integer", "description": "矩形模式：目标输入区左上角 x"},
        "y": {"type": "integer", "description": "矩形模式：目标输入区左上角 y"},
        "width": {"type": "integer", "description": "矩形模式：目标输入区宽度"},
        "height": {"type": "integer", "description": "矩形模式：目标输入区高度"},
        "text": {"type": "string", "description": "要输入的文本"},
        "window": {"type": "string", "description": "限定窗口标题片段；与 hwnd 二选一"},
        "hwnd": {"type": "integer", "description": "限定窗口句柄"},
        "match": {"type": "string", "enum": ["contains", "exact", "regex"],
                  "description": "目标文字匹配方式（默认 contains）"},
        "index": {"type": "integer", "description": "第几个目标命中 0–49（默认 0）"},
        "clear": {"type": "boolean", "description": "输入前 ctrl+a 清空（默认 true）"},
        "submit": {"type": "boolean", "description": "输入后按回车（默认 false）"},
        "space": {"type": "string", "enum": ["screen", "image"],
                  "description": "矩形坐标空间：screen（默认）/ image（需 capture_id）"},
        "capture_id": {"type": "string", "description": "desktop_eye 返回的 capture_id"},
    }

    _FIELDS = ("target", "x", "y", "width", "height", "text", "window",
               "hwnd", "match", "index", "clear", "submit", "space", "capture_id")

    def __init__(self, backend: Backend, config: DesktopConfig,
                 live_state: Any = None, captures: Optional[CaptureStore] = None) -> None:
        self._backend = backend
        self._config = config
        self._live_state = live_state
        self._captures = captures

    def execute(self, arguments: Dict[str, Any]) -> Any:
        reject_unknown(arguments, set(self._FIELDS), action=self.name)
        reject_in_plan(self._live_state, "桌面按文字输入")
        move_text = as_text(arguments, "text")
        target_text = str(arguments.get("target") or "").strip()
        rect_keys = ("x", "y", "width", "height")
        has_rect = any(k in arguments for k in rect_keys)
        if target_text and has_rect:
            raise ValueError("target 与 x/y/width/height 二选一")
        if target_text:
            locator = self._backend.locator
            if locator is None:
                raise DesktopUnavailable("当前平台没有 UIA；改用 x/y/width/height 矩形模式")
            target, _matched = window_target(self._backend, arguments)
            match = choice(arguments, "match", ("contains", "exact", "regex"), "contains")
            index = require_range(as_int(arguments, "index", 0), "index", 0, 49)
            moves = list(locator.find(target.hwnd if target is not None else None,
                                      target_text, match, index + 1))
            if index >= len(moves):
                raise ValueError(f"没有第 {index} 个目标命中「{target_text}」")
            row = moves[index]
            point = row.clickable or _center(row.rect)
        else:
            if not all(k in arguments for k in rect_keys):
                raise ValueError("需要 target，或同时给出 x/y/width/height")
            capture_id = str(arguments.get("capture_id") or "").strip()
            space = choice(arguments, "space", ("screen", "image"),
                           "image" if capture_id else "screen")
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
                region = ScreenRect(left.x, left.y, right.x - left.x + 1,
                                    right.y - left.y + 1)
            else:
                if capture_id:
                    raise ValueError("capture_id 只能与 space=image 一起使用")
                region = raw
            from ..locate import LocatorMatch
            row = LocatorMatch(name="(rect)", control_type="Rect", rect=region,
                               clickable=None, source="point", confidence=0.0)
            point = _center(region)
        focus = focus_target(self._backend, arguments)
        require_active(focus, "按文字输入")
        evidence = begin(self._backend, point)
        with input_guard():
            self._backend.mouse.click(point, "left", 1)
            time.sleep(0.05)
            if as_bool(arguments, "clear", True):
                self._backend.keyboard.hotkey(("ctrl", "a"), 1)
                time.sleep(0.02)
            self._backend.keyboard.type_text(move_text, self._config.type_interval_ms)
            if as_bool(arguments, "submit", False):
                self._backend.keyboard.press("enter", 1)
        changed = finish(self._backend, evidence)
        title_changed = _title_changed(self._backend, focus)
        result: Dict[str, Any] = {
            "typed": True, "target": row.to_dict(), "point": point.to_dict(),
            "chars": len(move_text), "submitted": as_bool(arguments, "submit", False),
            "changed": changed, "title_changed": title_changed,
            "verified": (changed is not None and changed > 0) or title_changed,
        }
        if focus is not None:
            result["focus"] = focus
        return result


def _center(rect: Any) -> Any:
    from ..coords import ScreenPoint
    return ScreenPoint(rect.x + rect.width // 2, rect.y + rect.height // 2)


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
