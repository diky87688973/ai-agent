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


def resolve_focus(frame, explicit, width: int, height: int) -> dict:
    if explicit is not None:
        return {**explicit}
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


def square_content(screen_width: int, screen_height: int, size: int) -> dict:
    scale = min(size / float(max(1, screen_width)),
                size / float(max(1, screen_height)))
    width = max(1, round(screen_width * scale))
    height = max(1, round(screen_height * scale))
    return {"x": (size - width) // 2, "y": (size - height) // 2,
            "width": width, "height": height}


def pad_to_square(image: Image.Image, size: int) -> tuple:
    content = square_content(image.width, image.height, size)
    canvas = Image.new("RGB", (size, size), (0, 0, 0))
    resized = image.resize((content["width"], content["height"]),
                           Image.Resampling.LANCZOS)
    canvas.paste(resized, (content["x"], content["y"]))
    return canvas, content


def full_point_screen(screen_width: int, screen_height: int, x: int, y: int,
                      width: int, height: int, size: int) -> dict:
    content = square_content(screen_width, screen_height, size)
    full_x = int(x) * size / float(width)
    full_y = int(y) * size / float(height)
    if (full_x < content["x"] or full_y < content["y"]
            or full_x > content["x"] + content["width"]
            or full_y > content["y"] + content["height"]):
        return {"outside": True, "content": content}
    screen_x = (full_x - content["x"]) / float(content["width"]) * screen_width
    screen_y = (full_y - content["y"]) / float(content["height"]) * screen_height
    return {
        "screen": {
            "x": max(0, min(screen_width - 1, round(screen_x))),
            "y": max(0, min(screen_height - 1, round(screen_y))),
        },
        "content": content,
        "screen_size": [screen_width, screen_height],
        "scale": {"x": screen_width / float(content["width"]),
                  "y": screen_height / float(content["height"])},
    }


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


__all__ = ["clip_focus", "crop_padded", "data_url", "draw_marker", "fit",
           "full_point_screen", "model_point_screen", "pad_to_square",
           "resolve_focus", "square_content", "zoom"]
