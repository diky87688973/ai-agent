# -*- coding: utf-8 -*-
"""输入模块：认领本轮用户输入。"""
from __future__ import annotations

from typing import Any, Dict, Iterator, Optional, Sequence

from agent.core.event_name import INPUT_CLAIMED, INPUT_ENDED, INPUT_STARTED
from agent.core.input_attachments import with_attachment_ids
from agent.core.module import ModuleBase
from agent.core.outcome import Outcome
from agent.core.ports import Ports


class InputModule(ModuleBase):
    """把本轮的新用户输入认领成事实。

    - 有输入：发 `input_claimed`，返回 `ok`（链上后面的模型模块自己会看到"末端是新输入"）；
    - 无输入：只发 `input_ended`（claimed=False），返回 `ok`。

    第二点是硬要求：接口确认触发的恢复轮没有用户发言，此时上下文末端
    就该是那次工具调用——凭空发一条空的 `input_claimed` 会让消息序列变成
    `…assistant(tool_calls) → user("") → tool`，模型 API 直接拒绝（400）。

    不要求续行：这条链的模型模块在同趟里就会跑（它看事实末端）。若这里返回
    `next`，宿主会多跑一整趟空链（`passes` 从 1 变 2）。
    """

    name = "input"

    def __init__(self, text: str = "",
                 attachments: Optional[Sequence[Dict[str, Any]]] = None) -> None:
        self._text = str(text or "")
        self._attachments = list(attachments or [])
        self._sender: Optional[Dict[str, Any]] = None
        self._from_queue = False
        self._meta: Dict[str, Any] = {}

    def feed(self, text: str, attachments: Optional[Sequence[Dict[str, Any]]] = None,
             sender: Optional[Dict[str, Any]] = None, from_queue: bool = False,
             meta: Any = None) -> None:
        """投喂一轮新输入（壳层在每轮开始前调用）。"""
        self._text = str(text or "")
        self._attachments = list(attachments or [])
        self._sender = dict(sender) if isinstance(sender, dict) else None
        self._from_queue = bool(from_queue)
        self._meta = dict(meta) if isinstance(meta, dict) else {}

    def execute(self, ports: Ports) -> Iterator[Any]:
        if not self._text and not self._attachments:
            # 无输入 = 无用户消息（不是"跳过"，是"没有"）。仍发终态：
            # 监听者要能配对上"这次调用结束了"，而不是猜"它到底跑没跑"。
            yield ports.emit(INPUT_ENDED, claimed=False)
            return Outcome.ok()
        text = self._text
        attachments = with_attachment_ids(self._attachments)
        sender = self._sender
        from_queue = self._from_queue
        meta = self._meta
        self._text, self._attachments, self._sender, self._from_queue, self._meta = "", [], None, False, {}
        from time import perf_counter
        started = perf_counter()
        yield ports.emit(INPUT_STARTED, length=len(text),
                         attachments=len(attachments))
        payload: Dict[str, Any] = {"content": text}
        if attachments:
            payload["attachments"] = attachments
        if sender:
            cid = str(sender.get("cid") or sender.get("_sender") or "").strip()
            if cid:
                payload["_sender"] = cid
                name = str(sender.get("name") or sender.get("_sender_name") or "").strip()
                if name:
                    payload["_sender_name"] = name
        if from_queue:
            payload["_from_queue"] = 1
        for key in ("kind", "source", "notice_id", "batch"):
            if meta.get(key):
                payload[key] = meta[key]
        yield ports.emit(INPUT_CLAIMED, **payload)
        yield ports.emit(INPUT_ENDED, claimed=True,
                         elapsed_ms=int((perf_counter() - started) * 1000))
        return Outcome.ok()
