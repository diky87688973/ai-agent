# -*- coding: utf-8 -*-
"""目标与自主续跑判定。"""
from __future__ import annotations

from typing import Any, Callable, Optional

from agent.core.error_report import report_error

AUTO_CONTINUE_PROMPT = (
    "（自主模式）请继续推进未完成的工作；若已全部完成或需要用户决策，"
    "请直接给出结论并停止，不要再调用工具。"
)


def next_continuation_text(*, cid: str,
                           goal_row: Optional[Callable[[str], Any]] = None,
                           auto_continue: Optional[Callable[[str], bool]] = None) -> str:
    """目标优先；没有目标才看自主开关。"""
    if goal_row is not None:
        row = goal_row(cid)
        if isinstance(row, dict):
            if str(row.get("status") or "") != "active":
                return ""
            return str(row.get("text") or "").strip()
    if auto_continue is not None and bool(auto_continue(cid)):
        return AUTO_CONTINUE_PROMPT
    return ""


def note_round(app: Any, cid: str) -> None:
    state = getattr(app, "live_state", None)
    note = getattr(state, "note_goal_round", None)
    if not callable(note):
        return
    try:
        note(cid)
    except Exception as exc:
        # 计数只用于展示，记不上不影响续跑。
        report_error("agent.shell.session.goal.note_round", exc)
