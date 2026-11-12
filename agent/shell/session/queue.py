# -*- coding: utf-8 -*-
"""会话待发送队列访问。"""
from __future__ import annotations

import sys
from typing import Any, Dict

from agent.core.error_report import report_error
from agent.core.event_name import ERROR, INPUT_CLAIMED
from agent.core.events import Event
from agent.core.modules.queued_input_mod import input_claim_payload, insertion_waiting


def queue_of(app: Any) -> Any:
    return getattr(app, "conversation_queue", None)


def claim(cid: str, app: Any) -> Any:
    queue = queue_of(app)
    return queue.claim_after_turn(cid) if queue is not None else None


def release(cid: str, item: Dict[str, Any], app: Any) -> None:
    queue = queue_of(app)
    if queue is not None:
        queue.release(cid, str(item.get("id") or ""))


def complete(cid: str, item: Dict[str, Any], app: Any) -> None:
    queue = queue_of(app)
    if queue is not None:
        queue.complete(cid, str(item.get("id") or ""))


def input_of(item: Dict[str, Any]) -> Any:
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    content = str(item.get("content") or payload.get("content") or "")
    attachments = item.get("attachments") or payload.get("attachments")
    if isinstance(attachments, list):
        attachments = [row for row in attachments
                       if not isinstance(row, dict) or "data_base64" in row]
    meta = {key: payload[key] for key in (
        "kind", "source", "notice_id", "batch", "wake_job_id", "due_at",
        "goal_round", "goal_limit", "_confirmation_resume")
            if key in payload}
    return content, attachments, payload.get("resume"), (
        item.get("sender") if isinstance(item.get("sender"), dict) else None
    ), meta


def has_input(app: Any, cid: str, text: str, attachments: Any, resuming: bool) -> bool:
    return bool(text or attachments or resuming or insertion_waiting(queue_of(app), cid))


def notify_insert_failure(app: Any, cid: str) -> None:
    bus = getattr(app, "event_bus", None)
    if bus is None or not insertion_waiting(queue_of(app), cid):
        return
    try:
        bus.publish(Event(ERROR, {
            "conversation_id": cid, "where": "inbox",
            "detail": "插入消息暂未写入会话，已保留在 Inbox，可重试。",
        }))
    except Exception as exc:
        report_error("shell.session.queue.notify_insert_failure", exc, conversation_id=cid)


def claim_inserts(cid: str, app: Any, *, before_item_id: str) -> list:
    """认领全部排队的插入消息（不在模块链里时用）。"""
    q = queue_of(app)
    batch = getattr(q, "claim_insert_batch", None) if q is not None else None
    return list(batch(cid, resume_all=True, before_item_id=before_item_id)) if callable(batch) else []


def persist_inputs(cid: str, app: Any, store: Any, items: list) -> list[Event]:
    """Acknowledge only after the ordered input facts are durably available."""
    events = [
        Event(INPUT_CLAIMED, {
            **input_claim_payload(item), "conversation_id": cid, "_queue_item_id": item["id"],
        })
        for item in items
    ]

    def missing(existing: list, batch: list) -> list:
        recorded = {row.data.get("_queue_item_id") for row in existing if row.type == INPUT_CLAIMED}
        return [event for event in batch if event.data["_queue_item_id"] not in recorded]

    store.append_if_absent(cid, lambda _events: False, events,
                           retry_pending=False, select_missing=missing,
                           lookup={"kind": INPUT_CLAIMED, "items": tuple(item["id"] for item in items)})
    bus = getattr(app, "event_bus", None)
    written = []
    for item, event in zip(items, events, strict=True):
        try:
            complete(cid, item, app)
        except Exception as exc:
            report_error("shell.session.queue.complete_input", exc, conversation_id=cid)
        if "_seq" not in event.data:
            continue
        written.append(event)
        if bus is not None:
            try:
                bus.publish(event)
            except Exception as exc:
                report_error("shell.session.queue.publish_input", exc, conversation_id=cid)
    return written


def is_user_input(item: Any) -> bool:
    return bool(item and (item.get("payload") or {}).get("_inbox_user_send"))


def commit_user_input(cid: str, app: Any, store: Any, current: Dict[str, Any], *, batch: bool) -> None:
    backlog = claim_inserts(cid, app, before_item_id=current["id"]) if batch else []
    try:
        persist_inputs(cid, app, store, [*backlog, current])
    except Exception:
        for item in backlog:
            release(cid, item, app)
        raise


def flush_pending(cid: str, app: Any) -> None:
    store = getattr(app, "store", None)
    flusher = getattr(store, "flush_pending", None)
    if not cid or not callable(flusher):
        return
    try:
        written = flusher(cid)
    except Exception as exc:
        report_error("agent.shell.session.queue.flush_pending", exc)
        return
    if written:
        print(f"[session_runner] 补投了 {written} 条先前落盘失败的事实 "
              f"（cid={cid}）", file=sys.stderr, flush=True)
