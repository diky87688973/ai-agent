"""Windows desktop backdrop. Captured pixels stay in the native window."""
from __future__ import annotations

import ctypes
import io
import os
import threading
import time
from ctypes import wintypes
from urllib.parse import urlsplit

from agent.core.error_report import report_error

_EXPAND = 50
_EXCLUDE_FROM_CAPTURE = 0x11


def _client_origin(hwnd):
    point = wintypes.POINT()
    if not ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(point)):
        raise ctypes.WinError()
    return point.x, point.y


def _capture_box(hwnd):
    user32 = ctypes.windll.user32
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError()
    x, y = _client_origin(hwnd)
    left, top, width, height = (user32.GetSystemMetrics(i) for i in range(76, 80))
    return (max(left, x - _EXPAND), max(top, y - _EXPAND),
            min(left + width, x + rect.right + _EXPAND),
            min(top + height, y + rect.bottom + _EXPAND))


def _capture(box):
    from PIL import Image, ImageFilter, ImageGrab

    with ImageGrab.grab(bbox=box, all_screens=True) as image:
        width, height = image.size
        scale = min(1, 300 / max(width, height))
        small = image.resize((max(1, round(width * scale)), max(1, round(height * scale))),
                             Image.Resampling.BOX)
        blurred = small.filter(ImageFilter.GaussianBlur(2.8))
        with io.BytesIO() as buffer:
            blurred.resize(image.size, Image.Resampling.BICUBIC).filter(
                ImageFilter.GaussianBlur(2)).save(buffer, "JPEG", quality=84)
            return buffer.getvalue()


class DesktopBackdrop:
    """Own one capture worker and one UI-thread renderer per window."""

    def __init__(self, url):
        self._origin = urlsplit(url).netloc
        self._active = None

    def set_enabled(self, window, enabled):
        if os.name != "nt" or type(enabled) is not bool:
            return False
        try:
            from System import Action

            url = urlsplit(window.get_current_url() or "")
            if url.scheme != "http" or url.netloc != self._origin:
                return False
            native = window.native

            def update():
                if enabled and (self._active is None or self._active.closed):
                    candidate = _Backdrop(native)
                    try:
                        candidate.start()
                    except Exception:
                        candidate.close()
                        raise
                    self._active = candidate
                elif not enabled and self._active is not None:
                    self._active.close()
                    self._active = None

            native.Invoke(Action(update))
            return self._active is not None and not self._active.closed
        except Exception as exc:
            report_error("agent.gui.desktop_backdrop.toggle", exc)
            return False


class _Backdrop:
    def __init__(self, native):
        from System.Drawing import Color
        from System.Windows.Forms import PictureBox, Timer

        self.native = native
        self.hwnd = wintypes.HWND(int(native.Handle.ToInt64()))
        self.webview = next(child for child in native.Controls
                            if str(child.GetType().FullName).endswith(".WebView2"))
        self.original_color = self.webview.DefaultBackgroundColor
        self.transparent = Color.Transparent
        self.picture = PictureBox()
        self.picture.BackColor = native.BackColor
        self.picture.Visible = False
        self.timer = Timer()
        self.timer.Interval = 8
        self.stop = threading.Event()
        self.latest = None
        self.displayed = None
        self.position = None
        self.original_affinity = wintypes.DWORD()
        self.affinity_set = False
        self.closed = False
        self.subscribed = False

    def start(self):
        user32 = ctypes.windll.user32
        if not user32.GetWindowDisplayAffinity(self.hwnd, ctypes.byref(self.original_affinity)):
            raise ctypes.WinError()
        if not user32.SetWindowDisplayAffinity(self.hwnd, _EXCLUDE_FROM_CAPTURE):
            raise ctypes.WinError()
        self.affinity_set = True
        self.native.Controls.Add(self.picture)
        self.picture.SendToBack()
        self.webview.DefaultBackgroundColor = self.transparent
        self.native.FormClosing += self._on_closed
        self.webview.NavigationStarting += self._on_closed
        self.timer.Tick += self._paint
        self.subscribed = True
        self.timer.Start()
        threading.Thread(target=self._sample, name="desktop-backdrop", daemon=True).start()

    def _sample(self):
        user32 = ctypes.windll.user32
        try:
            deadline = time.monotonic()
            while not self.stop.is_set():
                deadline = max(deadline + 1 / 16, time.monotonic())
                if self.stop.wait(deadline - time.monotonic()):
                    break
                if user32.IsIconic(self.hwnd):
                    continue
                if self.latest is not None and user32.GetForegroundWindow() != self.hwnd.value:
                    continue
                box = _capture_box(self.hwnd)
                if box[0] < box[2] and box[1] < box[3]:
                    frame = (box, _capture(box))
                    if not self.stop.is_set():
                        self.latest = frame
        except Exception as exc:
            report_error("agent.gui.desktop_backdrop.capture", exc)
            self.stop.set()

    def _paint(self, _sender, _event):
        try:
            if self.stop.is_set():
                self._stop_after_failure()
            elif self.latest is not None:
                self._draw(self.latest)
        except Exception as exc:
            report_error("agent.gui.desktop_backdrop.paint", exc)
            self._stop_after_failure()

    def _stop_after_failure(self):
        self.close()
        self.webview.CoreWebView2.ExecuteScriptAsync(
            'window.dispatchEvent(new Event("desktop-backdrop-unavailable"))'
        )

    def _draw(self, frame):
        from System.Drawing import Bitmap, Image, Rectangle
        from System.IO import MemoryStream

        position = _client_origin(self.hwnd)
        if frame is self.displayed and position == self.position:
            return
        box, jpeg = frame
        left, top, right, bottom = box
        x, y = position
        self.picture.Bounds = Rectangle(left - x, top - y, right - left, bottom - top)
        if frame is not self.displayed:
            stream = MemoryStream(jpeg)
            try:
                image = Image.FromStream(stream)
                try:
                    bitmap = Bitmap(image)
                finally:
                    image.Dispose()
            finally:
                stream.Dispose()
            previous = self.picture.Image
            self.picture.Image = bitmap
            if previous is not None:
                previous.Dispose()
        self.picture.Visible = True
        self.picture.Refresh()
        self.displayed = frame
        self.position = position

    def _on_closed(self, _sender, _event):
        self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.stop.set()
        self.latest = None
        self.displayed = None
        self.timer.Stop()
        self.timer.Dispose()
        if self.subscribed:
            self.native.FormClosing -= self._on_closed
            self.webview.NavigationStarting -= self._on_closed
        if self.affinity_set and not ctypes.windll.user32.SetWindowDisplayAffinity(
                self.hwnd, self.original_affinity.value):
            report_error("agent.gui.desktop_backdrop.restore_affinity", ctypes.WinError())
        self.webview.DefaultBackgroundColor = self.original_color
        image = self.picture.Image
        self.picture.Dispose()
        if image is not None:
            image.Dispose()
