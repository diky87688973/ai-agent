# -*- coding: utf-8 -*-
"""唤醒调度工具：注册、取消、查询，不在工具内等待。"""
from __future__ import annotations

from typing import Any, Dict

from agent.capabilities.registry import ToolPlugin
from agent.core.context import SERVICE_WAKE_SCHEDULER
from agent.core.session_scope import current_context, current_session_id


def _scheduler() -> Any:
    ctx = current_context()
    app = getattr(ctx, "app", None) if ctx is not None else None
    has = getattr(app, "has", None)
    getter = getattr(app, "get", None)
    if not callable(has) or not callable(getter) or not has(SERVICE_WAKE_SCHEDULER):
        raise RuntimeError("唤醒调度器未装配")
    return getter(SERVICE_WAKE_SCHEDULER)


def _owner() -> str:
    cid = current_session_id()
    if not cid:
        raise RuntimeError("唤醒调度需要当前会话")
    return str(cid)


def _target(arguments: Dict[str, Any]) -> str:
    return str(arguments.get("target_cid") or "").strip() or _owner()


class TaskSleepTool(ToolPlugin):
    name = "task_sleep"
    label = "定时唤醒"
    icon = "⏰"
    description = (
        "注册一个相对时间的唤醒任务，立即返回 job_id，不阻塞当前回合。"
        "到期后宿主向目标会话投递 reminder，目标空闲则启动回合，忙碌则进入队列。"
        "不要用本工具等待结果，也不要在工具内 sleep。"
    )
    parameters = {
        "seconds": {"type": "number", "description": "延迟秒数，必须大于 0"},
        "reminder": {"type": "string", "description": "到期投递的提醒内容"},
        "target_cid": {"type": "string",
                       "description": "目标会话 id；缺省为当前会话"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return _scheduler().schedule_seconds(
            arguments.get("seconds"),
            target_cid=_target(arguments),
            owner_cid=_owner(),
            reminder=str(arguments.get("reminder") or ""),
        )


class TaskScheduleTool(ToolPlugin):
    name = "task_schedule"
    label = "定时唤醒"
    icon = "⏰"
    description = (
        "注册一个绝对时间的唤醒任务，立即返回 job_id，不阻塞当前回合。"
        "at 使用带时区的 ISO 8601；无时区按宿主本地时区解释。"
        "已过期时间会被拒绝，不会静默改成立即执行。"
    )
    parameters = {
        "at": {"type": "string",
               "description": "ISO 8601 时间，例如 2026-10-28T09:00:00+08:00"},
        "reminder": {"type": "string", "description": "到期投递的提醒内容"},
        "target_cid": {"type": "string",
                       "description": "目标会话 id；缺省为当前会话"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return _scheduler().schedule_at(
            arguments.get("at"),
            target_cid=_target(arguments),
            owner_cid=_owner(),
            reminder=str(arguments.get("reminder") or ""),
        )


class TaskWakeCancelTool(ToolPlugin):
    name = "task_wake_cancel"
    label = "取消唤醒"
    icon = "⏰"
    description = "取消一个尚未到期的唤醒任务；已终态的任务保持不变。"
    parameters = {
        "job_id": {"type": "string", "description": "task_sleep / task_schedule 返回的 job_id"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return _scheduler().cancel(
            str(arguments.get("job_id") or ""), owner_cid=_owner())


class TaskWakeListTool(ToolPlugin):
    name = "task_wake_list"
    label = "唤醒任务"
    icon = "⏰"
    description = "列出当前会话或指定目标会话的唤醒任务，按到期时间排序。"
    parameters = {
        "target_cid": {"type": "string",
                       "description": "目标会话 id；缺省为当前会话"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        target = _target(arguments)
        return {"jobs": _scheduler().list_jobs(
            target_cid=target, owner_cid=_owner())}


def build_plugins() -> list[ToolPlugin]:
    return [TaskSleepTool(), TaskScheduleTool(),
            TaskWakeCancelTool(), TaskWakeListTool()]
