# -*- coding: utf-8 -*-
"""工具侧读取当前会话门控的唯一入口。"""
from __future__ import annotations

from agent.mechanisms.quality import QualityGate


def session_gate() -> QualityGate:
    """取当前工具调用的会话门控；必须经 ToolPort.execute 注入 session。"""
    from agent.core.session_scope import current_context

    ctx = current_context()
    session = getattr(ctx, "session", None) if ctx is not None else None
    gate = getattr(session, "gate", None)
    if gate is None:
        raise ValueError(
            "取不到会话门控：须经 ToolPort.execute（管道上下文填入 session）调用"
        )
    return gate
