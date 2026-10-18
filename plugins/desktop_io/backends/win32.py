# -*- coding: utf-8 -*-
"""Windows 后端：GDI 截屏 + SendInput 输入。

坐标全部是屏幕物理像素。进程先声明 per-monitor v2 DPI 感知：截屏用虚拟
桌面坐标，SetCursorPos 也按物理像素落点，混合缩放的多屏不会整体偏移。
"""
from __future__ import annotations

import ctypes
import io
import time
from ctypes import wintypes
from typing import Optional, Sequence, Tuple

from ..coords import ScreenGeometry, ScreenPoint, ScreenRect
from ..errors import DesktopError, DesktopUnavailable, ScreenCaptureFailed
from ..keys import DIGITS, LETTERS
from ..ports import Backend, Screenshot

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
user32.MonitorFromPoint.argtypes = (POINT, wintypes.DWORD)
user32.MonitorFromPoint.restype = wintypes.HMONITOR
if shcore is not None:
    shcore.GetDpiForMonitor.argtypes = (
        wintypes.HMONITOR, ctypes.c_int,
        ctypes.POINTER(wintypes.UINT), ctypes.POINTER(wintypes.UINT))
    shcore.GetDpiForMonitor.restype = ctypes.c_long


def _enable_dpi_awareness() -> None:
    """声明 per-monitor v2；系统已由宿主声明时沿用宿主的选择。"""
    try:
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass
    if shcore is not None:
        try:
            shcore.SetProcessDpiAwareness(2)
            return
        except (AttributeError, OSError):
            pass
    try:
        user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


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
            pass
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


class Win32Screen:
    """屏幕几何与 GDI 截屏。"""

    def geometry(self) -> ScreenGeometry:
        virtual_width = _system_metric(SM_CXVIRTUALSCREEN)
        virtual_height = _system_metric(SM_CYVIRTUALSCREEN)
        if virtual_width > 0 and virtual_height > 0:
            rect = ScreenRect(
                _system_metric(SM_XVIRTUALSCREEN),
                _system_metric(SM_YVIRTUALSCREEN),
                virtual_width,
                virtual_height,
            )
        else:
            rect = ScreenRect(0, 0,
                              max(1, _system_metric(SM_CXSCREEN)),
                              max(1, _system_metric(SM_CYSCREEN)))
        dpis = _monitor_dpis(_monitor_rects())
        try:
            system_dpi = int(user32.GetDpiForSystem())
        except (AttributeError, OSError):
            system_dpi = 0
        dpi = dpis[0] if dpis else (system_dpi or 96)
        return ScreenGeometry(
            rect=rect,
            pixel_ratio=1.0,
            dpi=f"{dpi} dpi",
            mixed_scale=len(set(dpis)) > 1,
        )

    def capture(self, region: Optional[ScreenRect]) -> Screenshot:
        rect = region or self.geometry().rect
        data = _grab(rect)
        return Screenshot(png=_encode_bgra(data, rect.width, rect.height), rect=rect)


def _grab(rect: ScreenRect) -> bytes:
    width, height = rect.width, rect.height
    screen_dc = user32.GetDC(None)
    if not screen_dc:
        raise ScreenCaptureFailed(_last_error("GetDC"))
    memory_dc = gdi32.CreateCompatibleDC(screen_dc)
    bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
    if not memory_dc or not bitmap:
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if memory_dc:
            gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(None, screen_dc)
        raise ScreenCaptureFailed(_last_error("创建位图"))
    previous = gdi32.SelectObject(memory_dc, bitmap)
    try:
        if not gdi32.BitBlt(memory_dc, 0, 0, width, height, screen_dc,
                            rect.x, rect.y, SRCCOPY | CAPTUREBLT):
            raise ScreenCaptureFailed(_last_error("BitBlt"))
        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        # 负高度 = 自上而下的行序，PNG 编码不用再翻转。
        info.bmiHeader.biHeight = -height
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = 0
        buffer = ctypes.create_string_buffer(width * height * 4)
        if not gdi32.GetDIBits(memory_dc, bitmap, 0, height, buffer,
                               ctypes.byref(info), DIB_RGB_COLORS):
            raise ScreenCaptureFailed(_last_error("GetDIBits"))
        return buffer.raw
    finally:
        gdi32.SelectObject(memory_dc, previous)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(None, screen_dc)


def _encode_bgra(data: bytes, width: int, height: int) -> bytes:
    try:
        from PIL import Image
    except ImportError as exc:
        raise DesktopUnavailable(f"截屏编码需要 Pillow：{exc}") from exc
    image = Image.frombuffer("RGB", (width, height), data, "raw", "BGRX", 0, 1)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", compress_level=3)
    return buffer.getvalue()


