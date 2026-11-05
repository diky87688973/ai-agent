# -*- coding: utf-8 -*-
"""2.0 授权下的桌面辅助工具：窗口、应用、单次看屏、文本输入、滚动/拖拽。"""
from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class DesktopParts:
    """桌面辅助工具共享件。

    `captures` 必须只有一份：截图与鼠标靠同一张映射对齐。
    """

    config: Any
    backend: Any
    captures: CaptureStore


def make_desktop_parts() -> DesktopParts:
    """单点构造共享件；10 个桌面工具全部从这里取。"""
    config = load_desktop_config(
        Path(__file__).resolve().parent.parent / "visual_operator")
    return DesktopParts(config=config, backend=load_backend(),
                        captures=CaptureStore())


def _describe(name: str, text: str) -> str:
    return (
        f"【2.0 辅助桌面工具】{AUTH_HINT}{text}"
        + (" 滚动/拖拽之外不要用它移动或点击。" if name == "vision_mouse" else "")
    )


def make_vision_app(vision: VisionRuntime, parts: DesktopParts) -> ToolPlugin:
    return _AuthorizedDesktopTool(
        DesktopAppTool(parts.backend, None), vision, "vision_app", "启动应用",
        _describe("vision_app", "启动本地应用并等待窗口；不经过视觉搜索。"))


def make_vision_window(vision: VisionRuntime, parts: DesktopParts) -> ToolPlugin:
    return _AuthorizedDesktopTool(
        DesktopWindowTool(parts.backend, None), vision, "vision_window", "窗口",
        _describe("vision_window", "列窗口、激活、等待、读取矩形；不点击窗口内容。"))


def make_vision_eye(vision: VisionRuntime, parts: DesktopParts) -> ToolPlugin:
    return _AuthorizedDesktopTool(
        DesktopEyeTool(parts.backend, parts.config, None, parts.captures),
        vision, "vision_eye", "单独看屏",
        _describe("vision_eye", SEPARATE_LOOK + "支持窗口/区域截图，返回 capture_id。"))


def make_vision_type_into(vision: VisionRuntime, parts: DesktopParts) -> ToolPlugin:
    return _AuthorizedDesktopTool(
        DesktopTypeIntoTool(parts.backend, parts.config, None, parts.captures),
        vision, "vision_type_into", "定位输入",
        _describe("vision_type_into", "向 UIA 控件或截图矩形输入文本；用于标准输入框。"))


def make_vision_keyboard(vision: VisionRuntime, parts: DesktopParts) -> ToolPlugin:
    return _AuthorizedDesktopTool(
        DesktopKeyboardTool(parts.backend, parts.config, None, parts.captures),
        vision, "vision_keyboard", "键盘输入",
        _describe("vision_keyboard", "输入 Unicode 文本或单键；组合键请用 vision_key。"))


def make_vision_wait(vision: VisionRuntime, parts: DesktopParts) -> ToolPlugin:
    return _AuthorizedDesktopTool(
        DesktopWaitTool(parts.backend, parts.config), vision, "vision_wait",
        "等待条件", _describe("vision_wait", "等待画面变化、窗口出现/消失；不移动鼠标。"))


def make_vision_find(vision: VisionRuntime, parts: DesktopParts) -> ToolPlugin:
    return _AuthorizedDesktopTool(
        DesktopFindTool(parts.backend), vision, "vision_find", "查找控件",
        _describe("vision_find", "按文字查找 UIA 控件，返回矩形；不点击。"))


def make_vision_click_text(vision: VisionRuntime,
                           parts: DesktopParts) -> ToolPlugin:
    return _AuthorizedDesktopTool(
        DesktopClickTextTool(parts.backend, None), vision, "vision_click_text",
        "点击文字控件",
        _describe("vision_click_text",
                  "点击 UIA 文字控件；只用于标准控件，自绘界面用视觉链。"))


def make_vision_mouse(vision: VisionRuntime, parts: DesktopParts) -> ToolPlugin:
    return _AuthorizedDesktopTool(
        DesktopMouseTool(parts.backend, parts.config, None, parts.captures),
        vision, "vision_mouse", "滚动拖拽",
        _describe("vision_mouse",
                  "只提供滚动和拖拽；移动与点击走 vision_move_point / vision_click。"))


def make_vision_open(vision: VisionRuntime, parts: DesktopParts) -> ToolPlugin:
    return _AuthorizedDesktopTool(
        DesktopOpenTool(parts.backend, None), vision, "vision_open", "打开资源",
        _describe("vision_open", "打开 URL、文件或协议；不截图、不点击。"))


#: 桌面辅助工具装配顺序。
DESKTOP_TOOL_FACTORIES = (
    make_vision_app, make_vision_window, make_vision_eye, make_vision_type_into,
    make_vision_keyboard, make_vision_wait, make_vision_find,
    make_vision_click_text, make_vision_mouse, make_vision_open,
)


def build_tools(runtime: VisionRuntime,
                parts: DesktopParts | None = None) -> List[ToolPlugin]:
    parts = parts if parts is not None else make_desktop_parts()
    return [factory(runtime, parts) for factory in DESKTOP_TOOL_FACTORIES]
