# -*- coding: utf-8 -*-
"""任务与目标工具。"""
from __future__ import annotations

from typing import List

from agent.capabilities.registry import ToolPlugin
from agent.capabilities.tasks.confirm import ApprovalConfirmTool, UserConfirmTool
from agent.capabilities.tasks.goal import GoalTool
from agent.capabilities.tasks.run_type import RunTypeTool
from agent.capabilities.tasks.todo import TodoListTool
from agent.capabilities.tasks.wake import build_plugins as build_wake_plugins
from agent.mechanisms.live_state import LiveState


def build_plugins(live_state: LiveState) -> List[ToolPlugin]:
    """构造本组工具（run_type / todo_list / user_confirm / approval_confirm / goal / task_sleep / task_schedule / task_wake_cancel / task_wake_list）。"""
    return [
        RunTypeTool(live_state),
        TodoListTool(live_state),
        UserConfirmTool(),
        ApprovalConfirmTool(),
        GoalTool(live_state),
        *build_wake_plugins(),
    ]
