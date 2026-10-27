# -*- coding: utf-8 -*-
"""动作前后的落点区域像素证据。"""
from __future__ import annotations

from typing import Any, Optional, Tuple

from agent.core.error_report import report_error

from ..coords import ScreenPoint, ScreenRect
from ..diff import change_ratio, probe_region


def begin(backend: Any, point: ScreenPoint, side: int = 200
          ) -> Optional[Tuple[ScreenRect, bytes]]:
    """动作前拍一张落点附近区域；拍不到返回 None。"""
    try:
        bounds = backend.screen.geometry().rect
        region = probe_region(point, bounds, side)
        if region is None:
            return None
        shot = backend.screen.capture(region)
        return region, shot.png
    except Exception as exc:
        report_error("plugin.visual_operator.evidence.begin", exc)
        return None


def begin_rect(backend: Any, region: ScreenRect) -> Optional[Tuple[ScreenRect, bytes]]:
    """动作前拍指定矩形；拍不到返回 None。"""
    try:
        shot = backend.screen.capture(region)
        return region, shot.png
    except Exception as exc:
        report_error("plugin.visual_operator.evidence.begin_rect", exc)
        return None


def finish(backend: Any, before: Optional[Tuple[ScreenRect, bytes]]) -> Optional[float]:
    """动作后再拍同一区域并算差异；没有前后图返回 None。"""
    if before is None:
        return None
    region, png = before
    try:
        after = backend.screen.capture(region)
        return change_ratio(png, after.png)
    except Exception as exc:
        report_error("plugin.visual_operator.evidence.finish", exc)
        return None
