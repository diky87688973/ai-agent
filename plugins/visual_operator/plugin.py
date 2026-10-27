# -*- coding: utf-8 -*-
"""Visual Operator 插件：眼（截屏）、手（鼠标 / 键盘）、等待与窗口/应用/打开工具。

`register(ctx)` 读本插件目录的 `plugin-config.ini`，按平台装配后端并注册工具。
`[config]` 里任一能力关闭时对应的工具不注册；后端不可用（无 Pillow、缺辅助功能
权限、非 win/mac）不阻断注册 —— 动作执行时再报 `DesktopUnavailable`，
工具表在不同机器与 CI 上保持一致。
"""
from __future__ import annotations

from typing import Any, List

from agent.capabilities.registry import ToolPlugin

from .backends import load_backend
from .capture_store import CaptureStore
from .config import DesktopConfig, load_config
from .ports import Backend
from .tools import (
    DesktopActTool,
    DesktopAppTool,
    DesktopClickRegionTool,
    DesktopClickTextTool,
    DesktopEyeTool,
    DesktopFindTool,
    DesktopKeyboardTool,
    DesktopMouseTool,
    DesktopOpenTool,
    DesktopTypeIntoTool,
    DesktopWaitTool,
    DesktopWindowTool,
)

PLUGIN_VERSION = "1.0"


def build_tools(config: DesktopConfig, backend: Backend,
                live_state: Any = None,
                captures: Any = None) -> List[ToolPlugin]:
    """按开关装配工具；`captures` 让截图与鼠标共用同一份映射登记。"""
    captures = captures if captures is not None else CaptureStore()
    tools: List[ToolPlugin] = []
    if config.eye:
        tools.append(DesktopEyeTool(backend, config, live_state, captures))
    if config.mouse:
        tools.append(DesktopMouseTool(backend, config, live_state, captures))
    if config.keyboard:
        tools.append(DesktopKeyboardTool(backend, config, live_state, captures))
    if config.wait:
        tools.append(DesktopWaitTool(backend, config))
    tools.append(DesktopWindowTool(backend, live_state))
    tools.append(DesktopAppTool(backend, live_state))
    tools.append(DesktopOpenTool(backend, live_state))
    tools.append(DesktopFindTool(backend))
    tools.append(DesktopClickTextTool(backend, live_state))
    tools.append(DesktopClickRegionTool(backend, live_state, captures))
    tools.append(DesktopTypeIntoTool(backend, config, live_state, captures))
    tools.append(DesktopActTool(backend, config, live_state, captures))
    return tools


def register(ctx: Any) -> List[Any]:
    """插件入口：注册视觉操作工具，返回它们的 disposer。"""
    config = load_config()
    backend = load_backend()
    captures = CaptureStore()

    def live_state() -> Any:
        # 装载阶段内核还没装配完：执行工具时再取，拿不到就不做模式门控。
        return getattr(ctx.app, "live_state", None)

    return [
        ctx.register_tool(tool)
        for tool in build_tools(config, backend, live_state, captures)
    ]
