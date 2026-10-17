# -*- coding: utf-8 -*-
"""收件箱模块：把入站消息收进事实。"""
from __future__ import annotations

from typing import Any, Dict, Iterator

from agent.core.event_name import INBOX_DEQUEUED, INPUT_CLAIMED
from agent.core.module import ModuleBase
from agent.core.outcome import Outcome
from agent.core.ports import Ports


class InboxModule(ModuleBase):
    """会话消息队列：把别的会话投进来的消息，**在本轮开始前**收进上下文。

    位置在压缩之前：入站消息会变成新的用户轮次，压缩得看得见它们，
    否则"刚收到消息就按旧预算压缩"会把新消息挤掉。

    **从不要求续行**：这一模块只负责"把排队的消息搬进事实"，
    搬完就结束；要不要再问一次模型由链上的后续模块决定。
    队列为空是常态，此时不产生任何事件。
    """

    name = "inbox"
    requires = ("inbox",)

    def __init__(self, *, inbox: Any = None) -> None:
        #: 一个可调用对象：`(cid) -> Optional[dict]`，返回队首消息或 None。
        #: 由装配方注入（内核不认某个具体存储实现）。
        self._inbox = inbox

    def execute(self, ports: Ports) -> Iterator[Any]:
        if self._inbox is None:
            return Outcome.ok()
        cid = str(getattr(ports, "conversation_id", "") or "")
        if not cid:
            return Outcome.ok()
        received = 0
        while True:
            try:
                msg = self._inbox(cid)
            except Exception:
                # 判据：队列读失败不该打断回合 —— 消息还在（或已丢），
                # 但用户当前这一轮必须照常跑完。
                break
            if not isinstance(msg, dict):
                break
            text = str(msg.get("content") or "").strip()
            if not text:
                # 空消息（只有空白）没有可读内容：**直接丢弃并留痕**，
                # 不能既 pop 掉又装作收进来了 —— 那样队列少了消息却什么都没发生。
                yield ports.emit(INBOX_DEQUEUED, batch_count=0, dropped=1)
                continue
            # 入站消息就是**一条用户输入事实**：这样它自然进入模型可见消息序列，
            # 与用户手打的输入走同一条读规则。
            # 发送者字段由 `session_send` 写入，键名是 `_sender` / `_sender_name`
            # （下划线开头，与事实字段一致）。
            sender = str(msg.get("_sender") or msg.get("sender") or "").strip()
            payload: Dict[str, Any] = {"content": text}
            if sender:
                payload["_sender"] = sender
                name = str(msg.get("_sender_name") or "").strip()
                if name:
                    payload["_sender_name"] = name
            yield ports.emit(INPUT_CLAIMED, **payload)
            received += 1
        if received:
            yield ports.emit(INBOX_DEQUEUED, batch_count=received)
        return Outcome.ok()
