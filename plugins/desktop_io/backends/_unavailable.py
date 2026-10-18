# -*- coding: utf-8 -*-
"""不可用平台的后端：三个端口都只在调用时报错。

工具仍在注册表里：CI 与 Linux 上工具表保持稳定，模型看到的是明确的
「此平台不支持」而不是工具凭空消失。
"""
from __future__ import annotations

import sys
from typing import Optional, Sequence

from ..coords import ScreenGeometry, ScreenPoint, ScreenRect
from ..errors import DesktopUnavailable
from ..ports import Backend, Screenshot

_REASON = f"桌面 IO 在 {sys.platform} 上不可用（支持 Windows 与 macOS）"


class UnavailableScreen:
    def geometry(self) -> ScreenGeometry:
        raise DesktopUnavailable(_REASON)

    def capture(self, region: Optional[ScreenRect]) -> Screenshot:
        raise DesktopUnavailable(_REASON)


class UnavailableMouse:
    def cursor(self) -> ScreenPoint:
        raise DesktopUnavailable(_REASON)

    def move(self, point: ScreenPoint, duration_ms: int) -> None:
        raise DesktopUnavailable(_REASON)

    def click(self, point: Optional[ScreenPoint], button: str, count: int) -> None:
        raise DesktopUnavailable(_REASON)

    def drag(self, start: ScreenPoint, end: ScreenPoint, button: str,
             duration_ms: int) -> None:
        raise DesktopUnavailable(_REASON)

    def scroll(self, point: Optional[ScreenPoint], amount: int,
               horizontal: bool) -> None:
        raise DesktopUnavailable(_REASON)


class UnavailableKeyboard:
    def type_text(self, text: str, interval_ms: int) -> None:
        raise DesktopUnavailable(_REASON)

    def press(self, key: str, repeat: int) -> None:
        raise DesktopUnavailable(_REASON)

    def hotkey(self, keys: Sequence[str], repeat: int) -> None:
        raise DesktopUnavailable(_REASON)


def unavailable_backend() -> Backend:
    return Backend(platform=sys.platform, screen=UnavailableScreen(),
                   mouse=UnavailableMouse(), keyboard=UnavailableKeyboard())
