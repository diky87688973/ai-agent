# -*- coding: utf-8 -*-
"""GUI 启动器：启动并维护自己的 Web 服务子进程，然后在嵌入式 WebView 中打开 Web UI。

Windows 使用 Edge WebView2；macOS 使用 WKWebView。
窗口关闭或启动失败时终止子进程；不把后端打包进 GUI。
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, List, Optional

from agent.core.error_report import report_error

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 3156
DEFAULT_TIMEOUT = 30.0


def _health_url(host: str, port: int) -> str:
    return f"http://{host}:{int(port)}/health"


def _is_agent_health(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(_health_url(host, port), timeout=timeout) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except (OSError, ValueError, urllib.error.URLError):
        return False
    return isinstance(payload, dict) and bool(payload.get("ok")) \
        and str(payload.get("service") or "") == "agent.web"


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _python_command() -> Optional[List[str]]:
    """按 python、python3、py 的顺序检测可执行解释器。"""
    for name in ("python", "python3", "py"):
        executable = shutil.which(name)
        if not executable:
            continue
        try:
            result = subprocess.run(
                [executable, "-c", "import sys"],
                cwd=str(_app_root()),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            report_error("agent.gui.launcher.python_probe", exc, executable=name)
            continue
        if result.returncode == 0:
            return [executable]
    print("未找到可用的 Python，请配置 PATH 环境变量。", file=sys.stderr)
    return None


def _web_command() -> Optional[List[str]]:
    """只认两个位置：同目录 agent-web.exe，或同目录源码 web.py。"""
    root = _app_root()
    web_exe = root / "agent-web.exe"
    if web_exe.is_file():
        return [str(web_exe)]
    web_py = root / "agent" / "entry" / "web.py"
    if web_py.is_file():
        python = _python_command()
        if python:
            return [*python, "-m", "agent.entry.web"]
    return None


def _spawn_server(host: str, port: int) -> Optional[subprocess.Popen]:
    command = _web_command()
    if command is None:
        print("找不到 Web 服务入口。", file=sys.stderr)
        return None
    options: dict[str, Any] = {
        "cwd": str(_app_root()),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "env": {**os.environ, "AI_AGENT_GUI": "1"},
    }
    if os.name == "nt":
        options["creationflags"] = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    else:
        options["start_new_session"] = True
    try:
        return subprocess.Popen(
            [*command, "--host", host, "--port", str(int(port))],
            **options,
        )
    except OSError as exc:
        print(f"启动 Web 服务失败：{exc}", file=sys.stderr)
        return None


def _wait_health(host: str, port: int, timeout: float) -> bool:
    deadline = time.monotonic() + max(0.1, float(timeout))
    while time.monotonic() < deadline:
        if _is_agent_health(host, port):
            return True
        time.sleep(0.15)
    return _is_agent_health(host, port)


def _pointer_int(value: Any) -> int:
    if value is None:
        return 0
    to_int = getattr(value, "ToInt64", None)
    if callable(to_int):
        return int(to_int())
    return int(value)


def _apply_maximized_bounds(window: Any) -> None:
    if os.name != "nt":
        return
    try:
        from System.Windows.Forms import Screen

        native = getattr(window, "native", None)
        if native is None:
            return
        native.MaximizedBounds = Screen.FromHandle(native.Handle).WorkingArea
    except (ImportError, AttributeError, OSError, ValueError) as exc:
        report_error("agent.gui.launcher.maximized_bounds", exc)


class _WindowApi:
    """暴露给页面标题栏的最小窗口控制接口。"""

    def __init__(self, supervisor: Optional["_ServerSupervisor"] = None) -> None:
        self._window: Any = None
        self._supervisor = supervisor

    def minimize(self) -> bool:
        if self._window is not None:
            self._window.minimize()
        return True

    def toggle_maximize(self, maximized: bool) -> bool:
        if self._window is not None:
            if maximized:
                if os.name == "nt":
                    _apply_maximized_bounds(self._window)
                self._window.maximize()
            else:
                self._window.restore()
        return True

    def close(self) -> bool:
        if self._window is not None:
            self._window.destroy()
        return True

    def ensure_server(self) -> bool:
        if self._supervisor is None:
            return False
        return self._supervisor.ensure_alive()

    def window_position(self) -> list:
        if self._window is None:
            return [0, 0]
        return [int(self._window.x), int(self._window.y)]

    def move_window(self, x: int, y: int) -> bool:
        if self._window is not None:
            self._window.move(int(x), int(y))
        return True

    def window_size(self) -> list:
        if self._window is None:
            return [0, 0]
        return [int(self._window.width), int(self._window.height)]

    def resize_window(self, width: int, height: int,
                      x: int | None = None, y: int | None = None) -> bool:
        if self._window is None:
            return False
        self._window.resize(max(640, int(width)), max(480, int(height)))
        if x is not None and y is not None:
            self._window.move(int(x), int(y))
        return True


def _pick_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _stop_server(proc: Optional[subprocess.Popen]) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


class _WindowsJob:
    """父进程退出时由系统终止子进程树。"""

    def __init__(self) -> None:
        self._handle: Any = None
        self._kernel32: Any = None
        if os.name != "nt":
            return
        try:
            self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("ReadOperationCount", ctypes.c_ulonglong),
                    ("WriteOperationCount", ctypes.c_ulonglong),
                    ("OtherOperationCount", ctypes.c_ulonglong),
                    ("ReadTransferCount", ctypes.c_ulonglong),
                    ("WriteTransferCount", ctypes.c_ulonglong),
                    ("OtherTransferCount", ctypes.c_ulonglong),
                ]

            class BASIC_LIMIT(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_longlong),
                    ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", ctypes.c_ulong),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", ctypes.c_ulong),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", ctypes.c_ulong),
                    ("SchedulingClass", ctypes.c_ulong),
                ]

            class EXTENDED_LIMIT(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", BASIC_LIMIT),
                    ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            self._extended_limit = EXTENDED_LIMIT
            handle = self._kernel32.CreateJobObjectW(None, None)
            if not handle:
                return
            info = EXTENDED_LIMIT()
            info.BasicLimitInformation.LimitFlags = 0x2000
            if not self._kernel32.SetInformationJobObject(
                handle, 9, ctypes.byref(info), ctypes.sizeof(info)
            ):
                self._kernel32.CloseHandle(handle)
                return
            self._handle = handle
        except (AttributeError, OSError):
            self._handle = None

    def assign(self, proc: Optional[subprocess.Popen]) -> None:
        if not self._handle or proc is None:
            return
        handle = int(getattr(proc, "_handle", 0) or 0)
        if handle:
            try:
                self._kernel32.AssignProcessToJobObject(self._handle, handle)
            except (AttributeError, OSError) as exc:
                report_error("agent.gui.launcher.job_assign", exc)

    def close(self) -> None:
        if self._handle:
            try:
                self._kernel32.CloseHandle(self._handle)
            except (AttributeError, OSError) as exc:
                report_error("agent.gui.launcher.job_close", exc)
            self._handle = None


class _ServerSupervisor:
    """维护唯一 Web 服务子进程；异常退出时重启并通知界面刷新。"""

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._proc: Optional[subprocess.Popen] = None
        self._job = _WindowsJob()

    def start(self) -> bool:
        self._proc = self._spawn()
        return self._proc is not None

    def _spawn(self) -> Optional[subprocess.Popen]:
        proc = _spawn_server(self.host, self.port)
        if proc is not None:
            self._proc = proc
            self._job.assign(proc)
        return proc

    def wait_ready(self) -> bool:
        return _wait_health(self.host, self.port, self.timeout)

    def ensure_alive(self) -> bool:
        """子进程已退出时重启；返回是否发生了重启。"""
        proc = self._proc
        if proc is not None and proc.poll() is None:
            return False
        proc = self._spawn()
        if proc is None:
            return False
        if not self.wait_ready():
            _stop_server(proc)
            return False
        return True

    def stop(self) -> None:
        _stop_server(self._proc)
        self._job.close()


def _storage_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    path = base / "ai-agent" / "webview"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _apply_dark_titlebar(window: Any) -> None:
    if os.name != "nt":
        return
    try:
        native = getattr(window, "native", None)
        hwnd = _pointer_int(getattr(native, "Handle", 0))
        if not hwnd:
            return
        enabled = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(enabled), ctypes.sizeof(enabled)
        )
    except (AttributeError, OSError, ValueError) as exc:
        report_error("agent.gui.launcher.dark_titlebar", exc)


def _window_handle(window: Any) -> int:
    native = getattr(window, "native", None)
    return _pointer_int(getattr(native, "Handle", 0))


def _apply_window_icon(window: Any) -> None:
    if os.name != "nt":
        return
    hwnd = _window_handle(window)
    icon_path = _app_root() / "assets" / "icon.ico"
    if not hwnd or not icon_path.is_file():
        return
    try:
        user32 = ctypes.windll.user32
        user32.LoadImageW.restype = ctypes.c_void_p
        user32.LoadImageW.argtypes = [
            ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint,
            ctypes.c_int, ctypes.c_int, ctypes.c_uint,
        ]
        icon = user32.LoadImageW(None, str(icon_path), 1, 0, 0, 0x10)
        if icon:
            user32.SendMessageW.restype = ctypes.c_ssize_t
            user32.SendMessageW.argtypes = [
                ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t,
            ]
            user32.SendMessageW(hwnd, 0x80, 1, icon)
            user32.SendMessageW(hwnd, 0x80, 0, icon)
    except (AttributeError, OSError) as exc:
        report_error("agent.gui.launcher.window_icon_handle", exc)


def _centered_geometry(width: int, height: int) -> tuple[int, int, int, int]:
    if os.name != "nt":
        return width, height, 0, 0
    try:
        from ctypes import wintypes

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", wintypes.LONG),
                ("top", wintypes.LONG),
                ("right", wintypes.LONG),
                ("bottom", wintypes.LONG),
            ]

        rect = RECT()
        if not ctypes.windll.user32.SystemParametersInfoW(
            48, 0, ctypes.byref(rect), 0
        ):
            return width, height, 0, 0
        work_width = max(640, int(rect.right - rect.left))
        work_height = max(480, int(rect.bottom - rect.top))
        width = min(width, work_width)
        height = min(height, work_height)
        x = int(rect.left + (work_width - width) / 2)
        y = int(rect.top + (work_height - height) / 2)
        return width, height, x, y
    except (AttributeError, OSError, ValueError):
        return width, height, 0, 0


def _open_window(url: str, supervisor: Optional[_ServerSupervisor] = None) -> bool:
    try:
        from agent.gui.bootstrap import deps_dir
        deps = deps_dir()
        if deps.is_dir():
            import sys as _sys
            _sys.path.insert(0, str(deps))
        import webview
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.fan.aiagent")
        except (AttributeError, OSError) as exc:
            report_error("agent.gui.launcher.app_id", exc)
        webview.settings["DRAG_REGION_DIRECT_TARGET_ONLY"] = True
    except ImportError:
        print("缺少 pywebview；请安装 GUI 依赖。", file=sys.stderr)
        return False
    try:
        api = _WindowApi(supervisor)
        width, height, x, y = _centered_geometry(1440, 900)
        window = webview.create_window(
            "AI Agent",
            url,
            width=width,
            height=height,
            x=x,
            y=y,
            background_color="#1e1e1e",
            frameless=True,
            easy_drag=False,
            draggable=True,
            js_api=api,
        )
        api._window = window

        def shown() -> None:
            _apply_dark_titlebar(window)
            _apply_window_icon(window)
            _apply_maximized_bounds(window)

        window.events.shown += shown
        window.expose(api.minimize, api.toggle_maximize, api.close, api.ensure_server, api.window_position, api.move_window, api.window_size, api.resize_window)
        icon = _app_root() / "assets" / "icon.ico"
        webview.start(private_mode=False, storage_path=str(_storage_path()),
                      icon=str(icon) if icon.is_file() else None)
    except Exception as exc:
        print(f"打开 WebView 失败：{exc}", file=sys.stderr)
        return False
    return True


def launch(host: str, port: int, *, open_window: bool = True,
           timeout: float = DEFAULT_TIMEOUT) -> int:
    if port <= 0:
        port = _pick_port(host)
    elif _is_agent_health(host, port):
        print("指定端口已被占用。", file=sys.stderr)
        return 1
    supervisor = _ServerSupervisor(host, port, timeout)
    if not supervisor.start():
        return 1
    try:
        ready = supervisor.wait_ready()
        if not ready:
            print("Web 服务在超时前没有就绪。", file=sys.stderr)
            return 1
        if open_window and not _open_window(f"http://{host}:{int(port)}/", supervisor):
            return 1
        return 0
    finally:
        supervisor.stop()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-gui")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--no-window", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    return launch(
        args.host,
        args.port,
        open_window=not args.no_window,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
