# -*- coding: utf-8 -*-
"""Windows 后端：GDI 截屏 + SendInput 输入。"""
from __future__ import annotations

import io
import time
from ctypes import wintypes
from typing import Callable, Optional, Sequence, Tuple

from ..coords import ScreenGeometry, ScreenPoint, ScreenRect
from ..errors import DesktopError, DesktopUnavailable, ScreenCaptureFailed
from ..ports import Backend, Screenshot, WindowActivation, WindowInfo
from .win32_common import (
    _ACTIVATE_TIMEOUT_SECONDS,
    _BUTTONS,
    _REPAINT_INTERVAL_SECONDS,
    _REPAINT_TIMEOUT_SECONDS,
    _UNIFORM_SAMPLE,
    _VK_NAMED,
    _WNDENUMPROC,
    BITMAPINFO,
    BITMAPINFOHEADER,
    CAPTUREBLT,
    DIB_RGB_COLORS,
    GA_ROOT,
    GWL_EXSTYLE,
    INPUT,
    INPUT_KEYBOARD,
    INPUT_MOUSE,
    INPUT_UNION,
    KEYBDINPUT,
    KEYEVENTF_KEYUP,
    KEYEVENTF_UNICODE,
    MOUSEEVENTF_HWHEEL,
    MOUSEEVENTF_WHEEL,
    MOUSEINPUT,
    POINT,
    PW_RENDERFULLCONTENT,
    SM_CXSCREEN,
    SM_CXVIRTUALSCREEN,
    SM_CYSCREEN,
    SM_CYVIRTUALSCREEN,
    SM_XVIRTUALSCREEN,
    SM_YVIRTUALSCREEN,
    SRCCOPY,
    SW_RESTORE,
    SW_SHOWNOACTIVATE,
    WS_EX_TOOLWINDOW,
    _enable_dpi_awareness,
    _last_error,
    _monitor_dpis,
    _monitor_rects,
    _system_metric,
    ctypes,
    gdi32,
    user32,
)


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