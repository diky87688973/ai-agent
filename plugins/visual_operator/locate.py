# -*- coding: utf-8 -*-
"""文本定位端口：把「按文字找控件」从坐标原语里分出来。

定位结果只携带控件矩形与可点击点；点击/输入仍走既有鼠标、键盘端口，
因此输入锁、Plan 门控与动作回执不需要第二套实现。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Sequence

from .coords import ScreenPoint, ScreenRect


@dataclass(frozen=True)
class LocatorMatch:
    """一个命中的控件；`source` 只允许 `uia`。"""

    name: str
    control_type: str
    rect: ScreenRect
    clickable: Optional[ScreenPoint] = None
    source: str = "uia"
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "control_type": self.control_type,
            "rect": self.rect.to_dict(),
            "clickable": self.clickable.to_dict() if self.clickable else None,
            "source": self.source,
            "confidence": self.confidence,
        }


class LocatorPort(Protocol):
    """按窗口和文字找控件。没有 UIA 的平台不提供这个端口。"""

    def find(self, hwnd: Optional[int], text: str, match: str,
             limit: int) -> Sequence[LocatorMatch]:
        ...
