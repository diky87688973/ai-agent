# -*- coding: utf-8 -*-
"""安全插入点：把队列中积压的插入消息一次性写成输入事实。"""
from __future__ import annotations

from typing import Any, Callable, Iterator

from agent.core.error_report import report_error
from agent.core.event_name import INPUT_CLAIMED
from agent.core.events import Event
from agent.core.input_attachments import with_attachment_ids
from agent.core.module import ModuleBase
from agent.core.outcome import Outcome
from agent.core.ports import Ports


def input_claim_payload(item: dict) -> dict:
    """队列项 → `input_claimed` 载荷。

    模块链与回合取消后的清账共用同一份构造，两边字段不能各自演化：
    字段不一致时同一条消息会因“由谁写入”不同而在模型眼里长得不一样。
    """
    payload: dict = {"content": str(item.get("content") or ""),
                     "_from_queue": 1}
    attachments = with_attachment_ids([
        row for row in (item.get("attachments") or [])
        if isinstance(row, dict) and row.get("data_base64")
    ])
    if attachments:
        payload["attachments"] = attachments
    meta = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    for key in ("kind", "source", "notice_id", "batch", "wake_job_id", "due_at",
                "goal_round", "goal_limit"):
        if meta.get(key):
            payload[key] = meta[key]
    sender = item.get("sender")
    if isinstance(sender, dict) and str(sender.get("cid") or "").strip():
        payload["_sender"] = str(sender.get("cid") or "").strip()
        name = str(sender.get("name") or "").strip()
        if name:
            payload["_sender_name"] = name
    return payload


def insertion_waiting(queue: Any, cid: str) -> bool:
    check = getattr(queue, "has_inserting", None)
    return bool(check(cid)) if callable(check) else False


class QueuedInputModule(ModuleBase):
    """在压缩前消费全部积压的插入请求；不消费回合结束队列。"""

    name = "queued_input"
    requires = ()

    def __init__(self, *, queue: Any = None,
                 commit: Callable[[str, list], list[Event]] | None = None) -> None:
        self._queue = queue
        self._commit = commit

    def execute(self, ports: Ports) -> Iterator[Any]:
        if self._queue is None:
            return Outcome.ok()
        if ports.canceled():
            return Outcome.stopped("用户请求停止")
        cid = ports.conversation_id
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
        if ports.canceled():
            self._release(cid, items)
            return Outcome.stopped("用户请求停止")
        if self._commit is not None:
            try:
                events = ports.integrate_external_facts(lambda: self._commit(cid, items))
            except Exception:
                self._release(cid, items)
                raise
            if events is None:
                self._release(cid, items)
                return Outcome.stopped("用户请求停止")
            yield from events
            return Outcome.ok()
        for index, item in enumerate(items):
            item_id = str(item.get("id") or "")
            try:
                yield ports.emit(INPUT_CLAIMED, **input_claim_payload(item))
            except Exception as exc:
                report_error("agent.core.modules.queued_input_mod.QueuedInputModule.execute", exc)
                # claim_insert_batch 已把整批移出队列；当前条与尚未处理的都要还回去，
                # 否则它们永远停在 claimed 状态，后续回合再也收不到。
                self._release(cid, items[index:])
                raise
            else:
                try:
                    self._queue.complete(cid, item_id)
                except Exception as exc:
                    report_error(
                        "agent.core.modules.queued_input_mod.QueuedInputModule.complete",
                        exc)
                    self._release(cid, items[index:])
                    raise
        return Outcome.ok()

    def _release(self, cid: str, items: list) -> None:
        for item in items:
            self._queue.release(cid, item["id"])
