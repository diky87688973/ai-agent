# -*- coding: utf-8 -*-
"""插件配置：`[ext]` 的读取、回退与夹取。

解析只看 `[ext]`，不碰 `[base]`。真实配置缺失时整份取默认值，
非法值回退默认、越界值夹到边界：配置错误不阻断工具注册，
生效值可由 `desktop_eye` 的返回值反查。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from agent.config import load_ini

CONFIG_FILE = "plugin-config.ini"
SECTION = "ext"

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})

#: 整数键的取值范围；越界夹到边界。
INT_RANGES: Mapping[str, tuple] = {
    "max_side": (0, 8192),
    "grid_step": (20, 500),
    "settle_ms": (0, 2000),
    "type_interval_ms": (0, 200),
}


@dataclass(frozen=True)
class DesktopConfig:
    """三个能力开关与截图、输入的时间参数。"""

    eye: bool = True
    mouse: bool = True
    keyboard: bool = True
    max_side: int = 1600
    grid_step: int = 100
    cursor_mark: bool = True
    settle_ms: int = 60
    type_interval_ms: int = 12


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
    """读插件目录下的配置；文件缺失或没有 `[ext]` 时全部取默认值。"""
    root = Path(plugin_root) if plugin_root is not None else Path(__file__).resolve().parent
    parser = load_ini(root / CONFIG_FILE)
    values: Dict[str, Any] = {}
    if parser.has_section(SECTION):
        values = {str(key): str(value) for key, value in parser.items(SECTION)}

    return DesktopConfig(
        eye=_as_bool(values.get("eye"), DEFAULTS.eye),
        mouse=_as_bool(values.get("mouse"), DEFAULTS.mouse),
        keyboard=_as_bool(values.get("keyboard"), DEFAULTS.keyboard),
        max_side=_as_int(values.get("max_side"), "max_side"),
        grid_step=_as_int(values.get("grid_step"), "grid_step"),
        cursor_mark=_as_bool(values.get("cursor_mark"), DEFAULTS.cursor_mark),
        settle_ms=_as_int(values.get("settle_ms"), "settle_ms"),
        type_interval_ms=_as_int(values.get("type_interval_ms"), "type_interval_ms"),
    )
