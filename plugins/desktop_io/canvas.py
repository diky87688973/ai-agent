# -*- coding: utf-8 -*-
"""截图加工：缩放、坐标网格、光标十字与 PNG 编码。

网格刻度写屏幕坐标值，绘制发生在缩放后的画布上：标签在最终尺寸下渲染，
缩图不会把刻度糊成小字，刻度含义也不随图片尺寸变化。
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from .coords import ScreenPoint, ScreenRect
from .errors import DesktopUnavailable, ScreenCaptureFailed

#: 每这么多条细线画一条带刻度的主线。
MAJOR_EVERY = 5
#: 细线间距小于该像素时只画主线，避免糊成一片。
MIN_MINOR_GAP = 8
#: 刻度字号范围（像素）。
FONT_MIN = 11
FONT_MAX = 16

_THIN_COLOR = (90, 200, 255, 70)
_MAJOR_COLOR = (255, 90, 90, 150)
_CURSOR_COLOR = (0, 255, 0, 235)
_SHADOW_COLOR = (0, 0, 0, 200)


@dataclass(frozen=True)
class Rendered:
    """加工后的图片与尺寸信息。"""

    png: bytes
    width: int
    height: int
    sent_width: int
    sent_height: int
    scale: float
    blank: bool

    @property
    def shrunk(self) -> bool:
        return self.sent_width != self.width or self.sent_height != self.height


def _pillow() -> Tuple[Any, Any, Any]:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise DesktopUnavailable(f"截图加工需要 Pillow：{exc}") from exc
    return Image, ImageDraw, ImageFont


def _is_blank(image: Any) -> bool:
    """三个通道的最大值全为 0：锁屏、安全桌面或受保护内容会得到这种图。"""
    return all(high == 0 for _low, high in image.getextrema())


def _font(image_font: Any, size: int) -> Any:
    try:
        return image_font.load_default(size=size)
    except TypeError:
        # Pillow 10.1 之前没有 size 参数，退回默认字号。
        return image_font.load_default()


def _text_size(draw: Any, text: str, font: Any) -> Tuple[int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top


def _draw_label(draw: Any, position: Tuple[int, int], text: str, font: Any,
                text_height: int, width: int, height: int,
                color: Tuple[int, int, int, int] = _MAJOR_COLOR) -> None:
    """在画布内画刻度文字，带一层深色描边。"""
    text_width, _ = _text_size(draw, text, font)
    x = max(2, min(int(position[0]), width - text_width - 2))
    y = max(2, min(int(position[1]), height - text_height - 2))
    draw.text((x + 1, y + 1), text, font=font, fill=_SHADOW_COLOR)
    draw.text((x, y), text, font=font, fill=color)


def _offset(origin: int, value: int, extent: int, pixels: int) -> int:
    """屏幕坐标 → 图片像素偏移；`extent` 是该轴的屏幕坐标跨度，`pixels` 是图片尺寸。"""
    return round((value - origin) * pixels / extent)


def _draw_overlay(image: Any, image_module: Any, image_draw: Any, image_font: Any, *,
                  rect: ScreenRect, step: int, grid: bool,
                  cursor: Optional[ScreenPoint]) -> None:
    """在图片上叠坐标网格与光标十字；刻度是屏幕坐标值。"""
    width, height = image.size
    step = max(1, int(step))
    base = image.convert("RGBA")
    canvas = image_module.new("RGBA", base.size, (0, 0, 0, 0))
    draw = image_draw.Draw(canvas)
    font = _font(image_font, max(FONT_MIN, min(FONT_MAX, round(width / 120))))
    text_height = _text_size(draw, "0", font)[1] + 2

    if grid:
        gap = step * width / rect.width
        show_minor = gap >= MIN_MINOR_GAP
        first = -(-rect.x // step)
        last = (rect.right - 1) // step
        for index in range(first, last + 1):
            major = index % MAJOR_EVERY == 0
            if not show_minor and not major:
                continue
            screen_x = index * step
            offset = _offset(rect.x, screen_x, rect.width, width)
            if 0 <= offset < width:
                draw.line([(offset, 0), (offset, height)],
                          fill=_MAJOR_COLOR if major else _THIN_COLOR,
                          width=2 if major else 1)
                if major:
                    _draw_label(draw, (offset + 3, 2), str(screen_x),
                                font, text_height, width, height)
                    _draw_label(draw, (offset + 3, height - text_height - 2),
                                str(screen_x), font, text_height, width, height)

        first = -(-rect.y // step)
        last = (rect.bottom - 1) // step
        for index in range(first, last + 1):
            major = index % MAJOR_EVERY == 0
            if not show_minor and not major:
                continue
            screen_y = index * step
            offset = _offset(rect.y, screen_y, rect.height, height)
            if 0 <= offset < height:
                draw.line([(0, offset), (width, offset)],
                          fill=_MAJOR_COLOR if major else _THIN_COLOR,
                          width=2 if major else 1)
                if major:
                    _draw_label(draw, (2, offset + 3), str(screen_y),
                                font, text_height, width, height)
                    _draw_label(draw, (width - 4 - _text_size(draw, str(screen_y), font)[0],
                                       offset + 3),
                                str(screen_y), font, text_height, width, height)

    if cursor is not None:
        cursor_x = _offset(rect.x, cursor.x, rect.width, width)
        cursor_y = _offset(rect.y, cursor.y, rect.height, height)
        if 0 <= cursor_x < width and 0 <= cursor_y < height:
            draw.line([(0, cursor_y), (width, cursor_y)], fill=_CURSOR_COLOR, width=1)
            draw.line([(cursor_x, 0), (cursor_x, height)], fill=_CURSOR_COLOR, width=1)
            _draw_label(draw, (cursor_x + 6, cursor_y + 6), f"{cursor.x},{cursor.y}",
                        font, text_height, width, height, color=(0, 255, 0, 245))

    image.paste(image_module.alpha_composite(base, canvas).convert("RGB"))


def render(png: bytes, *, rect: ScreenRect, grid: bool, step: int,
           cursor: Optional[ScreenPoint], cursor_mark: bool, max_side: int) -> Rendered:
    """把原始截图加工成要发给模型的那一张。"""
    Image, ImageDraw, ImageFont = _pillow()
    try:
        image = Image.open(io.BytesIO(png))
        image.load()
    except OSError as exc:
        raise ScreenCaptureFailed(f"截图数据无法解码：{exc}") from exc
    image = image.convert("RGB")
    width, height = image.size
    if width <= 0 or height <= 0:
        raise ScreenCaptureFailed("截图尺寸为空")
    blank = _is_blank(image)

    if max_side > 0 and max(width, height) > max_side:
        ratio = max_side / max(width, height)
        image = image.resize(
            (max(1, round(width * ratio)), max(1, round(height * ratio))),
            Image.Resampling.LANCZOS,
        )
    sent_width, sent_height = image.size
    scale = width / sent_width

    mark = cursor if cursor_mark else None
    if grid or mark is not None:
        _draw_overlay(image, Image, ImageDraw, ImageFont, rect=rect,
                      step=step, grid=grid, cursor=mark)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", compress_level=6)
    return Rendered(
        png=buffer.getvalue(),
        width=width,
        height=height,
        sent_width=sent_width,
        sent_height=sent_height,
        scale=round(scale, 4),
        blank=blank,
    )
