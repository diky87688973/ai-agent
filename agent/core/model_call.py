# -*- coding: utf-8 -*-
"""模型调用协议：流帧契约。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from agent.core.tool_call import ToolCallRequest


@dataclass(slots=True)
class StreamDelta:
 """归一化流帧：kind 取 "text" | "reasoning" | "tool_call" | "usage"。

 - "text"：正文增量（text 承载）；
 - "reasoning"：推理增量（text 承载；thinking 模式要求随消息回传）；
 - "tool_call"：归并完成的工具调用（tool_call 承载）；
 - "usage"：用量结算（usage 承载）。
 """

 kind: str
 text: str = ""
 tool_call: Optional[ToolCallRequest] = None
 usage: Optional[Dict[str, Any]] = None
