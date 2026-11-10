# -*- coding: utf-8 -*-
"""窗口级 Win32 操作：句柄取值、深色标题栏、图标、居中几何、前台激活、最大化边界。

只管「怎么操作一个已经存在的窗口」，不关心窗口从哪来、服务是否就绪 ——
那些属于启动器（`agent.gui.launcher`）。非 Windows 平台一律不动窗口，
也不引入 WinForms / DWM 依赖。
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Any, Tuple

from agent.core.error_report import report_error


def _pointer_int(value: Any) -> int:
    """把 pywebview 的句柄/指针值取成 int；空值按 0。"""
    if value is None:
        return 0
    to_int = getattr(value, "ToInt64", None)
    if callable(to_int):
        return int(to_int())
    return int(value)


def window_handle(window: Any) -> int:
    """窗口的原生句柄；取不到返回 0。"""
    native = getattr(window, "native", None)
    return _pointer_int(getattr(native, "Handle", 0))


def apply_dark_titlebar(window: Any) -> None:
    """标题栏切深色（DWM 属性 20）。"""
    if os.name != "nt":
        return
    try:
        hwnd = window_handle(window)
        if not hwnd:
            return
        enabled = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(enabled), ctypes.sizeof(enabled)
        )
    except (AttributeError, OSError, ValueError) as exc:
        report_error("agent.gui.window_ops.dark_titlebar", exc)


def activate_window(window: Any) -> None:
    """把窗口带到前台并抢焦点。

    前台锁会让 `SetForegroundWindow` 静默失败，所以要挂接前台线程的输入队列；
    先发一次 Alt（`keybd_event` 0x12）是让系统把本进程视为最近有输入。
    """
    if os.name != "nt":
        return
    hwnd = window_handle(window)
    if not hwnd:
        return
    try:
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)
        user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
        user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0003)
        user32.BringWindowToTop(hwnd)
        foreground = user32.GetForegroundWindow()
        if foreground == hwnd:
            return
        user32.keybd_event(0x12, 0, 0, 0)
        user32.keybd_event(0x12, 0, 2, 0)
        foreground_thread = user32.GetWindowThreadProcessId(foreground, None)
        current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
        if foreground_thread and foreground_thread != current_thread:
            user32.AttachThreadInput(current_thread, foreground_thread, True)
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
            user32.AttachThreadInput(current_thread, foreground_thread, False)
        else:
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
        user32.SwitchToThisWindow(hwnd, True)
    except (AttributeError, OSError) as exc:
        report_error("agent.gui.window_ops.activate", exc)


def apply_window_icon(window: Any, icon_path: Path) -> None:
    """设置窗口图标；`icon_path` 不存在时不动。

    图标文件归调用方提供：本模块不猜应用根在哪。
    参数已声明为 `Path`，直接用它：本函数只在 Windows 分支执行，
    在非 Windows 上重新构造 `Path` 会按当前 `os.name` 选错实现。
    """
    if os.name != "nt":
        return
    hwnd = window_handle(window)
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
        report_error("agent.gui.window_ops.window_icon_handle", exc)


def centered_geometry(width: int, height: int) -> Tuple[int, int, int, int]:
    """按工作区居中：返回 (宽, 高, x, y)。

    非 Windows 或取不到工作区时坐标归 0，尺寸原样返回。
    """
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


def apply_maximized_bounds(window: Any) -> None:
    """让最大化贴着工作区，而不是盖住任务栏（WinForms 的 MaximizedBounds）。"""
    if os.name != "nt":
        return
    try:
        from System.Windows.Forms import Screen

        native = getattr(window, "native", None)
        if native is None:
            return
        native.MaximizedBounds = Screen.FromHandle(native.Handle).WorkingArea
    except (ImportError, AttributeError, OSError, ValueError) as exc:
        report_error("agent.gui.window_ops.maximized_bounds", exc)


__all__ = [
    "activate_window",
    "apply_dark_titlebar",
    "apply_maximized_bounds",
    "apply_window_icon",
    "centered_geometry",
]
