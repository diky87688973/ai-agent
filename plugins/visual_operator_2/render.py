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
    """把聚焦区域裁到屏幕内；裁剪后小于 10×10 返回 None。"""
    screen_w, screen_h = max(1, int(screen_size[0])), max(1, int(screen_size[1]))
    x = max(0, min(screen_w - 1, int(region["x"])))
    y = max(0, min(screen_h - 1, int(region["y"])))
    right = max(x, min(screen_w, int(region["x"]) + int(region["width"])))
    bottom = max(y, min(screen_h, int(region["y"]) + int(region["height"])))
    width, height = right - x, bottom - y
    if width < 10 or height < 10:
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


def focus_screen_from_model(screen_width: int, screen_height: int,
                            x: int, y: int, width: int, height: int,
                            center_x: int, center_y: int,
                            image_width: int, image_height: int) -> Optional[dict]:
    center_x = max(1, int(center_x))
    center_y = max(1, int(center_y))
    width = int(width)
    height = int(height)
    if width <= 0 or height <= 0:
        return None
    scale_x = float(image_width) / (2.0 * center_x)
    scale_y = float(image_height) / (2.0 * center_y)
    left = image_width / 2.0 + (int(x) - center_x) * scale_x
    top = image_height / 2.0 + (int(y) - center_y) * scale_y
    return clip_focus({
        "x": round(left), "y": round(top),
        "width": max(1, round(width * scale_x)),
        "height": max(1, round(height * scale_y)),
    }, (screen_width, screen_height))


def focus_point_screen(focus: dict, x: int, y: int,
                       width: int, height: int) -> dict:
    width = max(1, int(width))
    height = max(1, int(height))
    return {
        "x": round(int(focus["x"]) + int(x) * int(focus["width"]) / float(width)),
        "y": round(int(focus["y"]) + int(y) * int(focus["height"]) / float(height)),
        "scale": {
            "x": float(focus["width"]) / float(width),
            "y": float(focus["height"]) / float(height),
        },
    }


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


def targets_for_points(frame, points, center_x: int, center_y: int,
                       image_width: int, image_height: int) -> list:
    targets = []
    for point in points:
        mapped = full_point_screen(
            frame.image.width, frame.image.height,
            int(point["x"]), int(point["y"]),
            center_x, center_y, image_width, image_height)
        targets.append({"model_point": {
            "x": int(point["x"]), "y": int(point["y"])},
            "screen": mapped["screen"]})
    return targets


def draw_marker(image: Image.Image, point: Tuple[int, int]) -> None:
    x, y = int(point[0]), int(point[1])
    draw = ImageDraw.Draw(image)
    color = (255, 230, 0)
    gap = 3
    arm = 8
    radius = 9
    draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                 outline=(0, 0, 0), width=3)
    draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                 outline=color, width=2)
    for line in (
        ((x - arm, y, x - gap, y), 3, (0, 0, 0)),
        ((x + gap, y, x + arm, y), 3, (0, 0, 0)),
        ((x, y - arm, x, y - gap), 3, (0, 0, 0)),
        ((x, y + gap, x, y + arm), 3, (0, 0, 0)),
        ((x - arm, y, x - gap, y), 2, color),
        ((x + gap, y, x + arm, y), 2, color),
        ((x, y - arm, x, y - gap), 2, color),
        ((x, y + gap, x, y + arm), 2, color),
    ):
        coords, width, fill = line
        draw.line(coords, fill=fill, width=width)


def draw_challenge(image: Image.Image, challenge, screen_width: int,
                   screen_height: int) -> None:
    if challenge is not None:
        draw_calibration(image, challenge["screen"], screen_width, screen_height)


def draw_calibration(image: Image.Image, points, screen_width: int,
                     screen_height: int) -> None:
    draw = ImageDraw.Draw(image)
    scale_x = image.width / float(max(1, screen_width))
    scale_y = image.height / float(max(1, screen_height))
    for index, (sx, sy) in enumerate(points, 1):
        x, y = round(sx * scale_x), round(sy * scale_y)
        radius = 10
        draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                     outline=(0, 0, 0), width=3)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                     outline=(0, 220, 255), width=2)
        draw.line((x - 14, y, x - 4, y), fill=(0, 0, 0), width=3)
        draw.line((x + 4, y, x + 14, y), fill=(0, 0, 0), width=3)
        draw.line((x, y - 14, x, y - 4), fill=(0, 0, 0), width=3)
        draw.line((x, y + 4, x, y + 14), fill=(0, 0, 0), width=3)
        draw.text((x + 14, y - 24), f"C{index}", fill=(0, 0, 0),
                  stroke_width=3, stroke_fill=(0, 0, 0))
        draw.text((x + 14, y - 24), f"C{index}", fill=(0, 220, 255))


def focus_view(image: Image.Image, focus: dict, cursor: Tuple[int, int],
               config: VisionConfig) -> dict:
    local = image.crop((
        focus["x"], focus["y"],
        focus["x"] + focus["width"], focus["y"] + focus["height"],
    ))
    cursor_in_focus = (
        focus["x"] <= cursor[0] < focus["x"] + focus["width"]
        and focus["y"] <= cursor[1] < focus["y"] + focus["height"]
    )
    if cursor_in_focus:
        draw_marker(local, (cursor[0] - focus["x"], cursor[1] - focus["y"]))
    data = {**focus, "image_size": [local.width, local.height]}
    label = "FOCUS FRAME"
    return {
        "image": local,
        "url": data_url(local, config),
        "cursor_in_focus": cursor_in_focus,
        "focus": data,
        "label": label,
    }


def data_url(image: Image.Image, config: VisionConfig) -> str:
    buf = io.BytesIO()
    image.save(buf, format=config.image_format,
               quality=config.image_quality) if config.image_format != "PNG" else image.save(
                   buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    mime = "image/" + config.image_format.lower()
    return f"data:{mime};base64,{encoded}"


__all__ = ["clip_focus", "crop_padded", "data_url", "draw_calibration",
           "draw_challenge",
           "draw_marker", "fit",
           "focus_point_screen", "focus_screen_from_model", "focus_view",
           "full_point_screen", "model_point_screen", "resolve_focus",
           "targets_for_points", "zoom"]
