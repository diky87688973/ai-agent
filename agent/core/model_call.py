# -*- coding: utf-8 -*-
"""模型调用协议：流帧契约。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from agent.core.tool_call import ToolCallRequest

#: 厂商私有元数据的键名。内核不解释其内容，只在事实与 assistant 消息之间透传；
#: 读写两侧都引用这个常量，避免各写一遍字符串（P6）。
PROVIDER_META_KEY = "provider_meta"


@dataclass(slots=True)
class StreamDelta:
    """归一化流帧：kind 取 "text" | "reasoning" | "tool_call" | "usage" | "meta"。

    - "text"：正文增量（text 承载）；
    - "reasoning"：推理增量（text 承载；thinking 模式要求随消息回传）；
    - "tool_call"：归并完成的工具调用（tool_call 承载）；
    - "usage"：用量结算（usage 承载）；
    - "meta"：厂商私有元数据（meta 承载，内核只透传不解释）。
    """

    kind: str
    text: str = ""
    tool_call: Optional[ToolCallRequest] = None
    usage: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None
