# -*- coding: utf-8 -*-
"""视觉操作 2.0 的 Windows 采集与 HID 原语。

只做系统能力调用；不包含目标应用业务、窗口控件或后台命令。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import sys
import threading
import time
from contextlib import suppress
from typing import Callable, Iterable, Optional, Tuple

from PIL import Image, ImageGrab

from agent.core.error_report import report_error

_WINDOWS = sys.platform == "win32"
_u = ctypes.windll.user32 if _WINDOWS else None
_k = ctypes.windll.kernel32 if _WINDOWS else None
_g = ctypes.windll.gdi32 if _WINDOWS else None
_mouse = _u.mouse_event if _WINDOWS else None
_key = _u.keybd_event if _WINDOWS else None


def _enable_dpi_awareness() -> None:
    """截图、GetCursorPos 和鼠标注入统一到物理屏幕像素。"""
    if not _WINDOWS:
        return
    with suppress(AttributeError, OSError):
        if _u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    with suppress(AttributeError, OSError):
        _shcore = ctypes.windll.shcore
        _shcore.SetProcessDpiAwareness(2)
        return
    with suppress(AttributeError, OSError):
        _u.SetProcessDPIAware()


_enable_dpi_awareness()

_MOUSE_LEFT = 0x0002
_MOUSE_LEFT_UP = 0x0004
_MOUSE_MOVE = 0x0001
_MOUSE_ABSOLUTE = 0x8000
_KEY_UP = 0x0002

_WM_QUIT = 0x0012
_WM_MOUSEMOVE = 0x0200
_WH_MOUSE_LL = 14
_WH_KEYBOARD_LL = 13
_LLMHF_INJECTED = 0x00000001
_LLKHF_INJECTED = 0x00000010


if _WINDOWS:
    class _MouseHookStruct(ctypes.Structure):
        _fields_ = [
            ("pt", wintypes.POINT),
            ("mouseData", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class _KeyboardHookStruct(ctypes.Structure):
        _fields_ = [
            ("vkCode", wintypes.DWORD),
            ("scanCode", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class _Message(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("message", wintypes.UINT),
            ("wParam", wintypes.WPARAM),
            ("lParam", wintypes.LPARAM),
            ("time", wintypes.DWORD),
            ("pt", wintypes.POINT),
        ]

    class _Rect(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    class _Paint(ctypes.Structure):
        _fields_ = [
            ("hdc", ctypes.c_void_p),
            ("fErase", wintypes.BOOL),
            ("rcPaint", _Rect),
            ("fRestore", wintypes.BOOL),
            ("fIncUpdate", wintypes.BOOL),
            ("rgbReserved", ctypes.c_byte * 32),
        ]

    class _WndClass(ctypes.Structure):
        _fields_ = [
            ("style", wintypes.UINT),
            ("lpfnWndProc", ctypes.c_void_p),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", ctypes.c_void_p),
            ("hIcon", ctypes.c_void_p),
            ("hCursor", ctypes.c_void_p),
            ("hbrBackground", ctypes.c_void_p),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]

    _LowLevelProc = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    _WndProc = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
        wintypes.WPARAM, wintypes.LPARAM)
else:
    _MouseHookStruct = None
    _KeyboardHookStruct = None
    _Message = None
    _Rect = None
    _Paint = None
    _WndClass = None
    _LowLevelProc = None
    _WndProc = None

if _WINDOWS:
    _u.SetWindowsHookExW.restype = ctypes.c_void_p
    _u.SetWindowsHookExW.argtypes = [
        ctypes.c_int, _LowLevelProc, ctypes.c_void_p, wintypes.DWORD]
    _u.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
    _u.CallNextHookEx.restype = ctypes.c_ssize_t
    _u.CallNextHookEx.argtypes = [
        ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    _k.GetModuleHandleW.restype = ctypes.c_void_p
    _u.PostThreadMessageW.argtypes = [
        wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _u.GetMessageW.argtypes = [
        ctypes.POINTER(_Message), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    _u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    _u.GetWindowLongW.restype = ctypes.c_long
    _u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    _u.SetWindowLongW.restype = ctypes.c_long
    _u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _u.ShowWindow.restype = ctypes.c_bool
    _u.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.UINT]
    _u.SetWindowPos.restype = ctypes.c_bool
    _u.PostMessageW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _u.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    _u.GetAncestor.restype = wintypes.HWND
    _u.SetLayeredWindowAttributes.argtypes = [
        wintypes.HWND, wintypes.DWORD, ctypes.c_byte, wintypes.DWORD]
    _u.SetLayeredWindowAttributes.restype = ctypes.c_bool
    _u.RegisterClassW.argtypes = [ctypes.POINTER(_WndClass)]
    _u.RegisterClassW.restype = ctypes.c_ushort
    _u.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    _u.CreateWindowExW.restype = wintypes.HWND
    _u.BeginPaint.argtypes = [wintypes.HWND, ctypes.POINTER(_Paint)]
    _u.BeginPaint.restype = ctypes.c_void_p
    _u.EndPaint.argtypes = [wintypes.HWND, ctypes.POINTER(_Paint)]
    _u.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(_Rect)]
    _u.DrawTextW.argtypes = [
        ctypes.c_void_p, wintypes.LPCWSTR, ctypes.c_int,
        ctypes.POINTER(_Rect), wintypes.UINT]
    _u.DestroyWindow.argtypes = [wintypes.HWND]
    _u.DefWindowProcW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _u.DefWindowProcW.restype = ctypes.c_ssize_t
    _u.TranslateMessage.argtypes = [ctypes.POINTER(_Message)]
    _u.DispatchMessageW.argtypes = [ctypes.POINTER(_Message)]
    _g.SetBkMode.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _g.SetTextColor.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    _g.CreateSolidBrush.argtypes = [wintypes.DWORD]
    _g.CreateSolidBrush.restype = ctypes.c_void_p
    _u.FillRect.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(_Rect), ctypes.c_void_p]
    _g.CreateFontW.argtypes = [
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
        wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
        wintypes.DWORD, wintypes.LPCWSTR]
    _g.CreateFontW.restype = ctypes.c_void_p
    _g.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _g.SelectObject.restype = ctypes.c_void_p
    _g.DeleteObject.argtypes = [ctypes.c_void_p]

_KEYS = {
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "shift": 0x10,
    "win": 0x5B,
    "enter": 0x0D,
    "return": 0x0D,
    "esc": 0x1B,
    "escape": 0x1B,
    "tab": 0x09,
    "space": 0x20,
    "backspace": 0x08,
    "delete": 0x2E,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
}


class HumanInputMonitor:
    """低层钩子：只报告人类鼠标/键盘，忽略本进程注入的事件。"""

    def __init__(self, takeover_distance: int = 100) -> None:
        self._callback: Optional[Callable[[], None]] = None
        self._takeover_distance = max(1, int(takeover_distance))
        self._mouse_lock = threading.Lock()
        self._mouse_point: Optional[Tuple[int, int]] = None
        self._mouse_distance = 0.0
        self._thread: Optional[threading.Thread] = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._failed = False
        self._mouse_hook: Optional[int] = None
        self._keyboard_hook: Optional[int] = None
        self._mouse_proc: Optional[Callable[..., int]] = None
        self._keyboard_proc: Optional[Callable[..., int]] = None
        self._fire_lock = threading.Lock()
        self._firing = False

    def bind(self, callback: Callable[[], None]) -> None:
        self._callback = callback

    def start(self) -> bool:
        if not _WINDOWS:
            return False
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return True
            self._failed = False
            self._reset_mouse()
            self._ready.clear()
            self._thread = threading.Thread(
                target=self._run, name="visual-input-monitor", daemon=True)
            self._thread.start()
        self._ready.wait(1.0)
        return not self._failed

    def stop(self) -> None:
        self._reset_mouse()
        with self._lock:
            thread = self._thread
            thread_id = self._thread_id
            self._thread = None
            self._thread_id = 0
        if thread is None or not thread.is_alive():
            return
        if thread is threading.current_thread():
            return
        if thread_id:
            _u.PostThreadMessageW(thread_id, _WM_QUIT, 0, 0)
        thread.join(timeout=1.0)

    def _run(self) -> None:
        self._thread_id = int(_k.GetCurrentThreadId())
        try:
            self._mouse_proc = _LowLevelProc(self._on_mouse)
            self._keyboard_proc = _LowLevelProc(self._on_keyboard)
            module = _k.GetModuleHandleW(None)
            self._mouse_hook = _u.SetWindowsHookExW(
                _WH_MOUSE_LL, self._mouse_proc, module, 0)
            self._keyboard_hook = _u.SetWindowsHookExW(
                _WH_KEYBOARD_LL, self._keyboard_proc, module, 0)
            self._failed = not bool(self._mouse_hook and self._keyboard_hook)
        except Exception as exc:
            report_error("plugins.visual_operator_2.input_monitor.start", exc)
            self._failed = True
        finally:
            self._ready.set()
        if self._failed:
            if self._mouse_hook:
                _u.UnhookWindowsHookEx(self._mouse_hook)
            if self._keyboard_hook:
                _u.UnhookWindowsHookEx(self._keyboard_hook)
            self._mouse_hook = None
            self._keyboard_hook = None
            return
        message = _Message()
        try:
            while _u.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                pass
        finally:
            if self._mouse_hook:
                _u.UnhookWindowsHookEx(self._mouse_hook)
            if self._keyboard_hook:
                _u.UnhookWindowsHookEx(self._keyboard_hook)
            self._mouse_hook = None
            self._keyboard_hook = None

    def _reset_mouse(self) -> None:
        with self._mouse_lock:
            self._mouse_point = None
            self._mouse_distance = 0.0

    def record_human_move(self, x: int, y: int) -> None:
        with self._mouse_lock:
            point = (int(x), int(y))
            if self._mouse_point is None:
                self._mouse_point = point
                return
            last_x, last_y = self._mouse_point
            distance = ((point[0] - last_x) ** 2
                        + (point[1] - last_y) ** 2) ** 0.5
            self._mouse_point = point
            self._mouse_distance += distance
            if self._mouse_distance < self._takeover_distance:
                return
            self._mouse_distance = 0.0
        self._fire()

    def _on_mouse(self, code: int, wparam: int, lparam: int) -> int:
        if code >= 0:
            info = ctypes.cast(
                lparam, ctypes.POINTER(_MouseHookStruct)).contents
            point = (int(info.pt.x), int(info.pt.y))
            if int(info.flags) & _LLMHF_INJECTED:
                with self._mouse_lock:
                    self._mouse_point = point
                    self._mouse_distance = 0.0
            elif wparam == _WM_MOUSEMOVE:
                self.record_human_move(point[0], point[1])
            else:
                self._reset_mouse()
                self._fire()
        return _u.CallNextHookEx(self._mouse_hook, code, wparam, lparam)

    def _on_keyboard(self, code: int, wparam: int, lparam: int) -> int:
        if code >= 0:
            info = ctypes.cast(
                lparam, ctypes.POINTER(_KeyboardHookStruct)).contents
            if not (int(info.flags) & _LLKHF_INJECTED):
                self._fire()
        return _u.CallNextHookEx(self._keyboard_hook, code, wparam, lparam)

    def _fire(self) -> None:
        with self._fire_lock:
            if self._firing:
                return
            self._firing = True
        threading.Thread(
            target=self._fire_worker, name="visual-input-takeover",
            daemon=True).start()

    def _fire_worker(self) -> None:
        callback = self._callback
        try:
            if callback is not None:
                callback()
        except Exception as exc:
            report_error("plugins.visual_operator_2.input_monitor.callback", exc)
        finally:
            with self._fire_lock:
                self._firing = False


class ControlBadge:
    """屏幕正上方的置顶控制标签；点击穿透、透明背景、不抢焦点。"""

    _CLASS_NAME = "VisualOperatorControlBadge"
    _COLOR_KEY = 0x00030201  # RGB(1, 2, 3)

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._hwnd: Optional[int] = None
        self._ready = threading.Event()
        self._failed = False
        self._wanted = False
        self._wndproc: Optional[Callable[..., int]] = None

    def show(self) -> None:
        if not _WINDOWS:
            return
        with self._lock:
            self._wanted = True
            hwnd = self._hwnd
            if hwnd:
                _u.ShowWindow(hwnd, 4)
                _u.SetLayeredWindowAttributes(
                    hwnd, self._COLOR_KEY, 255, 0x00000003)
                _u.SetWindowPos(hwnd, -1, 0, 0, 0, 0,
                                0x0001 | 0x0002 | 0x0010 | 0x0040)
                return
            if self._thread is not None and self._thread.is_alive():
                return
            self._failed = False
            self._reset_mouse()
            self._ready.clear()
            self._thread = threading.Thread(
                target=self._run, name="visual-control-badge", daemon=True)
            self._thread.start()
        self._ready.wait(1.0)
        if self._failed:
            report_error("plugins.visual_operator_2.control_badge",
                         RuntimeError("置顶标签窗口创建失败"))

    def hide(self) -> None:
        self._wanted = False
        hwnd = self._hwnd
        if hwnd and _WINDOWS:
            _u.SetLayeredWindowAttributes(hwnd, 0, 0, 0x00000002)
            _u.ShowWindow(hwnd, 0)

    def close(self) -> None:
        self.hide()
        hwnd = self._hwnd
        if hwnd and _WINDOWS:
            _u.PostMessageW(hwnd, 0x0010, 0, 0)

    def _run(self) -> None:
        hwnd = 0
        try:
            self._wndproc = _WndProc(self._on_message)
            wc = _WndClass()
            wc.lpfnWndProc = ctypes.cast(self._wndproc, ctypes.c_void_p)
            wc.hInstance = _k.GetModuleHandleW(None)
            wc.lpszClassName = self._CLASS_NAME
            _u.RegisterClassW(ctypes.byref(wc))
            screen_w = int(_u.GetSystemMetrics(0))
            width = 160
            height = 30
            x = max(0, (screen_w - width) // 2)
            hwnd = _u.CreateWindowExW(
                0x00080000 | 0x00000008 | 0x00000020 | 0x00000080
                | 0x08000000,
                self._CLASS_NAME, "[AI控制中]", 0x80000000,
                x, 2, width, height, 0, 0, wc.hInstance, 0)
            if not hwnd:
                raise RuntimeError("CreateWindowExW failed")
            self._hwnd = int(hwnd)
            _u.SetLayeredWindowAttributes(
                self._hwnd, self._COLOR_KEY, 255, 0x00000003)
            _u.SetWindowPos(self._hwnd, -1, x, 2, width, height,
                            0x0001 | 0x0002 | 0x0010 | 0x0040)
            _u.ShowWindow(self._hwnd, 4 if self._wanted else 0)
            self._ready.set()
            message = _Message()
            while _u.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                _u.TranslateMessage(ctypes.byref(message))
                _u.DispatchMessageW(ctypes.byref(message))
        except Exception as exc:
            report_error("plugins.visual_operator_2.control_badge.run", exc)
            self._failed = True
        finally:
            if hwnd:
                _u.DestroyWindow(hwnd)
            self._hwnd = None
            self._ready.set()

    def _on_message(self, hwnd: int, message: int, wparam: int,
                    lparam: int) -> int:
        if message == 0x000F:  # WM_PAINT
            paint = _Paint()
            hdc = _u.BeginPaint(hwnd, ctypes.byref(paint))
            try:
                rect = _Rect()
                _u.GetClientRect(hwnd, ctypes.byref(rect))
                brush = _g.CreateSolidBrush(self._COLOR_KEY)
                try:
                    _u.FillRect(hdc, ctypes.byref(rect), brush)
                finally:
                    _g.DeleteObject(brush)
                _g.SetBkMode(hdc, 1)
                _g.SetTextColor(hdc, 0xFFFFFF)
                font = _g.CreateFontW(
                    -20, 0, 0, 0, 700, 0, 0, 0, 1, 0, 0, 5, 0,
                    "Microsoft YaHei")
                old = _g.SelectObject(hdc, font)
                try:
                    text = "[AI控制中]"
                    buf = ctypes.create_unicode_buffer(text)
                    _u.DrawTextW(hdc, buf, -1, ctypes.byref(rect),
                                 0x00000001 | 0x00000004 | 0x00000020)
                finally:
                    _g.SelectObject(hdc, old)
                    _g.DeleteObject(font)
            finally:
                _u.EndPaint(hwnd, ctypes.byref(paint))
            return 0
        if message == 0x0014:  # WM_ERASEBKGND
            return 1
        if message == 0x0010:  # WM_CLOSE
            _u.DestroyWindow(hwnd)
            return 0
        if message == 0x0002:  # WM_DESTROY
            _u.PostQuitMessage(0)
            return 0
        return _u.DefWindowProcW(hwnd, message, wparam, lparam)

def capture_screen() -> Image.Image:
    """抓主屏像素。"""
    if not _WINDOWS:
        raise RuntimeError("视觉操作 2.0 当前只支持 Windows")
    return ImageGrab.grab().convert("RGB")


def cursor_position() -> Tuple[int, int]:
    if not _WINDOWS:
        raise RuntimeError("视觉操作 2.0 当前只支持 Windows")
    point = wintypes.POINT()
    if not _u.GetCursorPos(ctypes.byref(point)):
        raise OSError("GetCursorPos failed")
    return int(point.x), int(point.y)


def set_cursor(x: int, y: int) -> None:
    if not _WINDOWS:
        raise RuntimeError("视觉操作 2.0 当前只支持 Windows")
    width = max(1, int(_u.GetSystemMetrics(0)))
    height = max(1, int(_u.GetSystemMetrics(1)))
    safe_x = max(0, min(width - 1, int(x)))
    safe_y = max(0, min(height - 1, int(y)))
    norm_x = round(safe_x * 65535 / max(1, width - 1))
    norm_y = round(safe_y * 65535 / max(1, height - 1))
    _mouse(_MOUSE_MOVE | _MOUSE_ABSOLUTE, norm_x, norm_y, 0, 0)


def move_by(dx: int, dy: int) -> Tuple[int, int]:
    x, y = cursor_position()
    set_cursor(x + int(dx), y + int(dy))
    return x, y


_left_down = False


def release_left() -> None:
    """释放由本模块注入的左键，防止轨迹移动变成拖拽。"""
    global _left_down
    if _left_down:
        _mouse(_MOUSE_LEFT_UP, 0, 0, 0, 0)
        _left_down = False


def move_cursor(x: int, y: int, duration_ms: int = 200,
                should_stop: Optional[Callable[[], bool]] = None) -> bool:
    """按时长插值移动鼠标；被用户接管时返回 False。"""
    release_left()
    target_x, target_y = int(x), int(y)
    duration = max(0, min(2000, int(duration_ms)))
    if duration <= 0:
        set_cursor(target_x, target_y)
        return not (should_stop and should_stop())
    start_x, start_y = cursor_position()
    steps = max(1, min(60, duration // 10))
    for index in range(1, steps + 1):
        if should_stop is not None and should_stop():
            return False
        ratio = index / float(steps)
        set_cursor(round(start_x + (target_x - start_x) * ratio),
                   round(start_y + (target_y - start_y) * ratio))
        time.sleep(duration / 1000.0 / steps)
    if should_stop is not None and should_stop():
        return False
    set_cursor(target_x, target_y)
    return True


def click(button: str = "left", count: int = 1) -> None:
    if not _WINDOWS:
        raise RuntimeError("视觉操作 2.0 当前只支持 Windows")
    if button != "left":
        raise ValueError("目前只支持左键")
    global _left_down
    for _ in range(max(1, min(3, int(count)))):
        _mouse(_MOUSE_LEFT, 0, 0, 0, 0)
        _left_down = True
        try:
            time.sleep(0.010)
            _mouse(_MOUSE_LEFT_UP, 0, 0, 0, 0)
        finally:
            _left_down = False


def _key_code(name: str) -> int:
    value = str(name or "").strip().lower()
    if value in _KEYS:
        return _KEYS[value]
    if len(value) == 1:
        return ord(value.upper())
    raise ValueError(f"未知按键：{name}")


def press_keys(keys: Iterable[str]) -> None:
    if not _WINDOWS:
        raise RuntimeError("视觉操作 2.0 当前只支持 Windows")
    codes = [_key_code(key) for key in keys]
    if not codes:
        raise ValueError("keys 不能为空")
    for code in codes:
        _key(code, 0, 0, 0)
    for code in reversed(codes):
        _key(code, 0, _KEY_UP, 0)


__all__ = [
    "HumanInputMonitor", "capture_screen", "click", "cursor_position",
    "move_by", "press_keys", "set_cursor",
]
