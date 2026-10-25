# -*- coding: utf-8 -*-
"""Echo 假模型。"""
from __future__ import annotations

from typing import Any, Iterator
from uuid import uuid4

from agent.core.model_call import StreamDelta
from agent.core.tool_call import ToolCallRequest
from agent.mechanisms.providers.base import ModelProvider


class EchoProvider(ModelProvider):
    """假模型：首次请求发起 echo 工具调用；拿到工具结果后给出文本应答。

    用途：MVP 验证内核循环（模型→工具→回灌→再模型→结束），不依赖真实 API。
    """

    def stream(self, request: Any) -> Iterator[StreamDelta]:
        has_tool_result = any(m.get("role") == "tool" for m in request.messages)
        if not has_tool_result:
            yield StreamDelta(
                kind="tool_call",
                tool_call=ToolCallRequest(
                    call_id=f"call-{uuid4().hex[:8]}",
                    name="echo",
                    arguments={"text": "来自内核的第一次工具调用"},
                ),
            )
            return
        yield StreamDelta(kind="text", text="收到工具结果，")
        yield StreamDelta(kind="text", text="内核循环验证完成。")
