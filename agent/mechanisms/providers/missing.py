# -*- coding: utf-8 -*-
"""未配置模型时的占位 provider。"""
from __future__ import annotations

from typing import Any, Iterator

from agent.core.model_call import StreamDelta
from agent.mechanisms.providers.base import ModelProvider, ModelRequestError


class MissingProvider(ModelProvider):
    """没有任何可用模型时的占位：报错文案不提插件目录（内核不认插件名）。"""

    model = ""

    def stream(self, request: Any) -> Iterator[StreamDelta]:
        raise ModelRequestError("未配置任何模型")
        yield  # pragma: no cover - 生成器形状，永不产出
