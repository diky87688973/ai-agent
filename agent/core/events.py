# -*- coding: utf-8 -*-
"""事件信封：一件事实的**数据形状**（类型 + 载荷）。

本模块是事件的数据形状；事件名是 `event_name.py` 的词汇表。两处分开是因为职责不同：
`event_name.py` 是纯词汇（零依赖），本模块是跨层共用的数据契约。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Event:
    """一件事实的信封：类型 + 载荷（载荷字段随类型而变）。"""

    type: str
    data: dict[str, Any] = field(default_factory=dict)


def make_event(type_: str, **data: Any) -> Event:
    """构造事件（唯一工厂，方便将来统一加工）。"""
    return Event(type=type_, data=dict(data))
