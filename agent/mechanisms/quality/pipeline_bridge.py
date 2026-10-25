# -*- coding: utf-8 -*-
"""工具管道桥接（id 制）：把 gate 挂到 ToolPipeline 的 pre / post 钩子。"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Tuple

from agent.core.session_scope import current_session_id
from agent.core.tool_call import (
    GateDecision,
    PostObserver,
    PreGate,
    ToolCallRequest,
    ToolResult,
)
from agent.mechanisms.quality.checks import WriteContext
from agent.mechanisms.quality.diagnose import build_quality_report
from agent.mechanisms.quality.gate import QualityGate


def _mode_decision(live_state: Any) -> Optional[GateDecision]:
    if live_state is None:
        return None
    conv = current_session_id()
    mode = live_state.get_mode(conv) if conv else "auto"
    if mode == "plan":
        return GateDecision(
            allow=False,
            reason="ModeConflict：Plan 模式下禁止写盘（可先 run_type 切回 auto / execute）")
    if mode == "execute" and not live_state.has_active_todo(conv):
        return GateDecision(
            allow=False,
            reason="ModeConflict：Execute 模式写盘前须先创建非空执行清单（todo_list create）")
    return None


def _post_preview(call: ToolCallRequest, result: ToolResult,
                  session_gate: QualityGate) -> None:
    if isinstance(result.data, dict) and result.data.get("needs_commit", True):
        cid = session_gate.register_preview(call.name, dict(call.arguments))
        result.data["confirm_id"] = cid


def _post_commit(call: ToolCallRequest, result: ToolResult,
                 session_gate: QualityGate, info: dict, needs_reread: Any) -> None:
    if not isinstance(result.data, dict):
        return
    path = str(result.data.get("path") or "")
    if not path:
        return
    tool = str(info.get("tool") or "")
    session_gate.note_committed(
        path, diff_text=str(result.data.pop("_diff", "") or ""), tool=tool,
        reread=needs_reread(tool))
    result.data["host_quality"] = build_quality_report(session_gate, path)


def build_pipeline_gate(
    *,
    registry: Any,
    sessions: Any,
    live_state: Any = None,
    commit_tools: Iterable[str] = ("commit_write",),
    read_tools: Iterable[str] = ("read_file",),
) -> Tuple[PreGate, PostObserver]:
    """构建挂 ToolPipeline 的门控钩子（id 制四步）。"""
    if registry is None:
        raise ValueError("build_pipeline_gate 需要 registry")
    if sessions is None:
        raise ValueError("build_pipeline_gate 需要 sessions")
    commit_names = tuple(commit_tools)
    read_names = tuple(read_tools)
    pending: Dict[str, Dict[str, str]] = {}

    def plugin(name: str) -> Any:
        return registry.get(name)

    def is_preview(name: str) -> bool:
        found = plugin(name)
        return bool(found is not None and getattr(found, "needs_preview", False))

    def needs_reread(name: str) -> bool:
        found = plugin(name)
        return bool(found is not None and getattr(found, "needs_reread", False))

    def gate_for(ctx: Any) -> QualityGate:
        session = getattr(ctx, "session", None) if ctx is not None else None
        resolved = getattr(session, "gate", None) if session is not None else None
        if resolved is not None:
            return resolved
        cid = str(getattr(ctx, "conversation_id", "") or "") if ctx is not None else ""
        return sessions.resolve_sync(cid).gate

    def pre(call: ToolCallRequest, ctx: Any) -> Optional[GateDecision]:
        if call.name not in commit_names:
            return None
        blocked = _mode_decision(live_state)
        if blocked is not None:
            return blocked
        cid = str(call.arguments.get("confirm_id") or "")
        session_gate = gate_for(ctx)
        decision = session_gate.check_write(WriteContext(confirm_id=cid))
        if not decision.allow:
            return decision
        record = session_gate.peek(cid) or {}
        pending[call.call_id] = {"tool": str(record.get("tool") or "")}
        return None

    def post(call: ToolCallRequest, result: ToolResult, ctx: Any) -> None:
        info = pending.pop(call.call_id, None)
        if not result.ok:
            return
        session_gate = gate_for(ctx)
        if is_preview(call.name):
            _post_preview(call, result, session_gate)
        elif call.name in commit_names:
            _post_commit(call, result, session_gate, info or {}, needs_reread)
        elif call.name in read_names:
            path = str(call.arguments.get("path") or "")
            if path:
                session_gate.note_read(path)

    return pre, post
