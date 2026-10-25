# -*- coding: utf-8 -*-
"""子会话初始化：fresh 空历史与 fork 已完成回合前缀。"""
from __future__ import annotations

from typing import Iterable, List

from agent.core.events import Event, make_event
from agent.mechanisms.session_store import SessionStore


def completed_turn_prefix(events: Iterable[Event]) -> List[Event]:
    """取最后一个 turn_ended 及其之前的完整回合；没有则空。"""
    rows = list(events)
    end = -1
    for index, event in enumerate(rows):
        if str(getattr(event, "type", "")) == "turn_ended":
            end = index
    if end < 0:
        return []
    return rows[: end + 1]


def _copy_event(event: Event) -> Event:
    data = dict(event.data or {})
    data.pop("_seq", None)
    data.pop("conversation_id", None)
    if str(event.type).startswith("subagent/"):
        return make_event("subagent/skipped")
    return Event(type=str(event.type), data=data)


def seed_child(
    parent_store: SessionStore,
    child_store: SessionStore,
    *,
    child_id: str,
    parent_cid: str,
    batch: str,
    label: str,
    context: str,
) -> int:
    """写入子会话的 created 元数据与可选父会话前缀，返回写入事件数。"""
    if context not in ("fork", "fresh"):
        raise ValueError("context 必须是 fork 或 fresh")
    marker = make_event(
        "subagent/created",
        parent_cid=str(parent_cid),
        batch=str(batch),
        label=str(label),
        context=str(context),
    )
    child_store.append(child_id, [marker])
    if context == "fresh":
        return 1
    prefix = completed_turn_prefix(parent_store.load(parent_cid))
    copied = [_copy_event(event) for event in prefix]
    copied = [event for event in copied if event.type != "subagent/skipped"]
    if copied:
        child_store.append(child_id, copied)
    return 1 + len(copied)
