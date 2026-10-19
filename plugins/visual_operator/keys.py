# -*- coding: utf-8 -*-
"""跨平台键名：规范名、别名归一与组合键校验。

规范名是工具参数与后端键码表的共同词汇。别名只在这里归一一次，
两个后端各拿规范名查自己的键码表，键名规则不会分叉。
"""
from __future__ import annotations

from typing import Any, List, Tuple

LETTERS = tuple("abcdefghijklmnopqrstuvwxyz")
DIGITS = tuple("0123456789")
PUNCTUATION_KEYS = ("-", "=", "[", "]", ";", "'", ",", ".", "/", "\\", "`")
FUNCTION_KEYS = tuple(f"f{index}" for index in range(1, 21))
NAMED_KEYS = (
    "enter", "tab", "esc", "space", "backspace", "delete", "insert",
    "home", "end", "pageup", "pagedown", "left", "up", "right", "down",
    "capslock", "ctrl", "shift", "alt", "win", "cmd",
)

MODIFIERS = frozenset({"ctrl", "shift", "alt", "win", "cmd"})

CANONICAL_KEYS = frozenset(
    NAMED_KEYS + FUNCTION_KEYS + LETTERS + DIGITS + PUNCTUATION_KEYS
)

_ALIASES = {
    "return": "enter",
    "escape": "esc",
    "control": "ctrl",
    "option": "alt",
    "command": "cmd",
    "meta": "cmd",
    "super": "cmd",
    "windows": "win",
    "page_up": "pageup",
    "pgup": "pageup",
    "page_down": "pagedown",
    "pgdn": "pagedown",
    "back_space": "backspace",
    "del": "delete",
    "ins": "insert",
    "spacebar": "space",
    "arrowup": "up",
    "arrowdown": "down",
    "arrowleft": "left",
    "arrowright": "right",
    "minus": "-",
    "equal": "=",
    "slash": "/",
    "backslash": "\\",
    "comma": ",",
    "period": ".",
    "dot": ".",
    "semicolon": ";",
    "quote": "'",
    "backtick": "`",
}

_HINT = (
    "enter / tab / esc / space / backspace / delete / insert / home / end / "
    "pageup / pagedown / 方向键 / f1–f20 / ctrl / shift / alt / win / cmd / 单个字符"
)


def canonical(name: Any) -> str:
    """把键名归一成规范名；不认识时报错并给出可用词汇的摘要。"""
    raw = str(name or "").strip()
    if not raw:
        raise ValueError("键名不能为空")
    key = _ALIASES.get(raw.lower(), raw.lower())
    if key in CANONICAL_KEYS:
        return key
    if len(raw) == 1:
        raise ValueError(
            f"键名 {raw!r} 不能作为单键投递；单字符键只支持字母、数字与 "
            "- = [ ] ; ' , . / \\ `"
        )
    raise ValueError(f"未知键名 {raw!r}；可用 {_HINT}")


def split_hotkey(raw: Any) -> List[str]:
    """把 `"ctrl+c"` / `"ctrl,c"` / `["ctrl", "c"]` 拆成键名列表。"""
    if isinstance(raw, (list, tuple)):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        if text == "+":
            return ["+"]
        for separator in ("+", ","):
            if separator in text:
                return [part.strip() for part in text.split(separator) if part.strip()]
        return [text]
    raise ValueError("keys 需要字符串或字符串数组")


def normalize_hotkey(raw: Any) -> Tuple[str, ...]:
    """校验组合键：2–4 个键，至少一个非修饰键。"""
    keys = tuple(canonical(item) for item in split_hotkey(raw))
    if not 2 <= len(keys) <= 4:
        raise ValueError(f"组合键需要 2–4 个键，实际 {len(keys)} 个")
    if not any(key not in MODIFIERS for key in keys):
        raise ValueError(f"组合键至少包含一个非修饰键：{' + '.join(keys)}")
    return keys
