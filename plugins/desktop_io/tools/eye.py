# -*- coding: utf-8 -*-
"""`desktop_eye`：截屏、叠网格、把图片作为附件交给模型。"""
from __future__ import annotations

import dataclasses
from typing import Any, Dict, Optional

from agent.capabilities.registry import ToolPlugin
from agent.core.tool_call import ToolResult

from ..config import DesktopConfig
from ..coords import ScreenPoint
from ..guard import reject_in_plan
from ..ports import Backend
from ._capture import capture_payload, request_from_arguments
from ._params import as_int, reject_unknown, require_range

_FIELDS = ("x", "y", "width", "height", "grid", "max_side", "window", "hwnd",
           "activate", "hover", "hover_settle_ms")


class DesktopEyeTool(ToolPlugin):
    """截取桌面并附上图片。"""

    name = "desktop_eye"
    label = "看屏"
    icon = "👁"
    description = (
        "截取桌面并作为图片直接查看（不是 OCR）。支持整屏、区域与指定窗口。"
        "给 window（标题片段）或 hwnd 时取该窗口自身内容，目标被别的窗口盖住也能看到；"
        "窗口若已最小化会先恢复再取图，回执标 restored。"
        "activate=false（默认）只恢复不置前，不改变用户正在用的窗口；"
        "需要把窗口亮到前台时给 activate=true。"
        "要给悬停才出现的控件拍照（视频控制条、下拉菜单、提示气泡），"
        "用 hover=[x,y]：同一次调用内先移光标、等界面展开、再截图。"
        "分开调用「先移鼠标、再截图」在多数播放器与网页上都会失败——"
        "控件的自动隐藏通常只有 2–3 秒，撑不过一次模型往返。"
        "不给窗口则取屏幕合成结果（会包含遮挡物）。"
        "图上叠坐标网格，刻度数字与 desktop_mouse 使用同一套屏幕坐标。"
        "细节看不清时用 x/y/width/height 取局部，局部通常按原尺寸发送。"
    )
    parameters = {
        "x": {"type": "integer", "description": "区域左上角 x（屏幕坐标）；与 y/width/height 同时给出"},
        "y": {"type": "integer", "description": "区域左上角 y（屏幕坐标）"},
        "width": {"type": "integer", "description": "区域宽度（屏幕坐标）"},
        "height": {"type": "integer", "description": "区域高度（屏幕坐标）"},
        "window": {"type": "string", "description": "窗口标题片段；取该窗口自身内容，遮挡不影响"},
        "hwnd": {"type": "integer", "description": "窗口句柄；与 window 二选一，hwnd 更精确"},
        "activate": {"type": "boolean",
                     "description": "取图前是否把窗口带到前台（默认 false：只恢复不置前，不打断当前操作）"},
        "hover": {"type": "array", "items": {"type": "integer"}, "minItems": 2,
                  "maxItems": 2,
                  "description": "取图前把光标移到这里 [x, y]（屏幕坐标），用来展开悬停控件"},
        "hover_settle_ms": {"type": "integer",
                            "description": "移完光标等界面展开的毫秒数 0–5000；缺省取插件配置"},
        "grid": {"type": "boolean", "description": "叠加坐标网格与刻度（默认 true）"},
        "max_side": {"type": "integer",
                     "description": "长边缩到不超过该像素；0 = 不缩放；缺省取插件配置"},
    }

    def __init__(self, backend: Backend, config: DesktopConfig,
                 live_state: Any = None) -> None:
        self._backend = backend
        self._config = config
        self._live_state = live_state

    def execute(self, arguments: Dict[str, Any]) -> Any:
        reject_unknown(arguments, set(_FIELDS), action=self.name)
        hover = _hover_point(arguments)
        if hover is not None:
            # 悬停会移动真实光标：它已经不属于"只读看屏"，Plan 模式必须拦住。
            reject_in_plan(self._live_state, "桌面悬停取图")
        request = request_from_arguments(self._backend, self._config, arguments)
        if hover is not None:
            settle = require_range(
                as_int(arguments, "hover_settle_ms", self._config.hover_settle_ms),
                "hover_settle_ms", 0, 5000)
            request = dataclasses.replace(request, hover=hover, hover_settle_ms=settle)

        summary, attachments = capture_payload(self._backend, self._config, request)
        return ToolResult.attach(summary, attachments)


def _hover_point(arguments: Dict[str, Any]) -> Optional[ScreenPoint]:
    """读 hover=[x, y]；形态不对就报错，不做坐标猜测。"""
    value = arguments.get("hover")
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("hover 要给两个整数 [x, y]（屏幕坐标）")
    x, y = value
    for name, number in (("x", x), ("y", y)):
        if isinstance(number, bool) or not isinstance(number, int):
            raise ValueError(f"hover 的 {name} 必须是整数，实际 {number!r}")
    return ScreenPoint(int(x), int(y))
