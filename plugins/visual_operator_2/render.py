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


def crop_padded(image: Image.Image, rect: dict) -> Image.Image:
    width = max(1, int(rect["width"]))
    height = max(1, int(rect["height"]))
    output = Image.new("RGB", (width, height), (0, 0, 0))
    left = max(0, int(rect["x"]))
    top = max(0, int(rect["y"]))
    right = min(image.width, int(rect["x"]) + width)
    bottom = min(image.height, int(rect["y"]) + height)
    if right <= left or bottom <= top:
        return output
    patch = image.crop((left, top, right, bottom))
    output.paste(patch, (left - int(rect["x"]), top - int(rect["y"])))
    return output


def model_point_screen(screen_width: int, screen_height: int, x: int, y: int,
                       width: int, height: int,
                       image_width: int, image_height: int) -> dict:
    scale_x = (image_width / float(width)) * (screen_width / float(image_width))
    scale_y = (image_height / float(height)) * (screen_height / float(image_height))
    screen_x = round(int(x) * scale_x)
    screen_y = round(int(y) * scale_y)
    return {
        "screen": {
            "x": max(0, min(screen_width - 1, screen_x)),
            "y": max(0, min(screen_height - 1, screen_y)),
        },
        "screen_size": [screen_width, screen_height],
        "scale": {"x": scale_x, "y": scale_y},
    }


def resolve_focus(frame, _explicit, width: int, height: int) -> dict:
    cx, cy = frame.cursor
    width = max(1, int(width))
    height = max(1, int(height))
    x = cx - width // 2
    y = cy - height // 2
    if frame.image.width >= width:
        x = max(0, min(frame.image.width - width, x))
    if frame.image.height >= height:
        y = max(0, min(frame.image.height - height, y))
    return {"x": x, "y": y, "width": width, "height": height}


def full_point_screen(screen_width: int, screen_height: int, x: int, y: int,
                      center_x: int, center_y: int, image_width: int,
                      image_height: int) -> dict:
    center_x = max(1, int(center_x))
    center_y = max(1, int(center_y))
    scale_x = float(image_width) / (2.0 * center_x)
    scale_y = float(image_height) / (2.0 * center_y)
    screen_x = image_width / 2.0 + (int(x) - center_x) * scale_x
    screen_y = image_height / 2.0 + (int(y) - center_y) * scale_y
    return {
        "screen": {
            "x": max(0, min(int(image_width) - 1, round(screen_x))),
            "y": max(0, min(int(image_height) - 1, round(screen_y))),
        },
        "screen_size": [int(image_width), int(image_height)],
        "image_center": [center_x, center_y],
        "scale": {"x": scale_x, "y": scale_y},
    }


def draw_marker(image: Image.Image, point: Tuple[int, int]) -> None:
    x, y = int(point[0]), int(point[1])
    draw = ImageDraw.Draw(image)
    color = (255, 230, 0)
    gap = 4
    arm = 16
    radius = 18
    draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                 outline=(0, 0, 0), width=5)
    draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                 outline=color, width=3)
    for line in (
        ((x - arm, y, x - gap, y), 4, (0, 0, 0)),
        ((x + gap, y, x + arm, y), 4, (0, 0, 0)),
        ((x, y - arm, x, y - gap), 4, (0, 0, 0)),
        ((x, y + gap, x, y + arm), 4, (0, 0, 0)),
        ((x - arm, y, x - gap, y), 2, color),
        ((x + gap, y, x + arm, y), 2, color),
        ((x, y - arm, x, y - gap), 2, color),
        ((x, y + gap, x, y + arm), 2, color),
    ):
        coords, width, fill = line
        draw.line(coords, fill=fill, width=width)


def data_url(image: Image.Image, config: VisionConfig) -> str:
    buf = io.BytesIO()
    image.save(buf, format=config.image_format,
               quality=config.image_quality) if config.image_format != "PNG" else image.save(
                   buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    mime = "image/" + config.image_format.lower()
    return f"data:{mime};base64,{encoded}"


__all__ = ["clip_focus", "crop_padded", "data_url", "draw_marker", "fit",
           "full_point_screen", "model_point_screen", "resolve_focus", "zoom"]
