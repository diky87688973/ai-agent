# -*- coding: utf-8 -*-
"""模型提供者协议与错误类型。"""
from __future__ import annotations

from typing import Any, Iterator

from agent.core.model_call import StreamDelta


class ModelRequestError(Exception):
    """模型请求失败：detail 面向用户，status 保留上游 HTTP 状态。"""

    def __init__(self, detail: str, *, status: int = 0) -> None:
        super().__init__(detail)
        self.detail = str(detail or "")
        self.status = int(status or 0)


class ModelProvider:
    """提供者协议（替换点）：实现 `stream(request) -> Iterator[StreamDelta]`。"""

    def stream(self, request: Any) -> Iterator[StreamDelta]:
        raise NotImplementedError
