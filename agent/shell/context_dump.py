# -*- coding: utf-8 -*-
"""开发者上下文导出：按生产装配重建某个会话的完整请求，不调用模型。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from agent.core.session_log import SessionLog
from agent.mechanisms.context import ContextPipeline
from agent.shell.service_keys import SERVICE_RUNNER


def build_snapshot(app: Any, conversation_id: str, *,
                   include_tools: bool = False) -> Dict[str, Any]:
    """重建会话最近一次请求的完整上下文；只读会话事实，不调用模型。"""
    cid = str(conversation_id or "").strip()
    if not cid:
        raise ValueError("conversation_id 不能为空")
    store = getattr(app, "store", None)
    if store is None or not hasattr(store, "load"):
        raise RuntimeError("当前装配没有可读取的会话存储")
    events = list(store.load(cid))
    if not events:
        raise ValueError(f"会话不存在或没有事实：{cid}")

    runner = app.context.get(SERVICE_RUNNER)
    system_prompt = str(runner._system_prompt(cid))
    mode_note = str(runner._mode_note(cid))

    dialogue = SessionLog(events=events).derive_request_messages()
    compactor = None
    factory = getattr(app, "compactor_factory", None)
    if callable(factory):
        compactor = factory(cid)
        if compactor is not None:
            compactor.restore_from_events(events)

    context_factory = getattr(app, "context_factory", None)
    if callable(context_factory):
        context = context_factory(cid)
    else:
        context = ContextPipeline(
            cid,
            sources=getattr(app, "context_sources", None),
            **(dict(getattr(app, "context_defaults", None) or {})),
        )
    if context is None:
        raise RuntimeError("当前装配没有上下文管线工厂")
    context.append_system(system_prompt)
    if compactor is not None:
        context.set_summary_messages(compactor.summary_messages())
    covered_end = int(getattr(compactor, "covered_end", 0) or 0)
    context.set_dialogue(dialogue, covered_end=covered_end)
    tail = [{"role": "system", "content": mode_note}] if mode_note.strip() else []
    messages = context.assembles(tail)

    registry = getattr(app, "registry", None)
    schemas = list(registry.schemas()) if registry is not None else []
    snapshot: Dict[str, Any] = {
        "conversation_id": cid,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "model": str(app.model_for(cid) or ""),
        "event_count": len(events),
        "covered_end": covered_end,
        "system_prompt": system_prompt,
        "mode_note": mode_note,
        "messages": messages,
        "segments": [
            {"key": key, "label": label, "count": int(count)}
            for key, label, count in context.plugin_segments()
        ],
        "tools_count": len(schemas),
        "tools": schemas if include_tools else [],
    }
    return snapshot


def render_text(snapshot: Dict[str, Any]) -> str:
    """把快照渲染成便于人工检查的纯文本。"""
    lines = [
        f"# Context: {snapshot.get('conversation_id', '')}",
        f"generated_at: {snapshot.get('generated_at', '')}",
        f"model: {snapshot.get('model', '')}",
        f"events: {snapshot.get('event_count', 0)}",
        f"covered_end: {snapshot.get('covered_end', 0)}",
        f"tools: {snapshot.get('tools_count', 0)}",
        "",
        "## 分段",
    ]
    for segment in snapshot.get("segments") or []:
        lines.append(f"- {segment.get('label', '')}: {segment.get('count', 0)}")
    lines.extend(["", "## 系统提示词", str(snapshot.get("system_prompt", ""))])
    lines.extend(["", "## 模式尾部", str(snapshot.get("mode_note", ""))])
    lines.extend(["", "## 消息"])
    _append_messages(lines, snapshot.get("messages") or [])
    return "\n".join(lines).rstrip() + "\n"


def _append_messages(lines: List[str], messages: List[Dict[str, Any]]) -> None:
    for index, message in enumerate(messages):
        role = str(message.get("role") or "")
        content = message.get("content")
        if isinstance(content, list):
            content = _content_blocks(content)
        lines.extend([f"===== MESSAGE {index} role={role} =====", str(content or "")])


def _content_blocks(blocks: List[Any]) -> str:
    out: List[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            out.append(str(block))
            continue
        if block.get("type") == "image_url":
            out.append("[image]")
        else:
            out.append(str(block.get("text") or block.get("content") or ""))
    return "\n".join(part for part in out if part)
