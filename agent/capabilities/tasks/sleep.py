# -*- coding: utf-8 -*-
"""task_sleep 工具。"""
from __future__ import annotations

from typing import Any, Dict

from agent.capabilities.registry import ToolPlugin
from agent.core.session_scope import current_session_id
from agent.mechanisms.live_state import LiveState


class TaskSleepTool(ToolPlugin):
    """自主休眠指令：校验 + 信封 + 会话状态记录。"""

    name = "task_sleep"
    label = "等待"
    icon = "⏱️"
    description = "暂停自主执行：宿主停止自动激活，N 秒后携提醒重新激活（1~86400 秒）。"
    parameters = {
        "seconds": {"type": "integer", "description": "休眠秒数（1~86400）"},
        "reminder": {"type": "string", "description": "唤醒提醒（≤500 字符，超出截断）"},
    }

    def __init__(self, live_state: LiveState) -> None:
        self._state = live_state

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw = arguments.get("seconds")
        seconds = 0
        if isinstance(raw, (int, float, str)):
            try:
                seconds = int(raw)
            except (TypeError, ValueError):
                seconds = 0
            if seconds <= 0:
                seconds = 0
        if seconds < 1 or seconds > 86400:
            raise ValueError(f"seconds 必须在 1~86400 之间，收到 {seconds}")
        reminder = arguments.get("reminder", "")
        if not isinstance(reminder, str):
            reminder = str(reminder)
        if len(reminder) > 500:
            reminder = reminder[:500]
        cid = current_session_id()
        if cid:
            self._state.set_sleep(cid, seconds, reminder)
        return {"action": "sleep", "seconds": seconds, "reminder": reminder}
