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
FONT_MIN = 8
FONT_MAX = 18
#: 光标标签的屏幕目标字号；按图片缩放比例反推图上字号，保证不同缩放下观感一致。
CURSOR_FONT_MIN = 7
CURSOR_FONT_MAX = 16
CURSOR_FONT_SCREEN = 16
#: 短边小于它的区域用紧凑标签：只写坐标，不铺黑底。
COMPACT_SIDE = 140
#: 短边小于它的区域不画坐标标签，坐标只从回执 cursor 读取。
LABEL_MIN_SIDE = 90

_THIN_COLOR = (80, 190, 255, 120)
_MAJOR_COLOR = (255, 70, 70, 220)
_CURSOR_COLOR = (0, 255, 0, 255)
_CURSOR_WHITE = (255, 255, 255, 255)
_CURSOR_HALO = (0, 0, 0, 245)
_GRID_HALO = (0, 0, 0, 110)
_SHADOW_COLOR = (0, 0, 0, 220)


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


def cursor_label_visible(width: int, height: int) -> bool:
    """极小区域不画标签：标签本身比十字更占地方。"""
    return min(width, height) >= LABEL_MIN_SIDE


def cursor_font_size(width: int, height: int, scale: float) -> int:
    """按短边和截图缩放选图上字号；屏幕观感在不同缩放下保持一致。"""
    return max(
        CURSOR_FONT_MIN,
        min(CURSOR_FONT_MAX, round(min(width, height) / 18),
            round(CURSOR_FONT_SCREEN / max(scale, 1e-6))),
    )


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


