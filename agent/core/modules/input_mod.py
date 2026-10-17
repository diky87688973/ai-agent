# -*- coding: utf-8 -*-
"""输入模块：认领本轮用户输入。"""
from __future__ import annotations

from typing import Any, Dict, Iterator, Optional, Sequence

from agent.core.event_name import INPUT_CLAIMED, INPUT_ENDED, INPUT_STARTED
from agent.core.module import ModuleBase
from agent.core.outcome import Outcome
from agent.core.ports import Ports


class InputModule(ModuleBase):
    """把本轮的**新用户输入**认领成事实。

    - 有输入：发 `input_claimed`，返回 `ok`（链上后面的模型模块自己会看到"末端是新输入"）；
    - **无输入**：什么都不发，返回 `ok`。

    第二点是硬要求：接口确认触发的恢复轮**没有用户发言**，此时上下文末端
    就该是那次工具调用——凭空发一条空的 `input_claimed` 会让消息序列变成
    `…assistant(tool_calls) → user("") → tool`，模型 API 直接拒绝（400）。

    **不要求续行**：这条链的模型模块在同**趟**里就会跑（它看事实末端）。若这里返回
    `next`，宿主会多跑一整趟空链（`passes` 从 1 变 2）。
    """

    name = "input"

    def __init__(self, text: str = "",
                 attachments: Optional[Sequence[Dict[str, Any]]] = None) -> None:
        self._text = str(text or "")
        self._attachments = list(attachments or [])

    def feed(self, text: str, attachments: Optional[Sequence[Dict[str, Any]]] = None) -> None:
        """投喂一轮新输入（壳层在每轮开始前调用）。"""
        self._text = str(text or "")
        self._attachments = list(attachments or [])

    def execute(self, ports: Ports) -> Iterator[Any]:
        if not self._text and not self._attachments:
            # 无输入 = 无用户消息（不是"跳过"，是"没有"）。**仍发终态**：
            # 监听者要能配对上"这次调用结束了"，而不是猜"它到底跑没跑"。
            yield ports.emit(INPUT_ENDED, claimed=False)
            return Outcome.ok()
        text, attachments = self._text, self._attachments
        self._text, self._attachments = "", []      # 消费掉，本趟之后就没有新输入了
        from time import perf_counter
        started = perf_counter()
        yield ports.emit(INPUT_STARTED, length=len(text),
                         attachments=len(attachments))
        if attachments:
            yield ports.emit(INPUT_CLAIMED, content=text, attachments=attachments)
        else:
            yield ports.emit(INPUT_CLAIMED, content=text)
        yield ports.emit(INPUT_ENDED, claimed=True,
                         elapsed_ms=int((perf_counter() - started) * 1000))
        return Outcome.ok()


# ══════════════════════════════════════════════════════════════════════
# 二、压缩模块
# ══════════════════════════════════════════════════════════════════════
