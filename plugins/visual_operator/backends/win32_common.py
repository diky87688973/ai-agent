# -*- coding: utf-8 -*-
"""Windows 后端：GDI 截屏 + SendInput 输入。

坐标全部是屏幕物理像素。进程先声明 per-monitor v2 DPI 感知：截屏用虚拟
桌面坐标，SetCursorPos 也按物理像素落点，混合缩放的多屏不会整体偏移。
"""
from __future__ import annotations

import ctypes
from contextlib import suppress
from ctypes import wintypes
from typing import Sequence, Tuple

from ..coords import ScreenRect
from ..keys import DIGITS, LETTERS

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
try:
    shcore = ctypes.WinDLL("shcore", use_last_error=True)
except OSError:  # Windows 8.1 之前没有 shcore
    shcore = None

SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x00400000
DIB_RGB_COLORS = 0

SM_CXSCREEN = 0
SM_CYSCREEN = 1
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x01000

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

_BUTTONS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}

_VK_NAMED = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "shift": 0x10,
    "ctrl": 0x11, "alt": 0x12, "capslock": 0x14, "esc": 0x1B,
    "space": 0x20, "pageup": 0x21, "pagedown": 0x22, "end": 0x23,
    "home": 0x24, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "insert": 0x2D, "delete": 0x2E, "win": 0x5B, "cmd": 0x5B,
    **{f"f{index}": 0x6F + index for index in range(1, 25)},
    **{letter: ord(letter.upper()) for letter in LETTERS},
    **{digit: ord(digit) for digit in DIGITS},
    "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC,
    ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF, "`": 0xC0,
}


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


_MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
    ctypes.POINTER(wintypes.RECT), wintypes.LPARAM,
)
_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

PW_RENDERFULLCONTENT = 0x00000002
SW_RESTORE = 9
SW_SHOWNOACTIVATE = 4
GW_OWNER = 4
GA_ROOT = 2
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080

# 窗口从最小化恢复后，Chromium/CEF 一类自绘窗口需要一次真实重绘才产出内容。
# 实测约 440ms；给 1.2s 上限，超时就走屏幕回退并如实标注。
_REPAINT_TIMEOUT_SECONDS = 1.2
_REPAINT_INTERVAL_SECONDS = 0.06
# 激活是一次系统级交接：窗口管理器要处理置前与重绘。实测 3/3 在 100ms 内完成，
# 给 0.6s 上限足够判定成败，又不会让一次失败的激活拖慢整批动作。
_ACTIVATE_TIMEOUT_SECONDS = 0.6
_UNIFORM_SAMPLE = 4096

user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
user32.SetCursorPos.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = (ctypes.POINTER(POINT),)
user32.GetCursorPos.restype = wintypes.BOOL
user32.GetDC.argtypes = (wintypes.HWND,)
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
user32.EnumDisplayMonitors.argtypes = (
    wintypes.HDC, ctypes.POINTER(wintypes.RECT), _MONITORENUMPROC, wintypes.LPARAM)
gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = (wintypes.HDC, ctypes.c_int, ctypes.c_int)
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.BitBlt.argtypes = (
    wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD)
gdi32.BitBlt.restype = wintypes.BOOL
gdi32.GetDIBits.argtypes = (
    wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
    ctypes.c_void_p, ctypes.POINTER(BITMAPINFO), wintypes.UINT)
gdi32.GetDIBits.restype = ctypes.c_int
gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
gdi32.DeleteDC.argtypes = (wintypes.HDC,)
user32.PrintWindow.argtypes = (wintypes.HWND, wintypes.HDC, wintypes.UINT)
user32.PrintWindow.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
user32.GetWindowRect.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetWindowTextW.restype = ctypes.c_int
user32.IsWindow.argtypes = (wintypes.HWND,)
user32.IsWindow.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = (wintypes.HWND,)
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsIconic.argtypes = (wintypes.HWND,)
user32.IsIconic.restype = wintypes.BOOL
user32.GetWindow.argtypes = (wintypes.HWND, wintypes.UINT)
user32.GetWindow.restype = wintypes.HWND
user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
user32.GetWindowLongW.restype = wintypes.LONG
user32.EnumWindows.argtypes = (_WNDENUMPROC, wintypes.LPARAM)
user32.EnumWindows.restype = wintypes.BOOL
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.ShowWindow.restype = wintypes.BOOL
user32.SwitchToThisWindow.argtypes = (wintypes.HWND, wintypes.BOOL)
user32.SwitchToThisWindow.restype = None
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.GetForegroundWindow.argtypes = ()
user32.GetForegroundWindow.restype = wintypes.HWND
user32.MonitorFromPoint.argtypes = (POINT, wintypes.DWORD)
user32.MonitorFromPoint.restype = wintypes.HMONITOR
user32.WindowFromPoint.argtypes = (POINT,)
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
user32.GetAncestor.restype = wintypes.HWND
user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetClassNameW.restype = ctypes.c_int
if shcore is not None:
    shcore.GetDpiForMonitor.argtypes = (
        wintypes.HMONITOR, ctypes.c_int,
        ctypes.POINTER(wintypes.UINT), ctypes.POINTER(wintypes.UINT))
    shcore.GetDpiForMonitor.restype = ctypes.c_long


def _enable_dpi_awareness() -> None:
    """声明 per-monitor v2；系统已由宿主声明时沿用宿主的选择。"""
    with suppress(AttributeError, OSError):
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    if shcore is not None:
        with suppress(AttributeError, OSError):
            shcore.SetProcessDpiAwareness(2)
            return
    with suppress(AttributeError, OSError):
        user32.SetProcessDPIAware()


def _last_error(message: str) -> str:
    code = ctypes.get_last_error()
    return f"{message} 失败（WinError {code}）" if code else f"{message} 失败"


def _system_metric(index: int) -> int:
    return int(user32.GetSystemMetrics(index))


def _monitor_rects() -> Tuple[ScreenRect, ...]:
    rects = []

    def _collect(_monitor, _dc, _rect, _data):
        rect = _rect.contents
        try:
            rects.append(ScreenRect(rect.left, rect.top,
                                    rect.right - rect.left, rect.bottom - rect.top))
        except ValueError:
            return True
        return True

    user32.EnumDisplayMonitors(None, None, _MONITORENUMPROC(_collect), 0)
    return tuple(rects)


def _monitor_dpis(rects: Sequence[ScreenRect]) -> Tuple[int, ...]:
    if shcore is None or not rects:
        return ()
    values = []
    for rect in rects:
        x = wintypes.UINT()
        y = wintypes.UINT()
        monitor = user32.MonitorFromPoint(
            POINT(rect.x + rect.width // 2, rect.y + rect.height // 2), 2)
        if not monitor:
            continue
        if shcore.GetDpiForMonitor(monitor, 0, ctypes.byref(x), ctypes.byref(y)) == 0:
            values.append(int(x.value))
    return tuple(values)
