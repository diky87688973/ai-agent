# -*- coding: utf-8 -*-
"""桌面后端的三条端口与数据结构。

工具只依赖这些协议；平台实现放在 `backends/` 下，按平台选择。
坐标一律是工具契约里的屏幕坐标（Windows 物理像素，macOS 显示点），
后端直接以该坐标系投递输入。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Sequence

from .coords import ScreenGeometry, ScreenPoint, ScreenRect


@dataclass(frozen=True)
class Screenshot:
    """一张原始截图：PNG 字节与它覆盖的屏幕矩形。"""

    png: bytes
    rect: ScreenRect


class ScreenPort(Protocol):
    """截屏与屏幕几何。"""

    def geometry(self) -> ScreenGeometry:
        """当前虚拟桌面的矩形与比例。"""
        ...

    def capture(self, region: Optional[ScreenRect]) -> Screenshot:
        """截取区域；`region` 为 None 时截取整屏。"""
        ...


class MousePort(Protocol):
    """鼠标动作；坐标是屏幕像素。"""

    def cursor(self) -> ScreenPoint:
        ...

    def move(self, point: ScreenPoint, duration_ms: int) -> None:
        ...

    def click(self, point: Optional[ScreenPoint], button: str, count: int) -> None:
        ...

    def drag(self, start: ScreenPoint, end: ScreenPoint, button: str,
             duration_ms: int) -> None:
        ...

    def scroll(self, point: Optional[ScreenPoint], amount: int, horizontal: bool) -> None:
        ...


class KeyboardPort(Protocol):
    """键盘动作；键名是 `keys.py` 的规范名。"""

    def type_text(self, text: str, interval_ms: int) -> None:
        ...

    def press(self, key: str, repeat: int) -> None:
        ...

    def hotkey(self, keys: Sequence[str], repeat: int) -> None:
        ...


@dataclass(frozen=True)
class Backend:
    """一套可用的后端；平台不支持时换成三个只会报错的端口。"""

    platform: str
    screen: ScreenPort
    mouse: MousePort
    keyboard: KeyboardPort
