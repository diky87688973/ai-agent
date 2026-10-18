# -*- coding: utf-8 -*-
"""Plan 模式门控：会改变桌面的动作在 Plan 模式下拒绝。

截屏与只读查询不走这里：它们不改变任何状态，Plan 模式下照常可用。
"""
from __future__ import annotations

from typing import Any

from agent.core.session_scope import current_session_id
from agent.mechanisms.live_state import ModeConflict


def reject_in_plan(live_state: Any, action: str) -> None:
    """`live_state` 可以是实例，也可以是返回实例的可调用（插件装载时内核还没装配）。

    两者都拿不到时不拦：门控依赖会话状态，状态缺席时按非 Plan 处理。
    """
    state = live_state() if callable(live_state) else live_state
    if state is None:
        return
    conversation_id = current_session_id()
    if conversation_id and state.get_mode(conversation_id) == "plan":
        raise ModeConflict(
            f"Plan 模式下禁止{action}（可先 run_type 切回 auto / execute）"
        )
