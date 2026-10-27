# -*- coding: utf-8 -*-
"""`desktop_app`：启动本地程序并等待主窗口。"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

from agent.capabilities.registry import ToolPlugin

from ..errors import DesktopError, DesktopUnavailable
from ..guard import reject_in_plan
from ..ports import Backend
from ..titles import normalize_title
from ._params import as_bool, as_int, reject_unknown, require_range


class DesktopAppTool(ToolPlugin):
    name = "desktop_app"
    label = "启动应用"
    icon = "🚀"
    description = (
        "启动已安装的本地程序并等待窗口。path 必须是可执行文件/快捷方式的绝对路径；"
        "也可以用 name 从开始菜单快捷方式中查找，避免先 glob_files。"
        "args 以数组传递，不经 shell。启动后返回 pid（快捷方式可能为 null）；"
        "给 window 标题时等待并返回 hwnd、rect 与 active；不给 window 且给了 name 时用 name 等窗口。"
        "后续操作优先复用返回的 hwnd，不要按标题重新猜。打开 URL 用 desktop_open，不要用本工具。"
    )
    parameters = {
        "path": {"type": "string", "description": "可执行文件/快捷方式的绝对路径；与 name 二选一"},
        "name": {"type": "string", "description": "应用名，从开始菜单快捷方式中查找；与 path 二选一"},
        "args": {"type": "array", "items": {"type": "string"},
                 "description": "传给程序的参数数组；不经 shell"},
        "window": {"type": "string",
                   "description": "启动后等待的窗口标题片段；不给则只返回 pid"},
        "timeout_ms": {"type": "integer",
                       "description": "等待窗口的毫秒数 100–60000（默认 10000）"},
        "activate": {"type": "boolean",
                     "description": "找到窗口后是否置前（默认 true）"},
    }

    _FIELDS = ("path", "name", "args", "window", "timeout_ms", "activate")

    def __init__(self, backend: Backend, live_state: Any = None) -> None:
        self._backend = backend
        self._live_state = live_state

    def execute(self, arguments: Dict[str, Any]) -> Any:
        reject_unknown(arguments, set(self._FIELDS), action=self.name)
        reject_in_plan(self._live_state, "桌面应用启动")
        raw_path = str(arguments.get("path") or "").strip()
        name = str(arguments.get("name") or "").strip()
        if bool(raw_path) == bool(name):
            raise ValueError("path 与 name 必须二选一")
        matched = None
        if name:
            target, matched = _find_start_menu(name)
        else:
            target = Path(raw_path).expanduser()
            if not target.is_absolute() or not target.is_file():
                raise ValueError(f"path 必须存在且是绝对文件路径：{raw_path}")
        args = arguments.get("args") or []
        if not isinstance(args, list) or any(not isinstance(item, str) for item in args):
            raise ValueError("args 必须是字符串数组")
        if target.suffix.lower() == ".lnk" and args:
            raise ValueError("快捷方式不接受 args；请直接传可执行文件路径")
        try:
            if target.suffix.lower() == ".lnk":
                process = _start_shortcut(target)
            else:
                process = subprocess.Popen(
                    [str(target), *args], shell=False,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, close_fds=True)
        except OSError as exc:
            raise DesktopError(f"启动失败：{type(exc).__name__}: {exc}") from exc
        timeout = require_range(as_int(arguments, "timeout_ms", 10000),
                                "timeout_ms", 100, 60000)
        title = str(arguments.get("window") or "").strip() or name
        pid = getattr(process, "pid", None)
        if not title:
            return {"pid": pid, "path": str(target), "window": None,
                    "shortcut": str(matched) if matched else None}
        port = self._backend.windows
        if port is None:
            raise DesktopUnavailable("当前平台不支持按窗口等待")
        lister = getattr(port, "list_visible", None)
        existing = {info.hwnd for info in lister()} if callable(lister) else set()
        started = time.monotonic()
        while (time.monotonic() - started) * 1000 < timeout:
            matches = tuple(port.find(title))
            if matches:
                fresh = [info for info in matches if info.hwnd not in existing]
                target_window = _pick_window(fresh or list(matches), title)
                receipt = None
                if as_bool(arguments, "activate", True):
                    receipt = port.activate(target_window.hwnd).to_dict()
                return {
                    "pid": pid, "path": str(target),
                    "shortcut": str(matched) if matched else None,
                    "window": target_window.to_dict(),
                    "matched": len(matches), "focus": receipt,
                    "waited_ms": int((time.monotonic() - started) * 1000),
                }
            time.sleep(0.15)
        return {"pid": pid, "path": str(target),
                "shortcut": str(matched) if matched else None,
                "window": None, "satisfied": False,
                "waited_ms": int((time.monotonic() - started) * 1000)}


def _start_menu_roots(roots: Optional[Sequence[Path]] = None) -> Sequence[Path]:
    if roots is not None:
        return [Path(item) for item in roots]
    if sys.platform != "win32":
        return ()
    found = []
    for env in ("ProgramData", "APPDATA"):
        base = os.environ.get(env)
        if base:
            found.append(Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return found


def _find_start_menu(name: str, roots: Optional[Sequence[Path]] = None
                     ) -> Tuple[Path, Optional[Path]]:
    """从开始菜单快捷方式中找应用；返回 (目标, 匹配到的快捷方式)。"""
    wanted = normalize_title(name)
    if not wanted:
        raise ValueError("name 不能为空")
    candidates = []
    for root in _start_menu_roots(roots):
        if not root.is_dir():
            continue
        for path in root.rglob("*.lnk"):
            if not path.is_file():
                continue
            key = normalize_title(path.stem)
            if key == wanted:
                rank = 0
            elif wanted in key:
                rank = 1
            else:
                continue
            candidates.append((rank, len(path.stem), str(path).lower(), path))
    if not candidates:
        raise ValueError(f"开始菜单里找不到应用「{name}」；请改用 path")
    candidates.sort(key=lambda item: item[:3])
    chosen = candidates[0][3]
    return chosen, chosen


def _start_shortcut(path: Path) -> Any:
    """用系统 shell 打开快捷方式；不返回 pid。失败抛 OSError。"""
    result = os.startfile(str(path))  # type: ignore[attr-defined]
    return result


def _pick_window(matches: Any, title: str) -> Any:
    """优先精确标题，再取前台，最后取第一个；避免命中浏览器里的同名标签页。"""
    from ..titles import normalize_title
    wanted = normalize_title(title)
    exact = [info for info in matches if normalize_title(info.title) == wanted]
    if exact:
        return exact[0]
    foreground = [info for info in matches if info.foreground]
    return (foreground or list(matches))[0]
