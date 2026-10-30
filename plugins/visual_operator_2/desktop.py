# -*- coding: utf-8 -*-
"""2.0 授权下的桌面辅助工具：窗口、应用、单次看屏、文本输入、滚动/拖拽。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from agent.capabilities.registry import ToolPlugin
from plugins.visual_operator.backends import load_backend
from plugins.visual_operator.capture_store import CaptureStore
from plugins.visual_operator.config import load_config as load_desktop_config
from plugins.visual_operator.tools.app import DesktopAppTool
from plugins.visual_operator.tools.click_text import DesktopClickTextTool
from plugins.visual_operator.tools.eye import DesktopEyeTool
from plugins.visual_operator.tools.find import DesktopFindTool
from plugins.visual_operator.tools.keyboard import DesktopKeyboardTool
from plugins.visual_operator.tools.mouse import DesktopMouseTool
from plugins.visual_operator.tools.open import DesktopOpenTool
from plugins.visual_operator.tools.type_into import DesktopTypeIntoTool
from plugins.visual_operator.tools.wait import DesktopWaitTool
from plugins.visual_operator.tools.window import DesktopWindowTool

from . import step_log
from .state import VisionRuntime

AUTH_HINT = "先通过 vision_request_open + vision_start 获得持续视觉授权。"
CORE_ROUTE = "2.0 核心点击用 vision_move_point / vision_click；"
SEPARATE_LOOK = (
    "【单独看屏，不替代持续视觉帧】此工具只截取一张图供本次查看；"
    "下一轮仍以持续视觉帧为准，不要把它当成持续视觉。"
)
def _cid() -> str:
    from .tools import _cid as current
    return current()


class _AuthorizedDesktopTool(ToolPlugin):
    def __init__(self, tool: ToolPlugin, runtime: VisionRuntime, name: str,
                 label: str, description: str) -> None:
        self._tool = tool
        self._runtime = runtime
        self._name = name
        self._label = label
        self._description = description

    @property
    def name(self) -> str:
        return self._name

    @property
    def label(self) -> str:
        return self._label

    @property
    def icon(self) -> str:
        return getattr(self._tool, "icon", "")

    @property
    def description(self) -> str:
        return self._description

    @description.setter
    def description(self, value: str) -> None:
        self._description = str(value)

    @property
    def parameters(self) -> Dict[str, Any]:
        params = dict(self._tool.parameters)
        if self._name == "vision_mouse":
            params.pop("count", None)
            params["action"] = {
                "type": "string", "enum": ["drag", "scroll"],
                "description": "只支持 drag / scroll；移动和点击用 2.0 视觉链"}
        elif self._name == "vision_keyboard":
            params.pop("keys", None)
            params["action"] = {
                "type": "string", "enum": ["type", "key"],
                "description": "type 文本 / key 单键；组合键用 vision_key"}
        return params

    @property
    def parallel_safe(self) -> bool:
        return bool(getattr(self._tool, "parallel_safe", False))

    def __getattr__(self, key: str) -> Any:
        return getattr(self._tool, key)

    def execute(self, arguments: Dict[str, Any]) -> Any:
        cid = _cid()
        status = self._runtime.status(cid) if cid else {"eyes_open": False}
        if not status.get("eyes_open"):
            return {"ok": False, "error": "视觉未授权或已闭眼；" + AUTH_HINT}
        action = str(arguments.get("action") or "").lower()
        if self._name == "vision_mouse" and action not in ("drag", "scroll"):
            return {"ok": False, "error": "vision_mouse 只接受 drag/scroll；" + CORE_ROUTE}
        if self._name == "vision_keyboard" and action == "hotkey":
            return {"ok": False, "error": "组合键改用 vision_key。"}
        result = self._tool.execute(arguments)
        step_log.write("desktop_tool", tool=self._name,
                       conversation_id=cid, arguments=arguments, result=result)
        return result


def build_tools(runtime: VisionRuntime) -> List[ToolPlugin]:
    config = load_desktop_config(Path(__file__).resolve().parent.parent / "visual_operator")
    backend = load_backend()
    captures = CaptureStore()
    specs = [
        ("vision_app", "启动应用", "启动本地应用并等待窗口；不经过视觉搜索。", DesktopAppTool(backend, None)),
        ("vision_window", "窗口", "列窗口、激活、等待、读取矩形；不点击窗口内容。", DesktopWindowTool(backend, None)),
        ("vision_eye", "单独看屏", SEPARATE_LOOK + "支持窗口/区域截图，返回 capture_id。", DesktopEyeTool(backend, config, None, captures)),
        ("vision_type_into", "定位输入", "向 UIA 控件或截图矩形输入文本；用于标准输入框。", DesktopTypeIntoTool(backend, config, None, captures)),
        ("vision_keyboard", "键盘输入", "输入 Unicode 文本或单键；组合键请用 vision_key。", DesktopKeyboardTool(backend, config, None, captures)),
        ("vision_wait", "等待条件", "等待画面变化、窗口出现/消失；不移动鼠标。", DesktopWaitTool(backend, config)),
        ("vision_find", "查找控件", "按文字查找 UIA 控件，返回矩形；不点击。", DesktopFindTool(backend)),
        ("vision_click_text", "点击文字控件", "点击 UIA 文字控件；只用于标准控件，自绘界面用视觉链。", DesktopClickTextTool(backend, None)),
        ("vision_mouse", "滚动拖拽", "只提供滚动和拖拽；移动与点击走 vision_move_point / vision_click。", DesktopMouseTool(backend, config, None, captures)),
        ("vision_open", "打开资源", "打开 URL、文件或协议；不截图、不点击。", DesktopOpenTool(backend, None)),
    ]
    tools: List[ToolPlugin] = []
    for name, label, text, tool in specs:
        desc = (
            f"【2.0 辅助桌面工具】{AUTH_HINT}{text}"
            + ""
            + (" 滚动/拖拽之外不要用它移动或点击。" if name == "vision_mouse" else "")
        )
        tools.append(_AuthorizedDesktopTool(tool, runtime, name, label, desc))
    return tools
