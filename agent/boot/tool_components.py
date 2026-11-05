# -*- coding: utf-8 -*-
"""内置工具节点工厂：一个工厂只产出一个工具，注册由容器统一完成。

工具节点只负责造出工具对象；把工具登记进注册表、决定登记顺序与失败回滚，
都是 `tool_group` 一个容器的事 —— 否则 47 个节点各自持有注册表句柄，
注册这一职责就散到 47 个地方。
"""
from __future__ import annotations

from typing import Any, List

from agent.capabilities.registry import ToolPlugin


def tool_group(ctx: Any, children: Any = (), registry: Any = None) -> Any:
    """把子节点产出的工具逐个登记进注册表，按 order 顺序。

    本容器除工具外还挂着 `executors` 服务节点，所以只登记真正的工具对象；
    其余子节点是容器的同层邻居，不归这里管。
    """
    registered: List[Any] = []
    for item in children:
        if not isinstance(item, ToolPlugin):
            continue
        registry.register(item)
        registered.append(item)
    return tuple(registered)


def make_background_task(ctx: Any, background_tasks: Any = None,
                         live_state: Any = None) -> ToolPlugin:
    from agent.capabilities.builtin import background_task
    return background_task.build(background_tasks, live_state)


def make_echo(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin import echo
    return echo.build()


def make_read_file(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin import read_file
    return read_file.build()


def make_grep_files(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin import grep_files
    return grep_files.build()


def make_glob_files(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin import glob_files
    return glob_files.build()


def make_write_file(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin import write_file
    return write_file.build()


def make_replace_in_file(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin.edit_tools import ReplaceInFileTool
    return ReplaceInFileTool()


def make_apply_patch(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin.edit_tools import ApplyPatchTool
    return ApplyPatchTool()


def make_read_write(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin.edit_tools import ReadWriteTool
    return ReadWriteTool()


def make_delete_file(ctx: Any, files: Any = None) -> ToolPlugin:
    from agent.capabilities.builtin.fs_tools import DeleteFileTool
    return DeleteFileTool(files.recycle if files is not None else None)


def make_file_ops(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin.fs_tools import FileOpsTool
    return FileOpsTool()


def make_file_undo(ctx: Any, files: Any = None) -> ToolPlugin:
    from agent.capabilities.builtin.fs_tools import FileUndoTool
    return FileUndoTool(files.backups if files is not None else None)


def make_run_command(ctx: Any, live_state: Any = None) -> ToolPlugin:
    from agent.capabilities.builtin.command_tools import RunCommandTool
    return RunCommandTool(live_state)


def make_python_inline(ctx: Any, live_state: Any = None) -> ToolPlugin:
    from agent.capabilities.builtin.command_tools import PythonInlineTool
    return PythonInlineTool(live_state)


def make_run_type(ctx: Any, live_state: Any = None) -> ToolPlugin:
    from agent.capabilities.tasks import RunTypeTool
    return RunTypeTool(live_state)


def make_todo_list(ctx: Any, live_state: Any = None) -> ToolPlugin:
    from agent.capabilities.tasks import TodoListTool
    return TodoListTool(live_state)


def make_user_confirm(ctx: Any) -> ToolPlugin:
    from agent.capabilities.tasks import UserConfirmTool
    return UserConfirmTool()


def make_approval_confirm(ctx: Any) -> ToolPlugin:
    from agent.capabilities.tasks import ApprovalConfirmTool
    return ApprovalConfirmTool()


def make_goal(ctx: Any, live_state: Any = None) -> ToolPlugin:
    from agent.capabilities.tasks import GoalTool
    return GoalTool(live_state)


def make_task_sleep(ctx: Any) -> ToolPlugin:
    from agent.capabilities.tasks.wake import TaskSleepTool
    return TaskSleepTool()


def make_task_schedule(ctx: Any) -> ToolPlugin:
    from agent.capabilities.tasks.wake import TaskScheduleTool
    return TaskScheduleTool()


def make_task_wake_cancel(ctx: Any) -> ToolPlugin:
    from agent.capabilities.tasks.wake import TaskWakeCancelTool
    return TaskWakeCancelTool()


def make_task_wake_list(ctx: Any) -> ToolPlugin:
    from agent.capabilities.tasks.wake import TaskWakeListTool
    return TaskWakeListTool()


def make_session_send(ctx: Any, mesh: Any = None) -> ToolPlugin:
    from agent.capabilities.builtin.session_tools import SessionSendTool
    return SessionSendTool(mesh)


def make_session_multisend(ctx: Any, mesh: Any = None) -> ToolPlugin:
    from agent.capabilities.builtin.session_tools import SessionMultisendTool
    return SessionMultisendTool(mesh)


def make_session_broadcast(ctx: Any, mesh: Any = None) -> ToolPlugin:
    from agent.capabilities.builtin.session_tools import SessionBroadcastTool
    return SessionBroadcastTool(mesh)


def make_session_create(ctx: Any, mesh: Any = None) -> ToolPlugin:
    from agent.capabilities.builtin.session_tools import SessionCreateTool
    return SessionCreateTool(mesh)


def make_session_list(ctx: Any, mesh: Any = None) -> ToolPlugin:
    from agent.capabilities.builtin.session_tools import SessionListTool
    return SessionListTool(mesh)


def make_find_in_file(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin.locate_tools import FindInFileTool
    return FindInFileTool()


def make_subagent(ctx: Any, subagents: Any = None) -> ToolPlugin:
    from agent.capabilities.builtin.subagent_tools import SubagentTool
    return SubagentTool(subagents)


def make_subagent_send(ctx: Any, subagents: Any = None) -> ToolPlugin:
    from agent.capabilities.builtin.subagent_tools import SubagentSendTool
    return SubagentSendTool(subagents)


def make_text_diff(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin.text_data_tools import TextDiffTool
    return TextDiffTool()


def make_executors(ctx: Any, files: Any = None) -> Any:
    """构造提交执行器表：写入宿主既有的执行器注册表。"""
    from agent.capabilities.builtin import (
        archive_tool,
        edit_tools,
        fs_tools,
        web_tools,
        write_file,
    )
    host = ctx.boot_config.host_config
    backups = files.backups if files is not None else None
    recycle = files.recycle if files is not None else None
    executors = {}
    executors.update(write_file.build_executors(backups))
    executors.update(edit_tools.build_executors(backups))
    executors.update(fs_tools.build_executors(backups, recycle))
    executors.update(archive_tool.build_executors())
    executors.update(web_tools.build_executors())
    registry = host.executors
    for name, fn in executors.items():
        registry.add(name, fn, "host")
    return executors


def make_commit_write(ctx: Any, executors: Any = None) -> ToolPlugin:
    from agent.capabilities.builtin import commit_write
    return commit_write.build(executors, ctx.boot_config.host_config.executors)


def make_review_conclusion(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin import review_conclusion
    return review_conclusion.build()


def make_present(ctx: Any) -> ToolPlugin:
    from agent.capabilities.builtin import present_tool
    return present_tool.build()


__all__ = [name for name in globals() if name.startswith("make_")]
