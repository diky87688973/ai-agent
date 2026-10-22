# -*- coding: utf-8 -*-
"""会话待发送队列访问。"""
from __future__ import annotations

import sys
from typing import Any, Dict


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
    return content, attachments, payload.get("resume"), (
        item.get("sender") if isinstance(item.get("sender"), dict) else None
    )


def flush_pending(cid: str, app: Any) -> None:
    store = getattr(app, "store", None)
    flusher = getattr(store, "flush_pending", None)
    if not cid or not callable(flusher):
        return
    try:
        written = flusher(cid)
    except Exception as exc:
        print(f"[session_runner] 待重试事实补投失败 cid={cid}: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return
    if written:
        print(f"[session_runner] 补投了 {written} 条先前落盘失败的事实 "
              f"（cid={cid}）", file=sys.stderr, flush=True)
