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
from typing import Callable, Optional, Sequence, Tuple

from ..coords import ScreenGeometry, ScreenPoint, ScreenRect
from ..errors import DesktopError, DesktopUnavailable, ScreenCaptureFailed
from ..keys import DIGITS, LETTERS
from ..ports import Backend, Screenshot, WindowActivation, WindowInfo

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


def _window_rect(hwnd: int) -> Optional[ScreenRect]:
    raw = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(raw)):
        return None
    try:
        return ScreenRect(raw.left, raw.top, raw.right - raw.left, raw.bottom - raw.top)
    except ValueError:
        return None


def _window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def _window_class(hwnd: int) -> str:
    """窗口类名；拿不到返回空串（探测不因此失败）。"""
    buffer = ctypes.create_unicode_buffer(256)
    written = user32.GetClassNameW(hwnd, buffer, 256)
    return buffer.value if written > 0 else ""


def _is_foreground(hwnd: int) -> bool:
    """目标是否真的拿到了前台。

    只信 `GetForegroundWindow` 与实际图标态：`SetForegroundWindow` 的返回值
    和 `GetForegroundWindow` 都可能在窗口仍最小化时给出"成功"的假象。
    """
    return (int(user32.GetForegroundWindow() or 0) == int(hwnd)
            and not user32.IsIconic(hwnd))


def _bring_to_front(hwnd: int) -> Tuple[bool, bool]:
    """等价于用户点任务栏图标：最小化先恢复，再把窗口带到前台。

    返回 (是否恢复过, 是否真的到了前台)。`SwitchToThisWindow` 对最小化与纯遮挡
    都有效，且不像 `SetForegroundWindow` 那样返回不可信的 true；两个都发，
    后一个兜底。成败只按 `_is_foreground` 判，不看 API 返回值。
    """
    restored = False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
        restored = True
    user32.SwitchToThisWindow(hwnd, True)
    if not _is_foreground(hwnd):
        user32.SetForegroundWindow(hwnd)
    deadline = time.monotonic() + _ACTIVATE_TIMEOUT_SECONDS
    while (user32.IsIconic(hwnd) or not _is_foreground(hwnd)) \
            and time.monotonic() < deadline:
        time.sleep(_REPAINT_INTERVAL_SECONDS)
    return restored, _is_foreground(hwnd)


def _restore_without_activation(hwnd: int) -> None:
    """恢复最小化窗口但不抢前台：用户眼前的窗口不变，键盘焦点不跳。

    实测 `SW_SHOWNOACTIVATE` 会触发 CEF/Electron 的真实重绘
    （5.78MB 非空帧，与 `SW_RESTORE` 一致），所以"不打扰"与"取到内容"可以同时成立。
    """
    user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
    deadline = time.monotonic() + _ACTIVATE_TIMEOUT_SECONDS
    while user32.IsIconic(hwnd) and time.monotonic() < deadline:
        time.sleep(_REPAINT_INTERVAL_SECONDS)


def _is_uniform(data: bytes) -> bool:
    """整幅只有一个颜色（含全黑）：PrintWindow 没拿到内容的典型表现。

    抽样比较，不逐像素扫完 5MB 位图。
    """
    total = len(data) // 4
    if total <= 1:
        return True
    first = data[0:3]
    step = max(1, total // _UNIFORM_SAMPLE)
    for index in range(0, total, step):
        offset = index * 4
        if data[offset:offset + 3] != first:
            return False
    return True


def _crop_bgra(data: bytes, width: int, height: int,
               x: int, y: int, crop_width: int, crop_height: int) -> bytes:
    """从自上而下的 BGRA 位图里裁一块。"""
    if (x, y, crop_width, crop_height) == (0, 0, width, height):
        return data
    left = x * 4
    span = crop_width * 4
    rows = []
    for row in range(y, y + crop_height):
        start = row * width * 4 + left
        rows.append(data[start:start + span])
    return b"".join(rows)


def _print_window(hwnd: int, rect: ScreenRect) -> bytes:
    """PrintWindow(PW_RENDERFULLCONTENT)：取窗口自身重绘，遮挡不影响内容。"""
    window_dc = user32.GetWindowDC(hwnd)
    if not window_dc:
        raise ScreenCaptureFailed(_last_error("GetWindowDC"))
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, rect.width, rect.height)
    if not memory_dc or not bitmap:
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if memory_dc:
            gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(hwnd, window_dc)
        raise ScreenCaptureFailed(_last_error("创建窗口位图"))
    previous = gdi32.SelectObject(memory_dc, bitmap)
    try:
        if not user32.PrintWindow(hwnd, memory_dc, PW_RENDERFULLCONTENT):
            raise ScreenCaptureFailed(_last_error("PrintWindow"))
        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = rect.width
        info.bmiHeader.biHeight = -rect.height
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = 0
        buffer = ctypes.create_string_buffer(rect.width * rect.height * 4)
        if not gdi32.GetDIBits(memory_dc, bitmap, 0, rect.height, buffer,
                               ctypes.byref(info), DIB_RGB_COLORS):
            raise ScreenCaptureFailed(_last_error("GetDIBits"))
        return buffer.raw
    finally:
        gdi32.SelectObject(memory_dc, previous)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(hwnd, window_dc)


