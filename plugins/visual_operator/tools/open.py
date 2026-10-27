# -*- coding: utf-8 -*-
"""`desktop_open`：用系统默认程序打开 URL / scheme / 文件。"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict

from agent.capabilities.registry import ToolPlugin

from ..errors import DesktopError
from ..guard import reject_in_plan
from ..ports import Backend
from ._params import as_bool, as_int, reject_unknown, require_range


class DesktopOpenTool(ToolPlugin):
    name = "desktop_open"
    label = "打开"
    icon = "🌐"
    description = (
        "用系统默认浏览器/程序打开 URL、URL scheme 或已有文件；不经 shell。"
        "打开已知网站时优先用本工具，不要先扫文件系统或猜浏览器窗口。"
        "优先返回本次新出现的窗口，fresh=false 时返回实际复用窗口；"
        "给 window 时即使标题不完全匹配，也返回新窗口并说明实际标题。"
        "后续操作复用返回的 hwnd。打开本地程序用 desktop_app。"
    )
    parameters = {
        "target": {"type": "string",
                   "description": "URL（http/https）、scheme（mailto: 等）或已有文件路径"},
        "window": {"type": "string",
                   "description": "打开后等待的窗口标题片段；不给则只返回已发起"},
        "timeout_ms": {"type": "integer",
                       "description": "等待窗口的毫秒数 100–60000（默认 10000）"},
        "activate": {"type": "boolean",
                     "description": "找到窗口后是否置前（默认 true）"},
    }

    _FIELDS = ("target", "window", "timeout_ms", "activate")

    def __init__(self, backend: Backend, live_state: Any = None) -> None:
        self._backend = backend
        self._live_state = live_state

    def execute(self, arguments: Dict[str, Any]) -> Any:
        reject_unknown(arguments, set(self._FIELDS), action=self.name)
        reject_in_plan(self._live_state, "桌面打开 URL/文件")
        target = str(arguments.get("target") or "").strip()
        if not target:
            raise ValueError("缺少 target")
        if not self._valid_target(target):
            raise ValueError("target 必须是 http(s) URL、带 scheme 的地址或已存在的文件")
        port = self._backend.windows
        before = None
        if port is not None:
            lister = getattr(port, "list_visible", None)
            if callable(lister):
                before = {info.hwnd for info in lister()}
        method = self._launch(target)
        title = str(arguments.get("window") or "").strip()
        timeout = require_range(as_int(arguments, "timeout_ms", 10000),
                                "timeout_ms", 100, 60000)
        if port is None or before is None:
            return {"opened": True, "target": target, "method": method, "window": None}
        lister = getattr(port, "list_visible", None)
        started = time.monotonic()
        while (time.monotonic() - started) * 1000 < timeout:
            windows = list(lister())
            fresh = [info for info in windows if info.hwnd not in before]
            if fresh:
                chosen = self._choose(fresh, title) or fresh[0]
                return self._opened(target, method, chosen, windows, before,
                                    title, started, arguments)
            if not title and (time.monotonic() - started) * 1000 >= min(timeout, 1500):
                foreground = next((info for info in windows
                                   if info.foreground and _looks_browser(info.title)), None)
                if foreground is not None:
                    return self._opened(target, method, foreground, windows,
                                        before, title, started, arguments)
            time.sleep(0.15)
        # 目标窗口可能已经在打开前就存在，且没有新窗口出现。
        windows = list(lister())
        matched = [info for info in windows if self._title_ok(info.title, title)]
        if matched:
            return self._opened(target, method, matched[0], windows, before,
                                title, started, arguments, reused=True)
        return {"opened": True, "target": target, "method": method,
                "window": None, "satisfied": False,
                "waited_ms": int((time.monotonic() - started) * 1000)}

    def _opened(self, target: str, method: str, window: Any, windows: Any,
                 before: Any, title: str, started: float,
                 arguments: Dict[str, Any], reused: bool = False) -> Dict[str, Any]:
        port = self._backend.windows
        focus = None
        if as_bool(arguments, "activate", True):
            focus = port.activate(window.hwnd).to_dict()
        result = {
            "opened": True, "target": target, "method": method,
            "window": window.to_dict(),
            "matched": len([info for info in windows
                            if self._title_ok(info.title, title)]) if title else 0,
            "fresh": window.hwnd not in before,
            "reused": reused or window.hwnd in before,
            "focus": focus,
            "waited_ms": int((time.monotonic() - started) * 1000),
        }
        if title and not self._title_ok(window.title, title):
            result["note"] = (
                f"打开的窗口标题是「{window.title}」，不包含请求的「{title}」；"
                "已返回实际新窗口，后续请复用这个 hwnd"
            )
        if focus is not None and not focus.get("active"):
            result["note"] = "窗口已返回，但未能置前；输入前先处理前台窗口"
        return result

    @staticmethod
    def _title_ok(title: str, needle: str) -> bool:
        from ..titles import title_matches
        return not needle or title_matches(title, needle)

    @classmethod
    def _choose(cls, windows: Any, title: str) -> Any:
        from ..titles import normalize_title
        wanted = normalize_title(title)
        exact = [info for info in windows if normalize_title(info.title) == wanted]
        if exact:
            return exact[0]
        for info in windows:
            if cls._title_ok(info.title, title):
                return info
        return None

    @staticmethod
    def _valid_target(target: str) -> bool:
        lowered = target.lower()
        if lowered.startswith(("http://", "https://")):
            return True
        scheme = target.split(":", 1)[0].lower()
        if scheme in ("mailto", "tel", "file") and ":" in target:
            return True
        if len(target) > 2 and target[1] == ":" and target[2] in ("\\", "/"):
            return Path(target).is_file()
        return Path(target).expanduser().is_file()

    @staticmethod
    def _launch(target: str) -> str:
        try:
            if sys.platform == "win32":
                os.startfile(target)  # type: ignore[attr-defined]
                return "os.startfile"
            command = ["open", target] if sys.platform == "darwin" else ["xdg-open", target]
            subprocess.Popen(command, shell=False, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             close_fds=True)
            return command[0]
        except OSError as exc:
            raise DesktopError(f"打开失败：{type(exc).__name__}: {exc}") from exc


def _looks_browser(title: str) -> bool:
    from ..titles import normalize_title
    normalized = normalize_title(title)
    return any(name in normalized for name in ("chrome", "edge", "firefox", "safari"))
