# -*- coding: utf-8 -*-
"""background_task：按会话管理后台进程。"""
from __future__ import annotations

from typing import Any, Dict

from agent.capabilities.builtin.command_tools import reject_in_plan_mode
from agent.capabilities.registry import ToolPlugin
from agent.core.session_scope import current_session_id
from agent.mechanisms.background_tasks import BackgroundTaskManager


class BackgroundTaskTool(ToolPlugin):
    """创建、查询、取消后台任务并读取输出。"""

    name = "background_task"
    label = "后台任务"
    icon = "▣"
    description = (
        "管理本会话的后台命令任务。action=create 创建并入队，list 查看队列，"
        "cancel 取消，output 读取未读输出。任务超时包含排队与执行。"
    )
    parameters = {
        "action": {
            "type": "string",
            "enum": ["create", "list", "cancel", "output"],
            "description": "create / list / cancel / output",
        },
        "argv": {
            "type": "array",
            "items": {"type": "string"},
            "description": "命令参数数组（create 必填，不经 shell；例如 python -c print(1) 拆成三个参数）",
        },
        "cwd": {"type": "string", "description": "工作目录（可选）"},
        "timeout_sec": {
            "type": "integer",
            "description": "从创建时刻开始的总超时秒数（create 必填，1..86400）",
        },
        "label": {"type": "string", "description": "任务小标题（create 必填，用于工具壳展示；允许同名）"},
        "batch": {"type": "string", "description": "批次号；create 可选（传回执 batch 可加入同批），list 必填"},
        "task_id": {"type": "string", "description": "任务 ID（cancel / output 必填；list 可用于精确查询）"},
        "reason": {"type": "string", "description": "取消原因（cancel 可选）"},
        "status": {"type": "string", "description": "list 的状态过滤（可选）"},

        "wait": {"type": "boolean", "description": "output 是否等待终态（可选）"},
        "timeout_ms": {
            "type": "integer",
            "description": "output 等待上限毫秒数（可选，默认 30000）",
        },
    }

    def __init__(self, manager: BackgroundTaskManager, live_state: Any = None) -> None:
        self._manager = manager
        self._live_state = live_state

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        cid = str(current_session_id() or "").strip()
        if not cid:
            raise ValueError("缺少当前会话 id")
        action = str(arguments.get("action") or "").strip().lower()
        if action == "create":
            reject_in_plan_mode(self._live_state, "后台任务执行")
            return self._manager.create(
                cid,
                arguments.get("argv"),  # type: ignore[arg-type]
                cwd=str(arguments.get("cwd") or ""),
                timeout_sec=arguments.get("timeout_sec"),  # type: ignore[arg-type]
                label=str(arguments.get("label") or ""),
                batch=str(arguments.get("batch") or ""),
            )
        if action == "list":
            return self._manager.list_tasks(
                cid,
                str(arguments.get("batch") or ""),
                task_id=str(arguments.get("task_id") or ""),
                status=str(arguments.get("status") or ""),
            )
        if action == "cancel":
            return self._manager.cancel(
                cid,
                str(arguments.get("task_id") or ""),
                str(arguments.get("reason") or ""),
            )
        if action == "output":
            return self._manager.output(
                cid,
                str(arguments.get("task_id") or ""),
                wait=bool(arguments.get("wait", False)),
                timeout_ms=int(arguments.get("timeout_ms") or 30_000),
            )
        raise ValueError("action 必须是 create / list / cancel / output")


def build(manager: BackgroundTaskManager, live_state: Any = None) -> BackgroundTaskTool:
    return BackgroundTaskTool(manager, live_state)
