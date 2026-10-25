# -*- coding: utf-8 -*-
"""一趟模块链的上下文生命周期协议。

持有可注入源快照的对象（如 `ContextPipeline`）实现本协议；
模块经公开属性 `context_pass` 暴露它，由 `chain._Pass` 在趟边界调用。
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PassLifecycle(Protocol):
    """一趟开始 / 结束时收集与丢弃注入源快照。"""

    def begin_pass(self) -> None:
        """本趟链开始：收集注入源快照。"""
        ...

    def end_pass(self) -> None:
        """本趟链结束：丢掉注入源快照。"""
        ...
