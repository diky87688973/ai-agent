# -*- coding: utf-8 -*-
"""内置工具节点工厂（检索与外部资源类）：一个工厂只产出一个工具。

与 `tool_components` 里的工厂是同一种东西，拆开只为让单个模块的函数数落在阈值内；
把工具登记进注册表仍只由 `tool_components.tool_group` 一处完成。
"""
from __future__ import annotations

from typing import Any

from agent.capabilities.registry import ToolPlugin


def make_regex_locate(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin.locate_tools import RegexLocateTool
    return RegexLocateTool()


def make_file_search(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin.locate_tools import FileSearchTool
    return FileSearchTool()


def make_data_table(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin.text_data_tools import DataTableTool
    return DataTableTool()


def make_unified_diagnose(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin.system_tools import UnifiedDiagnoseTool
    return UnifiedDiagnoseTool()


def make_git_workspace(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin.system_tools import GitWorkspaceTool
    return GitWorkspaceTool()


def make_web_fetch(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin.web_tools import WebFetchTool
    return WebFetchTool()


def make_web_fetch_render(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin.web_tools import WebFetchRenderTool
    return WebFetchRenderTool()


def make_image_ocr(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin.ocr_tool import ImageOcrTool
    return ImageOcrTool()


def make_read_image(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin.image_tool import ImageReadTool
    return ImageReadTool()


def make_archive(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin.archive_tool import ArchiveTool
    return ArchiveTool()


def make_ip_geolocate(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin.geo_weather_tools import IpGeolocateTool
    return IpGeolocateTool()


def make_open_meteo_weather(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin.geo_weather_tools import OpenMeteoWeatherTool
    return OpenMeteoWeatherTool()


__all__ = [name for name in globals() if name.startswith("make_")]
