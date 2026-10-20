# -*- coding: utf-8 -*-
"""插件配置：`[config]` 的读取、回退与夹取。

解析只看 `[config]`。真实配置缺失时整份取默认值，
非法值回退默认、越界值夹到边界：配置错误不阻断工具注册，
生效值可由 `desktop_eye` 的返回值反查。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from agent.config import load_ini

CONFIG_FILE = "plugin-config.ini"
SECTION = "config"

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})

#: 整数键的取值范围；越界夹到边界。
INT_RANGES: Mapping[str, tuple] = {
    "max_side": (0, 8192),
    "grid_step": (20, 500),
    "settle_ms": (0, 2000),
    "type_interval_ms": (0, 200),
    "hover_settle_ms": (0, 2000),
    "hover_approach_ms": (0, 2000),
    "wait_interval_ms": (50, 2000),
}


@dataclass(frozen=True)
class DesktopConfig:
    """能力开关与截图、输入、等待的时间参数。"""

    eye: bool = True
    mouse: bool = True
    keyboard: bool = True
    wait: bool = True
    max_side: int = 1920
    grid_step: int = 100
    cursor_mark: bool = True
    settle_ms: int = 60
    type_interval_ms: int = 12
    hover_settle_ms: int = 250
    #: 悬停时用多久移到落点。0 = 一次跳变；有值的移动会连续产生
    #: WM_MOUSEMOVE，播放器/网页的自动隐藏控件才认"鼠标在动"。
    hover_approach_ms: int = 120
    #: 落点附近做几次 1–2px 的微移动。部分播放器只在"连续移动"时才唤出控制条，
    #: 一次跳变后静止会被当成"鼠标没动"。
    hover_wiggle: bool = True
    wait_interval_ms: int = 200


DEFAULTS = DesktopConfig()


def _as_bool(raw: Optional[str], default: bool) -> bool:
    text = str(raw or "").strip().lower()
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    return default


def _as_int(raw: Optional[str], key: str) -> int:
    default = int(getattr(DEFAULTS, key))
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    low, high = INT_RANGES[key]
    return max(low, min(high, value))


def load_config(plugin_root: Optional[Path] = None) -> DesktopConfig:
    """读插件目录下的配置；文件缺失或没有 `[config]` 时全部取默认值。"""
    root = Path(plugin_root) if plugin_root is not None else Path(__file__).resolve().parent
    parser = load_ini(root / CONFIG_FILE)
    values: Dict[str, Any] = {}
    if parser.has_section(SECTION):
        values = {str(key): str(value) for key, value in parser.items(SECTION)}

    return DesktopConfig(
        eye=_as_bool(values.get("eye"), DEFAULTS.eye),
        mouse=_as_bool(values.get("mouse"), DEFAULTS.mouse),
        keyboard=_as_bool(values.get("keyboard"), DEFAULTS.keyboard),
        wait=_as_bool(values.get("wait"), DEFAULTS.wait),
        max_side=_as_int(values.get("max_side"), "max_side"),
        grid_step=_as_int(values.get("grid_step"), "grid_step"),
        cursor_mark=_as_bool(values.get("cursor_mark"), DEFAULTS.cursor_mark),
        settle_ms=_as_int(values.get("settle_ms"), "settle_ms"),
        type_interval_ms=_as_int(values.get("type_interval_ms"), "type_interval_ms"),
        hover_settle_ms=_as_int(values.get("hover_settle_ms"), "hover_settle_ms"),
        hover_approach_ms=_as_int(values.get("hover_approach_ms"), "hover_approach_ms"),
        hover_wiggle=_as_bool(values.get("hover_wiggle"), DEFAULTS.hover_wiggle),
        wait_interval_ms=_as_int(values.get("wait_interval_ms"), "wait_interval_ms"),
    )
