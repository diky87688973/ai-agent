# -*- coding: utf-8 -*-
"""安全插入点：把队列中标记为插入的消息写成一条输入事实。"""
from __future__ import annotations

from typing import Any, Iterator

from agent.core.event_name import INPUT_CLAIMED
from agent.core.module import ModuleBase
from agent.core.outcome import Outcome
from agent.core.ports import Ports


class QueuedInputModule(ModuleBase):
    """在压缩前消费一条插入请求；不消费回合结束队列。"""

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
        item = self._queue.claim_insert(cid)
        if not isinstance(item, dict):
            return Outcome.ok()
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
            sender = item.get("sender")
            if isinstance(sender, dict) and str(sender.get("cid") or "").strip():
                payload["_sender"] = str(sender.get("cid") or "").strip()
                name = str(sender.get("name") or "").strip()
                if name:
                    payload["_sender_name"] = name
            yield ports.emit(INPUT_CLAIMED, **payload)
        except Exception:
            self._queue.release(cid, item_id)
            raise
        else:
            self._queue.complete(cid, item_id)
        return Outcome.ok()
