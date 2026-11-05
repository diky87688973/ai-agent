# -*- coding: utf-8 -*-
"""Visual Operator 插件：眼（截屏）、手（鼠标 / 键盘）、等待与窗口/应用/打开工具。

本插件只提供装配工厂：读本插件目录的 `plugin-config.ini`，按平台建后端，
每个工具一个 `make_tool_*` 工厂。`[config]` 里任一能力关闭时对应的插口由清单
声明控制；后端不可用（无 Pillow、缺辅助功能权限、非 win/mac）不被阻断 ——
动作执行时再报 `DesktopUnavailable`，工具表在不同机器与 CI 上保持一致。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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


@dataclass(frozen=True)
class ToolRuntime:
    """装配期共享件。

    `captures` 必须只有一份：截图与鼠标靠同一张映射对齐，各建各的就对不上了。
    其余字段一次装配只取一回。
    """

    config: DesktopConfig
    backend: Backend
    captures: CaptureStore
    live_state: Any = None


def _runtime_for(config: DesktopConfig, backend: Backend,
                 live_state: Any = None, captures: Any = None) -> ToolRuntime:
    return ToolRuntime(config=config, backend=backend,
                       captures=captures if captures is not None else CaptureStore(),
                       live_state=live_state)


def make_runtime(ctx: Any, live_state: Any) -> ToolRuntime:
    """插口装配入口：一份配置、一个后端、一张截图映射。

    `live_state` 由装配器按 requires 注入：工具执行时用它判 plan 模式。
    """
    return _runtime_for(load_config(), load_backend(), live_state)


def make_tool_desktop_eye(ctx: Any, runtime: ToolRuntime) -> ToolPlugin:
    return DesktopEyeTool(runtime.backend, runtime.config, runtime.live_state,
                          runtime.captures)


def make_tool_desktop_mouse(ctx: Any, runtime: ToolRuntime) -> ToolPlugin:
    return DesktopMouseTool(runtime.backend, runtime.config, runtime.live_state,
                            runtime.captures)


def make_tool_desktop_keyboard(ctx: Any, runtime: ToolRuntime) -> ToolPlugin:
    return DesktopKeyboardTool(runtime.backend, runtime.config, runtime.live_state,
                               runtime.captures)


def make_tool_desktop_wait(ctx: Any, runtime: ToolRuntime) -> ToolPlugin:
    return DesktopWaitTool(runtime.backend, runtime.config)


def make_tool_desktop_window(ctx: Any, runtime: ToolRuntime) -> ToolPlugin:
    return DesktopWindowTool(runtime.backend, runtime.live_state)


def make_tool_desktop_app(ctx: Any, runtime: ToolRuntime) -> ToolPlugin:
    return DesktopAppTool(runtime.backend, runtime.live_state)


def make_tool_desktop_open(ctx: Any, runtime: ToolRuntime) -> ToolPlugin:
    return DesktopOpenTool(runtime.backend, runtime.live_state)


def make_tool_desktop_find(ctx: Any, runtime: ToolRuntime) -> ToolPlugin:
    return DesktopFindTool(runtime.backend)


def make_tool_desktop_click_text(ctx: Any, runtime: ToolRuntime) -> ToolPlugin:
    return DesktopClickTextTool(runtime.backend, runtime.live_state)


def make_tool_desktop_click_region(ctx: Any, runtime: ToolRuntime) -> ToolPlugin:
    return DesktopClickRegionTool(runtime.backend, runtime.live_state,
                                  runtime.captures)


def make_tool_desktop_type_into(ctx: Any, runtime: ToolRuntime) -> ToolPlugin:
    return DesktopTypeIntoTool(runtime.backend, runtime.config, runtime.live_state,
                               runtime.captures)


def make_tool_desktop_act(ctx: Any, runtime: ToolRuntime) -> ToolPlugin:
    return DesktopActTool(runtime.backend, runtime.config, runtime.live_state,
                          runtime.captures)
