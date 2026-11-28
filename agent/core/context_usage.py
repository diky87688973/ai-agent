# -*- coding: utf-8 -*-
"""模块与上下文之间的 token 计量能力面。

`ContextPipeline` 结构上满足本协议：模块只按协议调用，不再 `getattr` 探测。
只实现装配、不实现计量的替身会 `isinstance` 失败 —— 那表示"不提供校准"，
模块跳过校正，行为退回未校准状态，与协议缺失前一致。
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TokenCalibration(Protocol):
    """把上游用量回灌估算，让预算判据与真实规模对齐。"""

    def raw_total_token_estimate(self) -> int:
        """未经上游校准的估算和（校准比值本身按它计算）。"""
        ...

    def observe_usage(self, actual: int, estimated: int) -> float:
        """用上游 `prompt_tokens` 记一次比值，返回当前校准系数。"""
        ...
