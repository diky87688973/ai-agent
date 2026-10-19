# -*- coding: utf-8 -*-
"""`desktop_keyboard`：输入文本、按键与组合键。"""
from __future__ import annotations

import time
from typing import Any, Dict

from agent.capabilities.registry import ToolPlugin

from ..config import DesktopConfig
from ..guard import reject_in_plan
from ..input_lock import input_guard
from ..keys import canonical as canonical_key
from ..keys import normalize_hotkey
from ..ports import Backend
from ._params import as_int, as_text, choice, reject_unknown, require_range
from ._windows import WINDOW_FIELDS, focus_target, require_active

_ACTIONS = {
    "type": ("text",),
    "key": ("key", "repeat"),
    "hotkey": ("keys", "repeat"),
}


class DesktopKeyboardTool(ToolPlugin):
    """投递键盘动作。"""

    name = "desktop_keyboard"
    label = "键盘"
    icon = "⌨"
    description = (
        "操作键盘。type 输入任意 Unicode 文本；key 按单个键（enter / tab / esc / "
        "方向键 / f1–f20 / 字母 / 数字 / 符号）；hotkey 按组合键（如 ctrl+c、alt+tab、cmd+space）。"
        "给 window（标题片段）或 hwnd 时先把该窗口恢复并置前，再输入，回执带 focus；"
        "置前失败时不会盲打，直接报错，避免字落进别的窗口。"
        "Plan 模式下拒绝。"
    )
    parameters = {
        "action": {"type": "string", "enum": list(_ACTIONS),
                   "description": "type 输入文本 / key 单键 / hotkey 组合键"},
        "text": {"type": "string", "description": "要输入的文本（type 必填）"},
        "key": {"type": "string", "description": "单键规范名或常见别名（key 必填）"},
        "keys": {"type": "string",
                 "description": "组合键，如 \"ctrl+c\" / \"alt+tab\" / \"cmd+space\"（hotkey 必填）"},
        "repeat": {"type": "integer", "description": "重复次数 1–20（默认 1）"},
        "window": {"type": "string", "description": "目标窗口标题片段；先置前再输入"},
        "hwnd": {"type": "integer", "description": "目标窗口句柄；与 window 二选一，hwnd 更精确"},
    }

    def __init__(self, backend: Backend, config: DesktopConfig,
                 live_state: Any = None) -> None:
        self._backend = backend
        self._config = config
        self._live_state = live_state

    def execute(self, arguments: Dict[str, Any]) -> Any:
        action = choice(arguments, "action", _ACTIONS)
        reject_unknown(arguments, set(_ACTIONS[action]) | {"action"} | set(WINDOW_FIELDS),
                       action=action)
        reject_in_plan(self._live_state, "桌面键盘输入")

        focus = focus_target(self._backend, arguments)
        require_active(focus, "键盘输入")

        port = self._backend.keyboard
        if action == "type":
            text = as_text(arguments, "text")
            with input_guard():
                port.type_text(text, self._config.type_interval_ms)
            result: Dict[str, Any] = {"action": action, "chars": len(text)}
        elif action == "key":
            key = canonical_key(as_text(arguments, "key"))
            repeat = require_range(as_int(arguments, "repeat", 1), "repeat", 1, 20)
            with input_guard():
                port.press(key, repeat)
            result = {"action": action, "key": key, "repeat": repeat}
        else:
            keys = normalize_hotkey(arguments.get("keys"))
            repeat = require_range(as_int(arguments, "repeat", 1), "repeat", 1, 20)
            with input_guard():
                port.hotkey(keys, repeat)
            result = {"action": action, "keys": list(keys), "repeat": repeat}

        if focus is not None:
            result["focus"] = focus
        if self._config.settle_ms:
            time.sleep(self._config.settle_ms / 1000.0)
        return result
