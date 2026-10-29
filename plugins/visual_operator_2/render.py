# -*- coding: utf-8 -*-
"""视觉操作 2.0 的图像加工：缩放、屏幕坐标辅助线、鼠标标记与编码。"""
from __future__ import annotations

import base64
import io
from typing import Optional, Tuple

from PIL import Image, ImageDraw

from .config import VisionConfig


def fit(image: Image.Image, max_side: int) -> Image.Image:
    longest = max(image.width, image.height)
    if longest <= max_side:
        return image
    scale = max_side / float(longest)
    return image.resize((max(1, int(image.width * scale)),
                         max(1, int(image.height * scale))), Image.Resampling.LANCZOS)


def zoom(image: Image.Image, factor: float) -> Image.Image:
    if factor <= 1.0:
        return image
    return image.resize((max(1, int(image.width * factor)),
                         max(1, int(image.height * factor))), Image.Resampling.LANCZOS)


def clip_focus(region: dict, screen_size: Tuple[int, int]) -> Optional[dict]:
    """把聚焦区域裁到屏幕内；裁剪后小于 64×64 返回 None。"""
    screen_w, screen_h = max(1, int(screen_size[0])), max(1, int(screen_size[1]))
    x = max(0, min(screen_w - 1, int(region["x"])))
    y = max(0, min(screen_h - 1, int(region["y"])))
    right = max(x, min(screen_w, int(region["x"]) + int(region["width"])))
    bottom = max(y, min(screen_h, int(region["y"]) + int(region["height"])))
    width, height = right - x, bottom - y
    if width < 64 or height < 64:
        return None
    return {"x": x, "y": y, "width": width, "height": height}


def draw_marker(image: Image.Image, point: Tuple[int, int]) -> None:
    x, y = int(point[0]), int(point[1])
    draw = ImageDraw.Draw(image)
    draw.ellipse((x - 9, y - 9, x + 9, y + 9), outline=(255, 60, 60), width=2)
    draw.line((x - 14, y, x + 14, y), fill=(255, 60, 60), width=1)
    draw.line((x, y - 14, x, y + 14), fill=(255, 60, 60), width=1)
    draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(255, 220, 60))


def data_url(image: Image.Image, config: VisionConfig) -> str:
    buf = io.BytesIO()
    image.save(buf, format=config.image_format,
               quality=config.image_quality) if config.image_format != "PNG" else image.save(
                   buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    mime = "image/" + config.image_format.lower()
    return f"data:{mime};base64,{encoded}"


__all__ = ["clip_focus", "data_url", "draw_marker", "fit", "zoom"]
