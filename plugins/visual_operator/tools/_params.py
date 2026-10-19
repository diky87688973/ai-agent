# -*- coding: utf-8 -*-
"""工具参数读取：类型校验、取值范围与动作矩阵检查。

三个工具共用这一层，参数规则只写一份。错误文案点名参数与可用取值，
模型据此改一次参数就能重试成功。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from ..coords import ScreenPoint

_MISSING = object()

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def has(arguments: Dict[str, Any], key: str) -> bool:
    """参数是否真的给了（None 与空串都算没给）。"""
    value = arguments.get(key)
    return value is not None and value != ""


def _raw(arguments: Dict[str, Any], key: str) -> Any:
    value = arguments.get(key)
    if value is None or value == "":
        return _MISSING
    return value


def as_int(arguments: Dict[str, Any], key: str,
           default: Optional[int] = None) -> Optional[int]:
    """读整数；布尔与浮点拒绝，数字字符串接受。"""
    value = _raw(arguments, key)
    if value is _MISSING:
        return default
    if isinstance(value, bool):
        raise ValueError(f"{key} 必须是整数，实际是布尔值")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            raise ValueError(f"{key} 必须是整数，实际 {value!r}") from None
    raise ValueError(f"{key} 必须是整数，实际是 {type(value).__name__}")


def as_text(arguments: Dict[str, Any], key: str) -> str:
    """读非空字符串；首尾空白保留（空格本身是合法的输入文本）。"""
    value = _raw(arguments, key)
    if value is _MISSING:
        raise ValueError(f"缺少 {key}")
    if not isinstance(value, str):
        raise ValueError(f"{key} 必须是字符串")
    return value


def as_bool(arguments: Dict[str, Any], key: str, default: bool) -> bool:
    value = _raw(arguments, key)
    if value is _MISSING:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    raise ValueError(f"{key} 需要布尔值，实际 {value!r}")


def choice(arguments: Dict[str, Any], key: str, allowed: Iterable[str],
           default: Optional[str] = None) -> str:
    """读枚举值；未知值点名可用项。"""
    options = tuple(allowed)
    value = _raw(arguments, key)
    if value is _MISSING:
        if default is None:
            raise ValueError(f"缺少 {key}；可用 {', '.join(options)}")
        return default
    text = str(value).strip().lower()
    if text not in options:
        raise ValueError(f"未知 {key}={value!r}；可用 {', '.join(options)}")
    return text


def require_range(value: Optional[int], key: str, low: int, high: int) -> int:
    """校验闭区间；越界报错，不夹取（工具参数与配置的取舍不同）。"""
    if value is None:
        raise ValueError(f"缺少 {key}")
    if not low <= value <= high:
        raise ValueError(f"{key} 取值 {low}–{high}，实际 {value}")
    return value


def reject_unknown(arguments: Dict[str, Any], allowed: Iterable[str], *,
                   action: str) -> None:
    """动作矩阵：拒绝属于别的动作的参数，避免参数被静默忽略。"""
    extra = sorted(set(arguments) - set(allowed))
    if extra:
        raise ValueError(
            f"action={action} 不接受 {', '.join(extra)}；"
            f"可用参数：{', '.join(sorted(allowed))}"
        )


def point_argument(arguments: Dict[str, Any], x_key: str = "x",
                   y_key: str = "y") -> Optional[ScreenPoint]:
    """读成对的 x/y；只给一个时报错，两个都没给返回 None。"""
    has_x = has(arguments, x_key)
    has_y = has(arguments, y_key)
    if not has_x and not has_y:
        return None
    if has_x != has_y:
        raise ValueError(f"{x_key} 与 {y_key} 需要同时给出")
    return ScreenPoint(as_int(arguments, x_key, 0) or 0,
                       as_int(arguments, y_key, 0) or 0)
