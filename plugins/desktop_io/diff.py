# -*- coding: utf-8 -*-
"""动作前后的画面差异：给"这一下到底有没有生效"一个可读的数字。

点击回执若只有落点坐标，"命中卡片还是命中背景"就只能靠下一张截图猜。
差异比例是廉价的一阶证据：0 表示画面完全没动，接近 1 表示整块都变了。
它不是语义判断，也不能替代看图；它的作用是让"没生效"当场暴露，
而不是留到下一轮凭截图重新推理。
"""
from __future__ import annotations

import io
import sys
from typing import Optional

from .coords import ScreenPoint, ScreenRect
from .errors import ScreenCaptureFailed

#: 比较前缩到这个边长：够区分"局部变了"与"整体变了"，又不受视频噪声支配。
_THUMB_SIDE = 64
#: 单通道差超过它的像素才算"变了"：抖动、抗锯齿与视频压缩噪声都在这条线以下。
_PIXEL_EPSILON = 8


def probe_region(point: ScreenPoint, bounds: ScreenRect, side: int = 200) -> Optional[ScreenRect]:
    """以落点为中心取一块方形区域；与屏幕无交集时返回 None。

    点击的影响几乎总在落点附近：局部差异比整屏差异更能说明"点中了什么"。
    """
    half = side // 2
    try:
        region = ScreenRect(point.x - half, point.y - half, side, side)
    except ValueError:
        return None
    return region.intersect(bounds)


def change_ratio(before: bytes, after: bytes) -> Optional[float]:
    """两张 PNG 的差异比例（0–1）；无法解码时返回 None 并留痕。

    差异是观察面而不是结论：算不出来只丢一个字段，不能把已经投递出去的
    动作改判成失败。
    """
    try:
        from PIL import Image
    except ImportError as exc:
        raise ScreenCaptureFailed(f"差异比较需要 Pillow：{exc}") from exc
    try:
        left = _thumb(Image, before)
        right = _thumb(Image, after)
    except OSError as exc:
        # 已投递的动作不该因为"事后量不出来"被改判失败；留痕即可。
        print(f"[desktop_io] 差异比较跳过：{exc}", file=sys.stderr, flush=True)
        return None
    changed = 0
    total = 0
    # `tobytes()` 是 L 模式的逐像素字节：比 `getdata()` 快，也没有弃用告警。
    for left_value, right_value in zip(left.tobytes(), right.tobytes()):
        total += 1
        if abs(left_value - right_value) > _PIXEL_EPSILON:
            changed += 1
    return round(changed / total, 3) if total else 0.0


def _thumb(image_module, png: bytes):
    image = image_module.open(io.BytesIO(png))
    image.load()
    return image.convert("L").resize((_THUMB_SIDE, _THUMB_SIDE),
                                     image_module.Resampling.BILINEAR)
