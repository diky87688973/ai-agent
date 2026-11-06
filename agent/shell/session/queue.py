# -*- coding: utf-8 -*-
"""会话待发送队列访问。"""
from __future__ import annotations

import sys
from typing import Any, Dict

from agent.core.error_report import report_error


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
        "goal_round", "goal_limit")
            if key in payload}
    return content, attachments, payload.get("resume"), (
        item.get("sender") if isinstance(item.get("sender"), dict) else None
    ), meta


def has_inserting(app: Any, cid: str) -> bool:
    q = queue_of(app)
    check = getattr(q, "has_inserting", None) if q is not None else None
    return bool(check(cid)) if callable(check) else False


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
