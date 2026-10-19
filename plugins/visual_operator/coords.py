# -*- coding: utf-8 -*-
"""屏幕几何：矩形、点、裁剪与比例换算。

工具层与后端之间只交换屏幕像素坐标。窗口系统的点、Retina 的物理像素
都收在后端里；这里的 `pixel_ratio` 只描述「截图一像素对应多少指针单位」。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ScreenPoint:
    """屏幕像素坐标上的一个点。"""

    x: int
    y: int

    def to_dict(self) -> Dict[str, int]:
        return {"x": self.x, "y": self.y}


@dataclass(frozen=True)
class ScreenRect:
    """屏幕像素坐标上的矩形；`right` / `bottom` 为开区间边界。"""

    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"矩形宽高必须为正：{self.width}x{self.height}")

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def contains(self, point: ScreenPoint) -> bool:
        return self.x <= point.x < self.right and self.y <= point.y < self.bottom

    def intersect(self, other: "ScreenRect") -> Optional["ScreenRect"]:
        """两个矩形的交集；不相交返回 None。"""
        left = max(self.x, other.x)
        top = max(self.y, other.y)
        right = min(self.right, other.right)
        bottom = min(self.bottom, other.bottom)
        if right <= left or bottom <= top:
            return None
        return ScreenRect(left, top, right - left, bottom - top)

    def to_dict(self) -> Dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass(frozen=True)
class ScreenGeometry:
    """截图像素空间与指针坐标系的关系。"""

    rect: ScreenRect
    #: 截图一像素对应的指针单位数：Windows 为 1，macOS Retina 为 2
    pixel_ratio: float = 1.0
    #: 生效的 DPI 档位或 Retina 描述，进返回值供排障
    dpi: str = ""
    #: 多屏缩放不一致时为 True，跨屏坐标可能有偏差
    mixed_scale: bool = False

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = self.rect.to_dict()
        data["pixel_ratio"] = round(self.pixel_ratio, 4)
        data["dpi"] = self.dpi
        data["mixed_scale"] = self.mixed_scale
        return data