class Win32Windows:
    """按窗口取图。

    与 `Win32Screen.capture` 的区别：后者取屏幕合成结果，目标被别的窗口盖住时
    拿到的是遮挡物；这里取目标窗口自己的重绘，遮挡与前台与否都不影响。

    已知边界：窗口最小化时内容不可取。先 `SW_RESTORE`，再等一次真实重绘
    （实测约 440ms，上限 1.2s）；等不到就回退屏幕截图，并把 `source` 标成
    `screen`，让调用侧知道这张图不是窗口内容。
    """

    def get(self, hwnd: int) -> WindowInfo:
        if not user32.IsWindow(hwnd):
            raise DesktopError(f"窗口句柄 {hwnd} 已失效；重新列窗口再取")
        rect = _window_rect(hwnd)
        if rect is None:
            raise ScreenCaptureFailed(_last_error("GetWindowRect"))
        return WindowInfo(hwnd=int(hwnd), title=_window_title(hwnd), rect=rect,
                          minimized=bool(user32.IsIconic(hwnd)),
                          visible=bool(user32.IsWindowVisible(hwnd)),
                          foreground=_is_foreground(hwnd))

    def find(self, title_contains: str) -> Sequence[WindowInfo]:
        """标题包含 `title_contains` 的可见顶层窗口。

        同名窗口不止一个时（CEF/Electron 常见：主窗 + 播放窗 + 隐藏辅助窗），
        排序规则是「前台 → Z 序 → 面积」，不是单纯的面积：
        用户眼前那个窗口几乎总是他想操作的那个，而面积最大的可能是
        一个盖在画面上的播放层。`foreground` 一并写进结果，
        让调用侧能在回执里说清"选中的是不是前台那个"。
        """
        needle = (title_contains or "").strip().lower()
        if not needle:
            raise ValueError("window 需要非空的标题片段")
        foreground = int(user32.GetForegroundWindow() or 0)
        found = []
        # EnumWindows 按 Z 序自上而下枚举：序号越小越靠前。
        z_index = [0]

        def _collect(hwnd, _data):
            z_index[0] += 1
            if not user32.IsWindowVisible(hwnd):
                return True
            if int(user32.GetWindowLongW(hwnd, GWL_EXSTYLE)) & WS_EX_TOOLWINDOW:
                return True
            title = _window_title(hwnd)
            if not title or needle not in title.lower():
                return True
            rect = _window_rect(hwnd)
            if rect is None or rect.width < 2 or rect.height < 2:
                return True
            iconic = bool(user32.IsIconic(hwnd))
            # CEF/Electron 会留一批 (32767,32767) 的屏幕外辅助窗口；
            # 最小化的真窗口坐标同样是 -32000，不能用同一个判据一起排掉。
            if not iconic and (rect.x > 30000 or rect.y > 30000
                               or rect.right <= -30000 or rect.bottom <= -30000):
                return True
            found.append((
                0 if int(hwnd) == foreground else 1,
                z_index[0],
                -rect.width * rect.height,
                WindowInfo(hwnd=int(hwnd), title=title, rect=rect,
                           minimized=iconic, visible=True,
                           foreground=int(hwnd) == foreground),
            ))
            return True

        user32.EnumWindows(_WNDENUMPROC(_collect), 0)
        found.sort(key=lambda item: item[:3])
        return tuple(item[3] for item in found)

    def list_visible(self) -> Sequence[WindowInfo]:
        """当前所有可见顶层窗口。

        只用于动作前后的窗口层对比：点击卡片后是否弹出了播放页、
        是否关掉了弹层。列表本身不进上下文，回执只留"新出现/消失了谁"。
        过滤规则与 `find` 一致：跳过工具窗与 CEF 的屏幕外辅助窗。
        """
        foreground = int(user32.GetForegroundWindow() or 0)
        windows = []

        def _collect(hwnd, _data):
            if not user32.IsWindowVisible(hwnd):
                return True
            if int(user32.GetWindowLongW(hwnd, GWL_EXSTYLE)) & WS_EX_TOOLWINDOW:
                return True
            rect = _window_rect(hwnd)
            if rect is None or rect.width < 2 or rect.height < 2:
                return True
            iconic = bool(user32.IsIconic(hwnd))
            if not iconic and (rect.x > 30000 or rect.y > 30000
                               or rect.right <= -30000 or rect.bottom <= -30000):
                return True
            windows.append(WindowInfo(
                hwnd=int(hwnd), title=_window_title(hwnd), rect=rect,
                minimized=iconic, visible=True,
                foreground=int(hwnd) == foreground))
            return True

        user32.EnumWindows(_WNDENUMPROC(_collect), 0)
        return tuple(windows)

    def activate(self, hwnd: int) -> WindowActivation:
        if not user32.IsWindow(hwnd):
            raise DesktopError(f"窗口句柄 {hwnd} 已失效；重新列窗口再取")
        restored, active = _bring_to_front(hwnd)
        foreground = "" if active else _window_title(user32.GetForegroundWindow())
        return WindowActivation(window=self.get(hwnd), active=active,
                                restored=restored, foreground=foreground)

    def capture(self, hwnd: int, region: Optional[ScreenRect],
                *, activate: bool = False,
                prepare: Optional[Callable[[], None]] = None) -> Screenshot:
        if not user32.IsWindow(hwnd):
            raise DesktopError(f"窗口句柄 {hwnd} 已失效；重新列窗口再取")
        rect = _window_rect(hwnd)
        if rect is None:
            raise ScreenCaptureFailed(_last_error("GetWindowRect"))

        # 最小化必须恢复，否则取到的是 (-32000, -32000) 的空帧；
        # 但"恢复"不等于"抢前台"：默认只恢复（SW_SHOWNOACTIVATE），
        # 用户正在用的窗口与键盘焦点都不动。需要亮出来时由调用侧显式要 activate。
        restored = bool(user32.IsIconic(hwnd))
        activation = "none"
        if activate:
            was_restored, ok = _bring_to_front(hwnd)
            restored = restored or was_restored
            activation = "ok" if ok else "failed"
        elif restored:
            _restore_without_activation(hwnd)
            activation = "none"
        if restored:
            rect = _window_rect(hwnd) or rect
        if prepare is not None:
            # 悬停必须发生在窗口已恢复/置前之后：否则光标落在原前台窗口上，
            # 展开的是别人的控件，拍到的却是目标窗口。
            prepare()
            rect = _window_rect(hwnd) or rect
        foreground = _is_foreground(hwnd)

        data = _print_window(hwnd, rect)
        if restored or _is_uniform(data):
            # 恢复后需要一次真实重绘；只有非空内容才算拿到了窗口画面。
            deadline = time.monotonic() + _REPAINT_TIMEOUT_SECONDS
            while _is_uniform(data) and time.monotonic() < deadline:
                time.sleep(_REPAINT_INTERVAL_SECONDS)
                data = _print_window(hwnd, rect)

        source = "window"
        if _is_uniform(data):
            if not user32.IsWindowVisible(hwnd):
                raise ScreenCaptureFailed(
                    "窗口不可见且取不到内容；先恢复窗口（ShowWindow）再截图"
                )
            # 回退到屏幕截图：可能含遮挡物，用 source 如实告知。
            data = _grab(rect)
            source = "screen"

        if region is not None:
            clipped = region.intersect(rect)
            if clipped is None:
                raise ValueError(
                    f"区域与窗口 {hwnd} 没有交集；窗口是 {rect.to_dict()}"
                )
            data = _crop_bgra(data, rect.width, rect.height,
                              clipped.x - rect.x, clipped.y - rect.y,
                              clipped.width, clipped.height)
            rect = clipped

        return Screenshot(png=_encode_bgra(data, rect.width, rect.height),
                          rect=rect, source=source, restored=restored,
                          foreground=foreground, activation=activation)


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


class Win32Hit:
    """落点探测：`WindowFromPoint` + 类名 + 所属顶层窗口标题。

    返回的是"谁在这一点"而不是"这一点的语义"：模型据此判断自己点的是
    卡片、按钮还是画面背景，不必靠下一次截图猜。
    """

    def probe(self, point: ScreenPoint) -> dict:
        hwnd = int(user32.WindowFromPoint(POINT(int(point.x), int(point.y))) or 0)
        if not hwnd:
            return {}
        root = int(user32.GetAncestor(hwnd, GA_ROOT) or hwnd)
        probe = {
            "hwnd": hwnd,
            "class": _window_class(hwnd),
        }
        if root != hwnd:
            probe["root"] = root
        title = _window_title(root)
        if title:
            probe["title"] = title
        return probe


class Win32Backend(Backend):
    """Windows 上的一套可用后端。"""

    def __init__(self) -> None:
        _enable_dpi_awareness()
        super().__init__(platform="win32", screen=Win32Screen(),
                         mouse=Win32Mouse(), keyboard=Win32Keyboard(),
                         windows=Win32Windows(), hit=Win32Hit())
