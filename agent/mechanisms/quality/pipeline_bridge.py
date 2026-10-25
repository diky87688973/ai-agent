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


def build_pipeline_gate(
    *,
    registry: Any,
    sessions: Any,
    live_state: Any = None,
    commit_tools: Iterable[str] = ("commit_write",),
    read_tools: Iterable[str] = ("read_file",),
) -> Tuple[PreGate, PostObserver]:
    """构建挂 ToolPipeline 的门控钩子（id 制四步：预览 → 确认 → 凭 ID 提交 → 重读）。

    `registry` / `sessions` 必填。预览判定只认工具元数据 `needs_preview`。
    会话门控取自 `ctx.session.gate`，否则 `sessions.resolve_sync(conversation_id).gate`。
    """
    if registry is None:
        raise ValueError("build_pipeline_gate 需要 registry")
    if sessions is None:
        raise ValueError("build_pipeline_gate 需要 sessions")
    commit_names = tuple(commit_tools)
    read_names = tuple(read_tools)
    pending_commits: Dict[str, Dict[str, str]] = {}  # call_id → {tool}

    def _plugin(name: str) -> Any:
        return registry.get(name)

    def _is_preview(name: str) -> bool:
        plugin = _plugin(name)
        return bool(plugin is not None and getattr(plugin, "needs_preview", False))

    def _needs_reread(name: str) -> bool:
        plugin = _plugin(name)
        return bool(plugin is not None and getattr(plugin, "needs_reread", False))

    def _gate(ctx: Any) -> QualityGate:
        session = getattr(ctx, "session", None) if ctx is not None else None
        resolved = getattr(session, "gate", None) if session is not None else None
        if resolved is not None:
            return resolved
        cid = str(getattr(ctx, "conversation_id", "") or "") if ctx is not None else ""
        return sessions.resolve_sync(cid).gate

    def pre(call: ToolCallRequest, ctx: Any) -> Optional[GateDecision]:
        if call.name not in commit_names:
            return None
        if live_state is not None:
            conv = current_session_id()
            mode = live_state.get_mode(conv) if conv else "auto"
            if mode == "plan":
                return GateDecision(
                    allow=False,
                    reason="ModeConflict：Plan 模式下禁止写盘（可先 run_type 切回 auto / execute）",
                )
            if mode == "execute" and not live_state.has_active_todo(conv):
                return GateDecision(
                    allow=False,
                    reason="ModeConflict：Execute 模式写盘前须先创建非空执行清单（todo_list create）",
                )
        cid = str(call.arguments.get("confirm_id") or "")
        session_gate = _gate(ctx)
        decision = session_gate.check_write(WriteContext(confirm_id=cid))
        if not decision.allow:
            return decision
        record = session_gate.peek(cid) or {}
        pending_commits[call.call_id] = {"tool": str(record.get("tool") or "")}
        return None

    def post(call: ToolCallRequest, result: ToolResult, ctx: Any) -> None:
        info = pending_commits.pop(call.call_id, None)
        if not result.ok:
            return
        session_gate = _gate(ctx)
        if _is_preview(call.name):
            if isinstance(result.data, dict) and result.data.get("needs_commit", True):
                cid = session_gate.register_preview(call.name, dict(call.arguments))
                result.data["confirm_id"] = cid
            return
        if call.name in commit_names:
            if not isinstance(result.data, dict):
                return
            path = str(result.data.get("path") or "")
            if not path:
                return
            tool = str((info or {}).get("tool") or "")
            session_gate.note_committed(
                path,
                diff_text=str(result.data.pop("_diff", "") or ""),
                tool=tool,
                reread=_needs_reread(tool),
            )
            report = build_quality_report(session_gate, path)
            result.data["host_quality"] = report
            return
        if call.name in read_names:
            path = str(call.arguments.get("path") or "")
            if path:
                session_gate.note_read(path)

    return pre, post
