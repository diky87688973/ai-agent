# -*- coding: utf-8 -*-
"""截图登记：只存坐标映射元数据，不存图片。

`desktop_eye` 把截图交给模型后，鼠标不能再要求模型做缩放与原点换算。
这里给每张图一个短期 ID，鼠标用 ID + 图内坐标查回屏幕矩形与图片尺寸，
由服务端完成换算。图片本身随工具结果发送，不进入本仓库，也不落盘。
"""
from __future__ import annotations

import math
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional

from .coords import ScreenPoint, ScreenRect

#: 每个插件实例最多保留多少张截图的映射；只存元数据，几十字节一张。
MAX_CAPTURES = 64
#: 映射有效期。截图过期不等于画面没变，但比用错图安全。
CAPTURE_TTL_SECONDS = 300.0


@dataclass(frozen=True)
class CaptureRef:
    """一张截图的屏幕矩形与模型看到的图片尺寸。"""

    capture_id: str
    session_id: str
    rect: ScreenRect
    image_width: int
    image_height: int
    created_at: float
    hwnd: Optional[int] = None
    title: str = ""

    def to_screen(self, image_x: float, image_y: float) -> ScreenPoint:
        """图内坐标 → 屏幕坐标；越出图片边界直接报错。"""
        try:
            x = float(image_x)
            y = float(image_y)
        except (TypeError, ValueError):
            raise ValueError(
                f"图内坐标必须是数字，实际 x={image_x!r} y={image_y!r}"
            ) from None
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError("图内坐标必须是有限数字")
        if not (0 <= x < self.image_width and 0 <= y < self.image_height):
            raise ValueError(
                f"图内坐标 ({x:g}, {y:g}) 超出截图 "
                f"{self.image_width}×{self.image_height}"
            )
        screen_x = self.rect.x + x * self.rect.width / self.image_width
        screen_y = self.rect.y + y * self.rect.height / self.image_height
        return ScreenPoint(int(round(screen_x)), int(round(screen_y)))

    def to_dict(self) -> Dict[str, object]:
        return {
            "capture_id": self.capture_id,
            "capture": self.rect.to_dict(),
            "image": {
                "width": self.image_width,
                "height": self.image_height,
            },
            "image_to_screen": {
                "scale_x": round(self.rect.width / self.image_width, 6),
                "scale_y": round(self.rect.height / self.image_height, 6),
                "ox": self.rect.x,
                "oy": self.rect.y,
            },
        }


class CaptureStore:
    """线程安全、有上限与 TTL 的内存登记表。"""

    def __init__(self, max_items: int = MAX_CAPTURES,
                 ttl_seconds: float = CAPTURE_TTL_SECONDS,
                 clock=time.monotonic) -> None:
        self._max_items = max(1, int(max_items))
        self._ttl_seconds = max(1.0, float(ttl_seconds))
        self._clock = clock
        self._items: Dict[str, CaptureRef] = {}
        self._lock = threading.Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def put(self, session_id: str, rect: ScreenRect,
            image_width: int, image_height: int, *,
            hwnd: Optional[int] = None, title: str = "") -> CaptureRef:
        """登记一张图；返回带 `capture_id` 的引用。"""
        width = int(image_width)
        height = int(image_height)
        if width <= 0 or height <= 0:
            raise ValueError(f"图片尺寸必须为正：{width}×{height}")
        now = float(self._clock())
        with self._lock:
            self._purge_locked(now)
            capture_id = self._new_id_locked()
            ref = CaptureRef(
                capture_id=capture_id,
                session_id=str(session_id or ""),
                rect=rect,
                image_width=width,
                image_height=height,
                created_at=now,
                hwnd=hwnd,
                title=str(title or ""),
            )
            self._items[capture_id] = ref
            while len(self._items) > self._max_items:
                oldest = min(self._items.values(), key=lambda item: item.created_at)
                self._items.pop(oldest.capture_id, None)
            return ref

    def resolve(self, session_id: str, capture_id: str) -> Optional[CaptureRef]:
        """按会话与 ID 取映射；不存在、过期或不属于该会话返回 None。"""
        key = str(capture_id or "").strip()
        if not key:
            return None
        now = float(self._clock())
        with self._lock:
            self._purge_locked(now)
            ref = self._items.get(key)
            if ref is None or ref.session_id != str(session_id or ""):
                return None
            return ref

    def _new_id_locked(self) -> str:
        while True:
            value = secrets.token_hex(6)
            if value not in self._items:
                return value

    def _purge_locked(self, now: float) -> None:
        expired = [
            key for key, item in self._items.items()
            if now - item.created_at > self._ttl_seconds
        ]
        for key in expired:
            self._items.pop(key, None)
