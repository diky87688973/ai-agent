# -*- coding: utf-8 -*-
"""视觉操作 2.0 插件配置。"""
from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VisionConfig:
    fps: float = 5.0
    queue_size: int = 2
    focus_width: int = 200
    focus_height: int = 200
    focus_zoom: float = 1.0
    settle_ms: int = 100
    takeover_distance: int = 100
    move_settle_ms: int = 50
    move_duration_ms: int = 0
    image_format: str = "WEBP"
    image_quality: int = 80
    square_size: int = 1024
    focus_max_side: int = 200


def _int(section: configparser.SectionProxy, key: str, default: int,
         low: int, high: int) -> int:
    try:
        value = int(section.get(key, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def _float(section: configparser.SectionProxy, key: str, default: float,
           low: float, high: float) -> float:
    try:
        value = float(section.get(key, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def _bool(section: configparser.SectionProxy, key: str, default: bool) -> bool:
    raw = str(section.get(key, "1" if default else "0") or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


def load_config(path: Path | None = None) -> VisionConfig:
    source = path or Path(__file__).with_name("plugin-config.ini")
    parser = configparser.ConfigParser()
    parser.read(source, encoding="utf-8")
    vision = parser["vision"] if parser.has_section("vision") else {}
    image = parser["image"] if parser.has_section("image") else {}
    fmt = str(image.get("format", "webp") if hasattr(image, "get") else "webp").upper()
    if fmt not in ("WEBP", "JPEG", "PNG"):
        fmt = "WEBP"
    return VisionConfig(
        fps=_float(vision, "fps", 5.0, 0.2, 30.0),
        queue_size=2,
        focus_width=_int(vision, "focus_width", 200, 64, 4096),
        focus_height=_int(vision, "focus_height", 200, 64, 4096),
        focus_zoom=_float(vision, "focus_zoom", 1.0, 1.0, 4.0),
        settle_ms=_int(vision, "settle_ms", 100, 0, 5000),
        takeover_distance=_int(vision, "takeover_distance", 100, 1, 2000),
        move_settle_ms=_int(vision, "move_settle_ms", 50, 0, 500),
        move_duration_ms=_int(vision, "move_duration_ms", 200, 0, 1000),
        image_format=fmt,
        image_quality=_int(image, "quality", 80, 1, 100),
        square_size=_int(image, "square_size", 1024, 256, 2048),
        focus_max_side=_int(image, "focus_max_side", 200, 64, 4096),
    )

__all__ = ["VisionConfig", "load_config"]
