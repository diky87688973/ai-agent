# -*- coding: utf-8 -*-
"""SSE 传输层。

## 边界

本模块只管一件事：把事件变成 SSE 帧、可靠地送到若干个订阅连接。
它不认识会话、路由、适配层 —— 那些留在 `web.py`。
本模块的失效模式（慢消费者丢帧、空闲心跳、关闭语义）
自成一类，可以独立测、独立改。

## 背压设计

`_Channel` 是有界队列：慢消费者丢最旧的帧、保最新的。
理由：`EventSource` 断线会自动重连，重连后靠 `Last-Event-ID` 续传 ——
所以"丢中间几帧但保住最新状态"比"卡住整条广播"对用户更有利。

"""
from __future__ import annotations

import json
import queue
from typing import Optional

from agent.core import events as ev


def _event_seq(event: ev.Event) -> Optional[int]:
    """取事件的存储坐标 `_seq`（无则 None）。

    它由 `App.session` 的落盘旁路标进载荷——存储坐标，不是事件语义，
    所以放在 `data` 里，不给 `Event` 加字段。
    """
    raw = (getattr(event, "data", None) or {}).get("_seq")
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        return None
    return raw


def _sse_payload(event: ev.Event) -> str:
    """事件 → SSE 数据帧（`data: {json}\\n\\n`；载荷统一信封 type + data）。

    有存储坐标时额外发一行 `id: <seq>` —— 这是 SSE 协议原生的续传游标：
    浏览器 `EventSource` 断线重连会把最后收到的 id 作为 `Last-Event-ID` 请求头带回，
    服务端据此从该位置之后继续，而不是重放全部或丢弃中间那段。
    """
    try:
        body = json.dumps(
            {"type": event.type, **dict(event.data or {})}, ensure_ascii=False, default=str
        )
    except (TypeError, ValueError):
        body = json.dumps(
            {"type": event.type, "conversation_id": "", "_serialize_error": True},
            ensure_ascii=False,
        )
    seq = _event_seq(event)
    if seq is None:
        return f"data: {body}\n\n"
    return f"id: {seq}\ndata: {body}\n\n"


class _Channel:
    """一条 SSE 连接：独占队列 + 关闭信号（线程安全）。"""

    def __init__(self, maxsize: int = 2000) -> None:
        self.queue: "queue.Queue[Optional[str]]" = queue.Queue(maxsize=maxsize)
        self._closed = False

    def push(self, frame: str) -> None:
        if self._closed:
            return
        try:
            self.queue.put_nowait(frame)
        except queue.Full:
            # 慢消费者：丢弃最旧一帧后重试，保证流不因前端卡顿而断
            try:
                self.queue.get_nowait()
                self.queue.put_nowait(frame)
            except (queue.Empty, queue.Full):
                pass

    def close(self) -> None:
        self._closed = True
        try:
            self.queue.put_nowait(None)
        except queue.Full:
            pass

    def next_frame(self, timeout: float) -> Optional[str]:
        if self._closed:
            return None
        try:
            item = self.queue.get(timeout=max(0.05, float(timeout)))
        except queue.Empty:
            return ": keep-alive\n\n"  # 心跳帧（SSE 注释行，前端忽略）
        return item
