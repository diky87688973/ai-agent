# -*- coding: utf-8 -*-
"""`desktop_eye`：截屏、叠网格、把图片作为附件交给模型。"""
from __future__ import annotations

import base64
from typing import Any, Dict, Optional

from agent.capabilities.registry import ToolPlugin
from agent.core.tool_call import ToolResult

from .. import canvas
from ..config import DesktopConfig
from ..coords import ScreenRect
from ..ports import Backend
from ._params import as_bool, as_int, has, reject_unknown, require_range

#: 单张截图的像素上限。整屏超过它时给区域参数；这不是内存保护，
#: 而是让错误停在调用侧，不把几百 MB 的位图搬进内存再报错。
MAX_CAPTURE_PIXELS = 40_000_000

_FIELDS = ("x", "y", "width", "height", "grid", "max_side")


class DesktopEyeTool(ToolPlugin):
    """截取桌面并附上图片。"""

    name = "desktop_eye"
    label = "看屏"
    icon = "👁"
    description = (
        "截取桌面并作为图片直接查看（不是 OCR）。支持整屏与区域。"
        "图上叠坐标网格，刻度数字与 desktop_mouse 使用同一套屏幕坐标。"
        "返回屏幕矩形、光标位置与实发尺寸。"
    )
    parameters = {
        "x": {"type": "integer", "description": "区域左上角 x（屏幕坐标）；与 y/width/height 同时给出"},
        "y": {"type": "integer", "description": "区域左上角 y（屏幕坐标）"},
        "width": {"type": "integer", "description": "区域宽度（屏幕坐标）"},
        "height": {"type": "integer", "description": "区域高度（屏幕坐标）"},
        "grid": {"type": "boolean", "description": "叠加坐标网格与刻度（默认 true）"},
        "max_side": {"type": "integer",
                     "description": "长边缩到不超过该像素；0 = 不缩放；缺省取插件配置"},
    }

    def __init__(self, backend: Backend, config: DesktopConfig) -> None:
        self._backend = backend
        self._config = config

    def execute(self, arguments: Dict[str, Any]) -> Any:
        reject_unknown(arguments, _FIELDS, action=self.name)
        geometry = self._backend.screen.geometry()
        region = _region(arguments, geometry.rect)
        planned = region or geometry.rect
        _check_area(planned.width * planned.height)

        screenshot = self._backend.screen.capture(region)
        _check_area(screenshot.rect.width * screenshot.rect.height)
        cursor = self._backend.mouse.cursor()
        grid = as_bool(arguments, "grid", True)
        max_side = require_range(
            as_int(arguments, "max_side", self._config.max_side), "max_side", 0, 8192)

        rendered = canvas.render(
            screenshot.png,
            rect=screenshot.rect,
            grid=grid,
            step=self._config.grid_step,
            cursor=cursor,
            cursor_mark=self._config.cursor_mark,
            max_side=max_side,
        )
        summary: Dict[str, Any] = {
            "platform": self._backend.platform,
            "screen": geometry.rect.to_dict(),
            "capture": screenshot.rect.to_dict(),
            "image": {
                "width": rendered.width,
                "height": rendered.height,
                "sent_width": rendered.sent_width,
                "sent_height": rendered.sent_height,
                "scale": rendered.scale,
                "bytes": len(rendered.png),
            },
            "dpi": geometry.dpi or "unknown",
        }
        if cursor is not None:
            summary["cursor"] = cursor.to_dict()
        if grid:
            summary["grid"] = {"step": self._config.grid_step, "unit": "屏幕坐标"}
        note = _note(rendered, geometry.mixed_scale, self._config.grid_step)
        if note:
            summary["note"] = note

        return ToolResult.attach(summary, [{
            "mime": "image/png",
            "data_base64": base64.b64encode(rendered.png).decode("ascii"),
        }])


def _region(arguments: Dict[str, Any], bounds: ScreenRect) -> Optional[ScreenRect]:
    given = [key for key in ("x", "y", "width", "height") if has(arguments, key)]
    if not given:
        return None
    if len(given) < 4:
        raise ValueError(
            "区域要 x / y / width / height 四个参数一起给；整屏时四个都省略"
        )
    requested = ScreenRect(
        as_int(arguments, "x") or 0,
        as_int(arguments, "y") or 0,
        as_int(arguments, "width") or 0,
        as_int(arguments, "height") or 0,
    )
    clamped = requested.intersect(bounds)
    if clamped is None:
        raise ValueError(f"区域与屏幕没有交集；屏幕是 {bounds.to_dict()}")
    return clamped


def _check_area(pixels: int) -> None:
    if pixels > MAX_CAPTURE_PIXELS:
        raise ValueError(
            f"截图区域 {pixels} 像素超过上限 {MAX_CAPTURE_PIXELS}；"
            "给一个更小的区域，或先缩放屏幕"
        )


def _note(rendered: Any, mixed_scale: bool, step: int) -> str:
    parts = []
    if rendered.shrunk:
        parts.append(
            f"图片已从 {rendered.width}x{rendered.height} 缩到 "
            f"{rendered.sent_width}x{rendered.sent_height}；"
            f"网格刻度（每 {step} 屏幕坐标）仍是原坐标，可直接用于 desktop_mouse"
        )
    if rendered.blank:
        parts.append("画面全黑：可能处于锁屏、UAC 安全桌面或受保护内容")
    if mixed_scale:
        parts.append("多屏缩放不一致，副屏坐标可能有偏差")
    return "；".join(parts)
