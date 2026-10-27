# -*- coding: utf-8 -*-
"""`desktop_window`：列出、激活、等待和读取窗口。"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from agent.capabilities.registry import ToolPlugin

from ..errors import DesktopUnavailable
from ..guard import reject_in_plan
from ..ports import Backend
from ..titles import title_matches
from ._params import as_int, choice, has, reject_unknown, require_range
from ._windows import focus_target, window_target


class DesktopWindowTool(ToolPlugin):
    name = "desktop_window"
    label = "窗口"
    icon = "🪟"
    description = (
        "列出/激活/等待/读取顶层窗口。已知目标时优先用 hwnd，"
        "导航或新开窗口后用 list 或 desktop_app 返回的 hwnd 绑定目标，"
        "不要反复按标题猜窗口。activate 只做激活，不投递输入；"
        "wait 只在目标尚未出现或尚未就绪时使用，窗口已存在时立即返回。"
    )
    parameters = {
        "action": {"type": "string", "enum": ["list", "activate", "wait", "rect"],
                   "description": "list 列表 / activate 激活 / wait 等窗口 / rect 读取矩形"},
        "window": {"type": "string",
                   "description": "窗口标题片段；与 hwnd 二选一"},
        "hwnd": {"type": "integer",
                 "description": "窗口句柄；导航后应复用 desktop_app / desktop_open 返回的 hwnd"},
        "timeout_ms": {"type": "integer",
                       "description": "wait 的最长等待毫秒数 100–60000（默认 10000）"},
        "interval_ms": {"type": "integer",
                        "description": "wait 的轮询间隔 50–2000 毫秒（默认 150）"},
        "limit": {"type": "integer",
                  "description": "list 最多返回多少个窗口 1–50（默认 20）"},
    }

    _FIELDS = ("action", "window", "hwnd", "timeout_ms", "interval_ms", "limit")

    def __init__(self, backend: Backend, live_state: Any = None) -> None:
        self._backend = backend
        self._live_state = live_state

    def execute(self, arguments: Dict[str, Any]) -> Any:
        reject_unknown(arguments, set(self._FIELDS), action=self.name)
        action = choice(arguments, "action", ("list", "activate", "wait", "rect"))
        if action == "list":
            return self._list(arguments)
        if action == "activate":
            reject_in_plan(self._live_state, "桌面窗口激活")
            return {"focus": focus_target(self._backend, arguments)}
        if action == "rect":
            target, matched = window_target(self._backend, arguments)
            return {"window": target.to_dict() if target is not None else None,
                    "matched": matched}
        return self._wait(arguments)

    def _list(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        port = self._backend.windows
        if port is None:
            raise DesktopUnavailable("当前平台不支持窗口列表")
        lister = getattr(port, "list_visible", None)
        if not callable(lister):
            raise DesktopUnavailable("当前后端没有窗口列表能力")
        limit = require_range(as_int(arguments, "limit", 20), "limit", 1, 50)
        title = str(arguments.get("window") or "").strip()
        windows = [info for info in lister() if not title or title_matches(info.title, title)]
        windows.sort(key=lambda info: (not info.foreground, info.rect.width * info.rect.height),
                     reverse=True)
        return {
            "windows": [info.to_dict() for info in windows[:limit]],
            "total": len(windows),
            "truncated": len(windows) > limit,
        }

    def _wait(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        port = self._backend.windows
        if port is None:
            raise DesktopUnavailable("当前平台不支持窗口等待")
        if not has(arguments, "window") and not has(arguments, "hwnd"):
            raise ValueError("wait 需要 window 或 hwnd")
        timeout = require_range(as_int(arguments, "timeout_ms", 10000),
                                "timeout_ms", 100, 60000)
        interval = require_range(as_int(arguments, "interval_ms", 150),
                                 "interval_ms", 50, 2000)
        started = time.monotonic()
        last: Optional[Dict[str, Any]] = None
        while True:
            try:
                target, matched = window_target(self._backend, arguments)
            except ValueError:
                if not has(arguments, "window"):
                    raise
                target, matched = None, 0
            if target is not None and (not target.minimized):
                return {
                    "satisfied": True,
                    "waited_ms": int((time.monotonic() - started) * 1000),
                    "delay_ms": interval,
                    "window": target.to_dict(),
                    "matched": matched,
                }
            if target is not None:
                last = target.to_dict()
            if (time.monotonic() - started) * 1000 >= timeout:
                return {
                    "satisfied": False,
                    "waited_ms": int((time.monotonic() - started) * 1000),
                    "window": last,
                }
            time.sleep(interval / 1000.0)
