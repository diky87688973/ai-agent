# -*- coding: utf-8 -*-
"""安全插入点：把队列中积压的 Agent 消息一次性写成输入事实。"""
from __future__ import annotations

from typing import Any, Iterator

from agent.core.error_report import report_error
from agent.core.event_name import INPUT_CLAIMED
from agent.core.module import ModuleBase
from agent.core.outcome import Outcome
from agent.core.ports import Ports


class QueuedInputModule(ModuleBase):
    """在压缩前消费全部积压的 Agent 插入请求；不消费回合结束队列。"""

    name = "queued_input"
    requires = ()

    def __init__(self, *, queue: Any = None) -> None:
        self._queue = queue

    def execute(self, ports: Ports) -> Iterator[Any]:
        if self._queue is None:
            return Outcome.ok()
        cid = str(getattr(ports, "conversation_id", "") or "")
        if not cid:
            return Outcome.ok()
        batch = getattr(self._queue, "claim_insert_batch", None)
        if callable(batch):
            items = batch(cid)
        else:
            item = self._queue.claim_insert(cid)
            items = [item] if isinstance(item, dict) else []
        if not items:
            return Outcome.ok()
        for item in items:
            item_id = str(item.get("id") or "")
            try:
                payload: dict = {"content": str(item.get("content") or ""),
                                 "_from_queue": 1}
                attachments = [
                    row for row in (item.get("attachments") or [])
                    if isinstance(row, dict) and row.get("data_base64")
                ]
                if attachments:
                    payload["attachments"] = attachments
                meta = item.get("payload") if isinstance(item.get("payload"), dict) else {}
                for key in ("kind", "source", "notice_id", "batch"):
                    if meta.get(key):
                        payload[key] = meta[key]
                sender = item.get("sender")
                if isinstance(sender, dict) and str(sender.get("cid") or "").strip():
                    payload["_sender"] = str(sender.get("cid") or "").strip()
                    name = str(sender.get("name") or "").strip()
                    if name:
                        payload["_sender_name"] = name
                yield ports.emit(INPUT_CLAIMED, **payload)
            except Exception as exc:
                report_error("agent.core.modules.queued_input_mod.QueuedInputModule.execute", exc)
                self._queue.release(cid, item_id)
                raise
            else:
                self._queue.complete(cid, item_id)
        return Outcome.ok()
