# -*- coding: utf-8 -*-
"""run_type 工具。"""
from __future__ import annotations

from typing import Any, Dict

from agent.capabilities.registry import ToolPlugin
from agent.core.session_scope import current_session_id
from agent.mechanisms.live_state import LiveState


class RunTypeTool(ToolPlugin):
    """查询 / 切换会话运行模式。"""

    name = "run_type"
    label = "切换运行模式"
    icon = "🎛️"
    description = "查询或切换会话运行模式（auto / plan / execute）；不传 `run_type` 为查询当前模式。"
    parameters = {
        "run_type": {"type": "string", "description": "auto / plan / execute；缺省为查询"},
    }

    def __init__(self, live_state: LiveState) -> None:
        self._state = live_state

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        cid = current_session_id()
        if not cid:
            raise ValueError("run_type 须由宿主注入 conversation_id 后执行；禁止无会话上下文直调")
        rt = str(arguments.get("run_type") or "").strip().lower()
        if not rt or rt not in ("auto", "plan", "execute"):
            return {"run_type": self._state.get_mode(cid), "action": "query"}
        return {"run_type": self._state.set_mode(cid, rt), "action": "switch"}
