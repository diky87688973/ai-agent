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
    label = "后台异步执行命令"
    icon = "▣"
    description = (
        "异步创建后台命令任务，立即返回 task_id，用 list / output / cancel 管理。"
        "适合长任务、服务、并行或需轮询取消的命令；短命令用 run_command。argv 不经过 shell。"
    )
    parameters = {
        "action": {
            "type": "string",
            "enum": ["create", "list", "cancel", "output"],
            "description": "create 创建；list 查看；cancel 取消；output 读取输出",
        },
        "argv": {
            "type": "array",
            "items": {"type": "string"},
            "description": "命令参数数组；不经 shell，不支持管道和重定向；create 必填",
        },
        "cwd": {"type": "string", "description": "工作目录；可选"},
        "timeout_sec": {
            "type": "integer",
            "description": "从创建时刻起的总超时秒数，1..86400；create 必填",
        },
        "label": {"type": "string", "description": "任务短标题；create 必填"},
        "batch": {"type": "string", "description": "批次号；create 可选，list 必填"},
        "task_id": {"type": "string", "description": "任务 ID；cancel/output 必填，list 可精确查询"},
        "reason": {"type": "string", "description": "取消原因；cancel 可选"},
        "status": {"type": "string", "description": "list 状态过滤"},

        "wait": {"type": "boolean", "description": "output 是否等待终态；默认 false"},
        "timeout_ms": {
            "type": "integer",
            "description": "output 等待上限毫秒，默认 30000",
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
