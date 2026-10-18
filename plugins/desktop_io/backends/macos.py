# -*- coding: utf-8 -*-
"""macOS 后端：screencapture 截屏 + CoreGraphics 输入。

坐标是全局显示坐标（点），与 CGEvent 使用的坐标系一致。Retina 屏上
截图是点的两倍像素，`pixel_ratio` 把这件事报给模型；鼠标与键盘仍按点投递。
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import tempfile
import time
from typing import Optional, Sequence, Tuple

from ..coords import ScreenGeometry, ScreenPoint, ScreenRect
from ..errors import DesktopError, DesktopPermissionDenied, ScreenCaptureFailed
from ..ports import Backend, Screenshot

_APPLICATION_SERVICES = (
    "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
)
_CORE_FOUNDATION = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"

_services = ctypes.CDLL(_APPLICATION_SERVICES)
_core = ctypes.CDLL(_CORE_FOUNDATION)

screencapture = "/usr/sbin/screencapture"

TAP_HID = 0

EVENT_LEFT_DOWN = 1
EVENT_LEFT_UP = 2
EVENT_RIGHT_DOWN = 3
EVENT_RIGHT_UP = 4
EVENT_MOUSE_MOVED = 5
EVENT_LEFT_DRAGGED = 6
EVENT_RIGHT_DRAGGED = 7
EVENT_OTHER_DOWN = 25
EVENT_OTHER_UP = 26
EVENT_OTHER_DRAGGED = 27

#: 鼠标事件的点击计数（连击次数），字段号来自 kCGMouseEventClickState。
FIELD_CLICK_STATE = 1

BUTTON_LEFT = 0
BUTTON_RIGHT = 1
BUTTON_CENTER = 2

SCROLL_UNIT_LINE = 1

FLAG_SHIFT = 1 << 17
FLAG_CONTROL = 1 << 18
FLAG_ALTERNATE = 1 << 19
FLAG_COMMAND = 1 << 20

_MOUSE_EVENTS = {
    "left": (EVENT_LEFT_DOWN, EVENT_LEFT_UP, EVENT_LEFT_DRAGGED, BUTTON_LEFT),
    "right": (EVENT_RIGHT_DOWN, EVENT_RIGHT_UP, EVENT_RIGHT_DRAGGED, BUTTON_RIGHT),
    "middle": (EVENT_OTHER_DOWN, EVENT_OTHER_UP, EVENT_OTHER_DRAGGED, BUTTON_CENTER),
}

_MODIFIER_FLAGS = {
    "shift": FLAG_SHIFT,
    "ctrl": FLAG_CONTROL,
    "alt": FLAG_ALTERNATE,
    "cmd": FLAG_COMMAND,
    "win": FLAG_COMMAND,
}

#: ANSI 键码表；字母与数字是物理键位，不是 ASCII。
_KEYCODES = {
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04, "g": 0x05,
    "z": 0x06, "x": 0x07, "c": 0x08, "v": 0x09, "b": 0x0B, "q": 0x0C,
    "w": 0x0D, "e": 0x0E, "r": 0x0F, "y": 0x10, "t": 0x11, "1": 0x12,
    "2": 0x13, "3": 0x14, "4": 0x15, "6": 0x16, "5": 0x17, "=": 0x18,
    "9": 0x19, "7": 0x1A, "-": 0x1B, "8": 0x1C, "0": 0x1D, "]": 0x1E,
    "o": 0x1F, "u": 0x20, "[": 0x21, "i": 0x22, "p": 0x23, "l": 0x25,
    "j": 0x26, "'": 0x27, "k": 0x28, ";": 0x29, "\\": 0x2A, ",": 0x2B,
    "/": 0x2C, "n": 0x2D, "m": 0x2E, ".": 0x2F, "`": 0x32,
    "enter": 0x24, "tab": 0x30, "space": 0x31, "backspace": 0x33,
    "esc": 0x35, "cmd": 0x37, "shift": 0x38, "capslock": 0x39,
    "alt": 0x3A, "ctrl": 0x3B, "win": 0x37,
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76, "f5": 0x60,
    "f6": 0x61, "f7": 0x62, "f8": 0x64, "f9": 0x65, "f10": 0x6D,
    "f11": 0x67, "f12": 0x6F, "f13": 0x69, "f14": 0x6B, "f15": 0x71,
    "f16": 0x6A, "f17": 0x40, "f18": 0x4F, "f19": 0x50, "f20": 0x5A,
    "insert": 0x72, "home": 0x73, "pageup": 0x74, "delete": 0x75,
    "end": 0x77, "pagedown": 0x79,
    "left": 0x7B, "right": 0x7C, "down": 0x7D, "up": 0x7E,
}


class CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class CGSize(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


class CGRect(ctypes.Structure):
    _fields_ = [("origin", CGPoint), ("size", CGSize)]


_services.CGEventCreateMouseEvent.restype = ctypes.c_void_p
_services.CGEventCreateMouseEvent.argtypes = (
    ctypes.c_void_p, ctypes.c_uint32, CGPoint, ctypes.c_uint32)
_services.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
_services.CGEventCreateKeyboardEvent.argtypes = (
    ctypes.c_void_p, ctypes.c_uint16, ctypes.c_bool)
_services.CGEventCreateScrollWheelEvent.restype = ctypes.c_void_p
_services.CGEventCreateScrollWheelEvent.argtypes = (
    ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_int32,
    ctypes.c_int32)
_services.CGEventCreate.restype = ctypes.c_void_p
_services.CGEventCreate.argtypes = (ctypes.c_void_p,)
_services.CGEventGetLocation.restype = CGPoint
_services.CGEventGetLocation.argtypes = (ctypes.c_void_p,)
_services.CGEventPost.argtypes = (ctypes.c_uint32, ctypes.c_void_p)
_services.CGEventSetFlags.argtypes = (ctypes.c_void_p, ctypes.c_uint64)
_services.CGEventSetIntegerValueField.argtypes = (
    ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int64)
_services.CGEventKeyboardSetUnicodeString.restype = None
_services.CGEventKeyboardSetUnicodeString.argtypes = (
    ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_uint16))
_services.CGWarpMouseCursorPosition.restype = ctypes.c_int32
_services.CGWarpMouseCursorPosition.argtypes = (CGPoint,)
_services.CGGetActiveDisplayList.restype = ctypes.c_int32
_services.CGGetActiveDisplayList.argtypes = (
    ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32))
_services.CGDisplayBounds.restype = CGRect
_services.CGDisplayBounds.argtypes = (ctypes.c_uint32,)
_services.CGDisplayPixelsWide.restype = ctypes.c_size_t
_services.CGDisplayPixelsWide.argtypes = (ctypes.c_uint32,)
_services.CGDisplayPixelsHigh.restype = ctypes.c_size_t
_services.CGDisplayPixelsHigh.argtypes = (ctypes.c_uint32,)
_core.CFRelease.argtypes = (ctypes.c_void_p,)


def _require_trusted() -> None:
    """输入事件需要辅助功能权限；没有权限时 SendInput 会静默丢弃。"""
    try:
        trusted = bool(_services.AXIsProcessTrusted())
    except AttributeError:
        return
    if not trusted:
        raise DesktopPermissionDenied(
            "缺少辅助功能权限：系统设置 → 隐私与安全性 → 辅助功能，勾选运行本程序的终端"
        )


def _require_screen_access() -> None:
    """10.15 起截屏需要屏幕录制权限；旧系统没有这个检查接口。"""
    try:
        allowed = bool(_services.CGPreflightScreenCaptureAccess())
    except AttributeError:
        return
    if not allowed:
        raise DesktopPermissionDenied(
            "缺少屏幕录制权限：系统设置 → 隐私与安全性 → 屏幕录制，勾选运行本程序的终端"
        )


def _displays() -> Tuple[Tuple[ScreenRect, float], ...]:
    count = ctypes.c_uint32()
    raw = (ctypes.c_uint32 * 16)()
    if _services.CGGetActiveDisplayList(16, raw, ctypes.byref(count)) != 0:
        return ()
    found = []
    for display in raw[:count.value]:
        bounds = _services.CGDisplayBounds(display)
        width = int(round(bounds.size.width))
        height = int(round(bounds.size.height))
        if width <= 0 or height <= 0:
            continue
        pixels = _services.CGDisplayPixelsWide(display)
        ratio = (pixels / width) if width else 1.0
        found.append((ScreenRect(int(round(bounds.origin.x)),
                                 int(round(bounds.origin.y)), width, height),
                      round(ratio, 3)))
    return tuple(found)


class MacScreen:
    """屏幕几何与 `screencapture` 截屏。"""

    def geometry(self) -> ScreenGeometry:
        displays = _displays()
        if not displays:
            raise DesktopError("没有读到活动显示器")
        left = min(rect.x for rect, _ratio in displays)
        top = min(rect.y for rect, _ratio in displays)
        right = max(rect.right for rect, _ratio in displays)
        bottom = max(rect.bottom for rect, _ratio in displays)
        ratios = {ratio for _rect, ratio in displays}
        primary_ratio = displays[0][1]
        return ScreenGeometry(
            rect=ScreenRect(left, top, right - left, bottom - top),
            pixel_ratio=primary_ratio,
            dpi=f"{primary_ratio:g}x",
            mixed_scale=len(ratios) > 1,
        )

    def capture(self, region: Optional[ScreenRect]) -> Screenshot:
        _require_screen_access()
        rect = region or self.geometry().rect
        handle, path = tempfile.mkstemp(prefix="desktop_io_", suffix=".png")
        os.close(handle)
        try:
            command = [
                screencapture, "-x", "-t", "png",
                "-R", f"{rect.x},{rect.y},{rect.width},{rect.height}", path,
            ]
            completed = subprocess.run(command, capture_output=True, timeout=30)
            if completed.returncode != 0:
                detail = completed.stderr.decode("utf-8", "replace").strip()
                raise ScreenCaptureFailed(f"screencapture 失败：{detail or completed.returncode}")
            with open(path, "rb") as stream:
                png = stream.read()
        except ScreenCaptureFailed:
            raise
        except (OSError, subprocess.SubprocessError) as exc:
            raise ScreenCaptureFailed(f"screencapture 调用失败：{exc}") from exc
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        if not png:
            raise ScreenCaptureFailed("screencapture 没有产出图片")
        return Screenshot(png=png, rect=rect)


class MacMouse:
    """CoreGraphics 鼠标事件。"""

    def cursor(self) -> ScreenPoint:
        event = _services.CGEventCreate(None)
        if not event:
            raise DesktopError("CGEventCreate 失败")
        try:
            location = _services.CGEventGetLocation(event)
        finally:
            _core.CFRelease(event)
        return ScreenPoint(int(round(location.x)), int(round(location.y)))

    def move(self, point: ScreenPoint, duration_ms: int) -> None:
        _require_trusted()
        if duration_ms <= 0:
            _warp(point)
            _post_mouse(EVENT_MOUSE_MOVED, point, BUTTON_LEFT)
            return
        start = self.cursor()
        steps = max(1, min(120, duration_ms // 10))
        for index in range(1, steps + 1):
            ratio = index / steps
            position = ScreenPoint(
                int(round(start.x + (point.x - start.x) * ratio)),
                int(round(start.y + (point.y - start.y) * ratio)),
            )
            _warp(position)
            _post_mouse(EVENT_MOUSE_MOVED, position, BUTTON_LEFT)
            time.sleep(duration_ms / 1000.0 / steps)

    def click(self, point: Optional[ScreenPoint], button: str, count: int) -> None:
        _require_trusted()
        target = point or self.cursor()
        down, up, _dragged, cg_button = _MOUSE_EVENTS[button]
        for index in range(count):
            _warp(target)
            _post_mouse(down, target, cg_button, index + 1)
            _post_mouse(up, target, cg_button, index + 1)
            if index + 1 < count:
                time.sleep(0.02)

    def drag(self, start: ScreenPoint, end: ScreenPoint, button: str,
             duration_ms: int) -> None:
        _require_trusted()
        down, up, dragged, cg_button = _MOUSE_EVENTS[button]
        _warp(start)
        _post_mouse(down, start, cg_button)
        try:
            steps = max(1, min(120, max(duration_ms, 60) // 10))
            for index in range(1, steps + 1):
                ratio = index / steps
                position = ScreenPoint(
                    int(round(start.x + (end.x - start.x) * ratio)),
                    int(round(start.y + (end.y - start.y) * ratio)),
                )
                _warp(position)
                _post_mouse(dragged, position, cg_button)
                time.sleep(max(duration_ms, 60) / 1000.0 / steps)
        finally:
            _post_mouse(up, end, cg_button)

    def scroll(self, point: Optional[ScreenPoint], amount: int, horizontal: bool) -> None:
        _require_trusted()
        if point is not None:
            _warp(point)
        # 正 wheel1 表示视图向上；契约的正数是向下。
        event = _services.CGEventCreateScrollWheelEvent(
            None, SCROLL_UNIT_LINE, 2,
            0 if horizontal else -amount,
            amount if horizontal else 0,
        )
        if not event:
            raise DesktopError("CGEventCreateScrollWheelEvent 失败")
        try:
            _services.CGEventPost(TAP_HID, event)
        finally:
            _core.CFRelease(event)


class MacKeyboard:
    """CoreGraphics 键盘事件；文本走 Unicode 注入。"""

    def type_text(self, text: str, interval_ms: int) -> None:
        _require_trusted()
        for char in text:
            if char in ("\r", "\n"):
                self.press("enter", 1)
            elif char == "\t":
                self.press("tab", 1)
            else:
                _post_unicode(char)
            if interval_ms > 0:
                time.sleep(interval_ms / 1000.0)

    def press(self, key: str, repeat: int) -> None:
        _require_trusted()
        code = _keycode(key)
        for _ in range(repeat):
            _post_key(code, True)
            _post_key(code, False)

    def hotkey(self, keys: Sequence[str], repeat: int) -> None:
        _require_trusted()
        codes = [_keycode(key) for key in keys]
        flags = 0
        for key in keys:
            flags |= _MODIFIER_FLAGS.get(key, 0)
        for _ in range(repeat):
            for code in codes:
                _post_key(code, True, flags)
            for code in reversed(codes):
                _post_key(code, False, flags)


def _keycode(key: str) -> int:
    try:
        return _KEYCODES[key]
    except KeyError:
        raise DesktopError(f"键名 {key!r} 没有 macOS 键码") from None


def _point(point: ScreenPoint) -> CGPoint:
    return CGPoint(float(point.x), float(point.y))


def _warp(point: ScreenPoint) -> None:
    _services.CGWarpMouseCursorPosition(_point(point))


def _post_mouse(kind: int, point: ScreenPoint, button: int,
                click_state: int = 0) -> None:
    event = _services.CGEventCreateMouseEvent(None, kind, _point(point), button)
    if not event:
        raise DesktopError("CGEventCreateMouseEvent 失败")
    try:
        if click_state:
            _services.CGEventSetIntegerValueField(event, FIELD_CLICK_STATE, click_state)
        _services.CGEventPost(TAP_HID, event)
    finally:
        _core.CFRelease(event)


def _post_key(code: int, down: bool, flags: int = 0) -> None:
    event = _services.CGEventCreateKeyboardEvent(None, code, down)
    if not event:
        raise DesktopError("CGEventCreateKeyboardEvent 失败")
    try:
        if flags:
            _services.CGEventSetFlags(event, flags)
        _services.CGEventPost(TAP_HID, event)
    finally:
        _core.CFRelease(event)


def _post_unicode(char: str) -> None:
    encoded = char.encode("utf-16-le")
    units = len(encoded) // 2
    buffer = ctypes.create_string_buffer(encoded, len(encoded))
    pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_uint16))
    for down in (True, False):
        event = _services.CGEventCreateKeyboardEvent(None, 0, down)
        if not event:
            raise DesktopError("CGEventCreateKeyboardEvent 失败")
        try:
            _services.CGEventKeyboardSetUnicodeString(event, units, pointer)
            _services.CGEventPost(TAP_HID, event)
        finally:
            _core.CFRelease(event)


class MacOSBackend(Backend):
    """macOS 上的一套可用后端。"""

    def __init__(self) -> None:
        super().__init__(platform="darwin", screen=MacScreen(),
                         mouse=MacMouse(), keyboard=MacKeyboard())