class Win32Mouse:
    """SetCursorPos 定位 + SendInput 按键。"""

    def cursor(self) -> ScreenPoint:
        point = POINT()
        if not user32.GetCursorPos(ctypes.byref(point)):
            raise DesktopError(_last_error("GetCursorPos"))
        return ScreenPoint(int(point.x), int(point.y))

    def move(self, point: ScreenPoint, duration_ms: int) -> None:
        if duration_ms <= 0:
            _set_cursor(point)
            return
        start = self.cursor()
        steps = max(1, min(120, duration_ms // 10))
        for index in range(1, steps + 1):
            ratio = index / steps
            _set_cursor(ScreenPoint(
                round(start.x + (point.x - start.x) * ratio),
                round(start.y + (point.y - start.y) * ratio),
            ))
            time.sleep(duration_ms / 1000.0 / steps)

    def click(self, point: Optional[ScreenPoint], button: str, count: int) -> None:
        down, up = _BUTTONS[button]
        for index in range(count):
            if point is not None:
                _set_cursor(point)
            _send_mouse(down)
            _send_mouse(up)
            if index + 1 < count:
                time.sleep(0.02)

    def drag(self, start: ScreenPoint, end: ScreenPoint, button: str,
             duration_ms: int) -> None:
        down, up = _BUTTONS[button]
        _set_cursor(start)
        _send_mouse(down)
        try:
            self.move(end, duration_ms)
        finally:
            _send_mouse(up)

    def scroll(self, point: Optional[ScreenPoint], amount: int, horizontal: bool) -> None:
        if point is not None:
            _set_cursor(point)
        flags = MOUSEEVENTF_HWHEEL if horizontal else MOUSEEVENTF_WHEEL
        # 正 wheel 值表示滚轮向前，视图向上；契约的正数是向下 / 向右。
        delta = amount if horizontal else -amount
        _send_mouse(flags, (delta * 120) & 0xFFFFFFFF)


def _set_cursor(point: ScreenPoint) -> None:
    if not user32.SetCursorPos(int(point.x), int(point.y)):
        raise DesktopError(_last_error("SetCursorPos"))


def _send_mouse(flags: int, data: int = 0) -> None:
    item = INPUT(type=INPUT_MOUSE, union=INPUT_UNION(
        mi=MOUSEINPUT(0, 0, data, flags, 0, None)))
    if user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(INPUT)) != 1:
        raise DesktopError(_last_error("SendInput 鼠标事件"))


class Win32Keyboard:
    """SendInput 键盘事件：Unicode 文本走扫描码通道，功能键走虚拟键码。"""

    def type_text(self, text: str, interval_ms: int) -> None:
        for char in text:
            if char in ("\r", "\n"):
                self.press("enter", 1)
            elif char == "\t":
                self.press("tab", 1)
            else:
                _send_unicode(char)
            if interval_ms > 0:
                time.sleep(interval_ms / 1000.0)

    def press(self, key: str, repeat: int) -> None:
        vk = _virtual_key(key)
        for _ in range(repeat):
            _send_key(vk, 0)
            _send_key(vk, KEYEVENTF_KEYUP)

    def hotkey(self, keys: Sequence[str], repeat: int) -> None:
        virtual_keys = [_virtual_key(key) for key in keys]
        for _ in range(repeat):
            for vk in virtual_keys:
                _send_key(vk, 0)
            for vk in reversed(virtual_keys):
                _send_key(vk, KEYEVENTF_KEYUP)


def _virtual_key(key: str) -> int:
    try:
        return _VK_NAMED[key]
    except KeyError:
        raise DesktopError(f"键名 {key!r} 没有 Windows 虚拟键码") from None


def _send_key(vk: int, flags: int, scan: int = 0) -> None:
    item = INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(
        ki=KEYBDINPUT(vk, scan, flags, 0, None)))
    if user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(INPUT)) != 1:
        raise DesktopError(_last_error("SendInput 键盘事件"))


def _utf16_units(char: str) -> Tuple[int, ...]:
    code = ord(char)
    if code <= 0xFFFF:
        return (code,)
    code -= 0x10000
    return (0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF))


def _send_unicode(char: str) -> None:
    for unit in _utf16_units(char):
        _send_key(0, KEYEVENTF_UNICODE, unit)
        _send_key(0, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, unit)


class Win32Backend(Backend):
    """Windows 上的一套可用后端。"""

    def __init__(self) -> None:
        _enable_dpi_awareness()
        super().__init__(platform="win32", screen=Win32Screen(),
                         mouse=Win32Mouse(), keyboard=Win32Keyboard())