def _draw_cursor_badge(draw: Any, cursor_x: int, cursor_y: int, radius: int,
                       title: str, coords: str, font: Any,
                       width: int, height: int) -> None:
    """光标读数用紧凑的黑底绿框标签，优先放在光标右侧。"""
    title_width, title_height = (_text_size(draw, title, font) if title else (0, 0))
    coord_width, coord_height = _text_size(draw, coords, font)
    compact = min(width, height) < COMPACT_SIDE
    pad = 2 if compact else 3
    line_gap = 3 if title else 0
    box_width = max(title_width, coord_width) + pad * 2
    box_height = title_height + coord_height + line_gap + pad * 2
    x = cursor_x + radius + 6
    if x + box_width > width - 2:
        x = cursor_x - radius - 6 - box_width
    x = max(2, min(x, width - box_width - 2))
    y = max(2, min(cursor_y - box_height // 2, height - box_height - 2))
    if compact:
        # 小区域只描字，不铺黑底，底下原有内容仍能透出来。
        if title:
            draw.text((x + pad, y + pad), title, font=font, fill=_CURSOR_WHITE,
                      stroke_width=1, stroke_fill=_CURSOR_HALO)
        draw.text((x + pad, y + pad + title_height + line_gap), coords,
                  font=font, fill=_CURSOR_WHITE,
                  stroke_width=1, stroke_fill=_CURSOR_HALO)
        return
    draw.rounded_rectangle(
        (x, y, x + box_width, y + box_height),
        radius=3,
        fill=(0, 0, 0, 200),
        outline=_CURSOR_COLOR,
        width=1,
    )
    if title:
        draw.text((x + pad, y + pad), title, font=font, fill=_CURSOR_WHITE)
    draw.text((x + pad, y + pad + title_height + line_gap), coords,
              font=font, fill=_CURSOR_WHITE)


def _offset(origin: int, value: int, extent: int, pixels: int) -> int:
    """屏幕坐标 → 图片像素偏移；`extent` 是该轴的屏幕坐标跨度，`pixels` 是图片尺寸。"""
    return round((value - origin) * pixels / extent)


def _label_value(value: int, origin: int, extent: int, pixels: int,
                 grid_unit: str) -> str:
    """刻度标签：屏幕坐标或图内像素坐标。"""
    if grid_unit == "image":
        return str(round((value - origin) * pixels / extent))
    return str(value)


def _draw_overlay(image: Any, image_module: Any, image_draw: Any, image_font: Any, *,
                  rect: ScreenRect, step: int, grid: bool,
                  cursor: Optional[ScreenPoint], grid_unit: str = "screen",
                  scale: float = 1.0) -> None:
    """在图片上叠坐标网格与光标十字；刻度单位由 `grid_unit` 决定。"""
    width, height = image.size
    step = max(1, int(step))
    base = image.convert("RGBA")
    canvas = image_module.new("RGBA", base.size, (0, 0, 0, 0))
    draw = image_draw.Draw(canvas)
    font = _font(image_font, max(FONT_MIN, min(FONT_MAX, round(width / 120))))
    text_height = _text_size(draw, "0", font)[1] + 2
    major_width = max(2, min(3, round(width / 600)))
    minor_width = max(1, min(2, round(width / 900)))

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
                line_width = major_width if major else minor_width
                draw.line([(offset, 0), (offset, height)],
                          fill=_GRID_HALO, width=line_width + 1)
                draw.line([(offset, 0), (offset, height)],
                          fill=_MAJOR_COLOR if major else _THIN_COLOR,
                          width=line_width)
                if major:
                    label = _label_value(screen_x, rect.x, rect.width, width, grid_unit)
                    _draw_label(draw, (offset + 3, 2), label,
                                font, text_height, width, height)
                    _draw_label(draw, (offset + 3, height - text_height - 2),
                                label, font, text_height, width, height)

        first = -(-rect.y // step)
        last = (rect.bottom - 1) // step
        for index in range(first, last + 1):
            major = index % MAJOR_EVERY == 0
            if not show_minor and not major:
                continue
            screen_y = index * step
            offset = _offset(rect.y, screen_y, rect.height, height)
            if 0 <= offset < height:
                line_width = major_width if major else minor_width
                draw.line([(0, offset), (width, offset)],
                          fill=_GRID_HALO, width=line_width + 1)
                draw.line([(0, offset), (width, offset)],
                          fill=_MAJOR_COLOR if major else _THIN_COLOR,
                          width=line_width)
                if major:
                    label = _label_value(screen_y, rect.y, rect.height, height, grid_unit)
                    _draw_label(draw, (2, offset + 3), label,
                                font, text_height, width, height)
                    _draw_label(draw, (width - 4 - _text_size(draw, label, font)[0],
                                       offset + 3),
                                label, font, text_height, width, height)

    if cursor is not None:
        cursor_x = _offset(rect.x, cursor.x, rect.width, width)
        cursor_y = _offset(rect.y, cursor.y, rect.height, height)
        if 0 <= cursor_x < width and 0 <= cursor_y < height:
            halo_width = max(3, min(5, round(width / 400)))
            cursor_width = max(1, min(3, round(width / 700)))
            white_width = cursor_width + 1
            radius = max(4, min(12, round(width / 70), round(16 / scale)))
            arm = max(8, min(36, round(min(width, height) / 12),
                             round(50 / scale)))
            gap = max(2, cursor_width + 1)
            # 只画光标周围的短十字；中心留空，落点像素本身不被盖住。
            for color, line_width in (
                (_CURSOR_HALO, halo_width),
                (_CURSOR_WHITE, white_width),
                (_CURSOR_COLOR, cursor_width),
            ):
                draw.line([(cursor_x - arm, cursor_y), (cursor_x - gap, cursor_y)],
                          fill=color, width=line_width)
                draw.line([(cursor_x + gap, cursor_y), (cursor_x + arm, cursor_y)],
                          fill=color, width=line_width)
                draw.line([(cursor_x, cursor_y - arm), (cursor_x, cursor_y - gap)],
                          fill=color, width=line_width)
                draw.line([(cursor_x, cursor_y + gap), (cursor_x, cursor_y + arm)],
                          fill=color, width=line_width)
            for color, line_width in (
                (_CURSOR_HALO, max(3, halo_width)),
                (_CURSOR_WHITE, max(2, white_width)),
                (_CURSOR_COLOR, max(1, cursor_width + 1)),
            ):
                draw.ellipse(
                    (cursor_x - radius, cursor_y - radius,
                     cursor_x + radius, cursor_y + radius),
                    outline=color, width=line_width,
                )
            if cursor_label_visible(width, height):
                coords = _label_value(cursor.x, rect.x, rect.width, width, grid_unit) + "," \
                    + _label_value(cursor.y, rect.y, rect.height, height, grid_unit)
                cursor_font = _font(
                    image_font, cursor_font_size(width, height, scale))
                title = "" if min(width, height) < COMPACT_SIDE else "CURSOR"
                _draw_cursor_badge(
                    draw, cursor_x, cursor_y, radius, title, coords,
                    cursor_font, width, height,
                )

    image.paste(image_module.alpha_composite(base, canvas).convert("RGB"))


def render(png: bytes, *, rect: ScreenRect, grid: bool, step: int,
           cursor: Optional[ScreenPoint], cursor_mark: bool, max_side: int,
           grid_unit: str = "screen") -> Rendered:
    """把原始截图加工成要发给模型的那一张。"""
    unit = str(grid_unit or "screen").strip().lower()
    if unit not in ("screen", "image"):
        raise ValueError(f"grid_unit 只能是 screen 或 image，实际 {grid_unit!r}")
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
                      step=step, grid=grid, cursor=mark, grid_unit=unit,
                      scale=scale)

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
