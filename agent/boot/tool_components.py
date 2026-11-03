# -*- coding: utf-8 -*-
"""内置工具节点工厂：每个节点只注册自己的工具，不枚举其他工具。"""
from __future__ import annotations

from typing import Any

from agent.core.context import SERVICE_BACKGROUND_TASKS, SERVICE_SUBAGENTS
from agent.core.slot import SlotLeaf


def _app(ctx: Any) -> Any:
    return ctx.runtime.app


def _leaf(ctx: Any) -> SlotLeaf:
    return SlotLeaf(ctx.node.path, master=ctx.node.master)


def _register(ctx: Any, plugins: Any) -> SlotLeaf:
    for plugin in plugins:
        _app(ctx).registry.register(plugin)
    return _leaf(ctx)


def make_background_task(ctx: Any):
    from agent.capabilities.builtin import background_task
    app = _app(ctx)
    app.registry.register(background_task.build(
        app.context.get(SERVICE_BACKGROUND_TASKS), app.live_state))
    return _leaf(ctx)


def make_echo(ctx: Any):
    from agent.capabilities.builtin import echo
    _app(ctx).registry.register(echo.build())
    return _leaf(ctx)


def make_read_file(ctx: Any):
    from agent.capabilities.builtin import read_file
    _app(ctx).registry.register(read_file.build())
    return _leaf(ctx)


def make_grep_files(ctx: Any):
    from agent.capabilities.builtin import grep_files
    _app(ctx).registry.register(grep_files.build())
    return _leaf(ctx)


def make_glob_files(ctx: Any):
    from agent.capabilities.builtin import glob_files
    _app(ctx).registry.register(glob_files.build())
    return _leaf(ctx)


def make_write_file(ctx: Any):
    from agent.capabilities.builtin import write_file
    _app(ctx).registry.register(write_file.build())
    return _leaf(ctx)


def make_edit_tools(ctx: Any):
    from agent.capabilities.builtin import edit_tools
    return _register(ctx, edit_tools.build_plugins())


def make_fs_tools(ctx: Any):
    from agent.capabilities.builtin import fs_tools
    runtime = ctx.runtime
    return _register(ctx, fs_tools.build_plugins(
        runtime.resources["backups"], runtime.resources["recycle"]))


def make_command_tools(ctx: Any):
    from agent.capabilities.builtin import command_tools
    return _register(ctx, command_tools.build_plugins(_app(ctx).live_state))


def make_tasks(ctx: Any):
    from agent.capabilities import tasks
    return _register(ctx, tasks.build_plugins(_app(ctx).live_state))


def make_session_tools(ctx: Any):
    from agent.capabilities.builtin import session_tools
    return _register(ctx, session_tools.build_plugins(_app(ctx).mesh))


def make_subagent_tools(ctx: Any):
    from agent.capabilities.builtin import subagent_tools
    app = _app(ctx)
    manager = app.context.get(SERVICE_SUBAGENTS) if app.context.has(SERVICE_SUBAGENTS) else None
    if manager is None:
        return _leaf(ctx)
    return _register(ctx, subagent_tools.build(manager))


def make_locate_tools(ctx: Any):
    from agent.capabilities.builtin import locate_tools
    return _register(ctx, locate_tools.build_plugins())


def make_text_data_tools(ctx: Any):
    from agent.capabilities.builtin import text_data_tools
    return _register(ctx, text_data_tools.build_plugins())


def make_system_tools(ctx: Any):
    from agent.capabilities.builtin import system_tools
    return _register(ctx, system_tools.build_plugins())


def make_web_tools(ctx: Any):
    from agent.capabilities.builtin import web_tools
    return _register(ctx, web_tools.build_plugins())


def make_ocr_tool(ctx: Any):
    from agent.capabilities.builtin import ocr_tool
    return _register(ctx, ocr_tool.build_plugins())


def make_image_tool(ctx: Any):
    from agent.capabilities.builtin import image_tool
    return _register(ctx, image_tool.build_plugins())


def make_archive_tool(ctx: Any):
    from agent.capabilities.builtin import archive_tool
    return _register(ctx, archive_tool.build_plugins())


def make_geo_weather_tools(ctx: Any):
    from agent.capabilities.builtin import geo_weather_tools
    return _register(ctx, geo_weather_tools.build_plugins())


def make_review_conclusion(ctx: Any):
    from agent.capabilities.builtin import review_conclusion
    _app(ctx).registry.register(review_conclusion.build())
    return _leaf(ctx)


def make_present_tool(ctx: Any):
    from agent.capabilities.builtin import present_tool
    _app(ctx).registry.register(present_tool.build())
    return _leaf(ctx)


def make_executors(ctx: Any):
    from agent.capabilities.builtin import (
        archive_tool,
        edit_tools,
        fs_tools,
        web_tools,
        write_file,
    )
    runtime = ctx.runtime
    backups = runtime.resources["backups"]
    recycle = runtime.resources["recycle"]
    executors = {}
    executors.update(write_file.build_executors(backups))
    executors.update(edit_tools.build_executors(backups))
    executors.update(fs_tools.build_executors(backups, recycle))
    executors.update(archive_tool.build_executors())
    executors.update(web_tools.build_executors())
    registry = runtime.resources["executors"]
    for name, fn in executors.items():
        registry.add(name, fn, "host")
    _app(ctx).executors = executors
    return _leaf(ctx)


def make_commit_write(ctx: Any):
    from agent.capabilities.builtin import commit_write
    app = _app(ctx)
    app.registry.register(commit_write.build(
        app.executors, ctx.runtime.resources["executors"]))
    return _leaf(ctx)


__all__ = [name for name in globals() if name.startswith("make_")]
