# -*- coding: utf-8 -*-
"""窗口操作模块：句柄取值、居中几何、最大化边界的纯逻辑。

只测不依赖真实窗口与 Win32 调用的部分；`activate_window` / `apply_dark_titlebar`
的真实调用需要句柄，那部分归 `test_gui_launcher` 打桩覆盖。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.gui import window_ops  # noqa: E402


class PointerIntTest(unittest.TestCase):
    """句柄值归一：pywebview 给的是 ctypes 指针，也可能是 None。"""

    def test_none_is_zero(self) -> None:
        self.assertEqual(window_ops._pointer_int(None), 0)

    def test_plain_int_passthrough(self) -> None:
        self.assertEqual(window_ops._pointer_int(123), 123)

    def test_ctypes_pointer_uses_to_int64(self) -> None:
        """ctypes 指针的 int() 会抛，必须走 ToInt64()。"""

        class _Ptr:
            def ToInt64(self) -> int:
                return 456

            def __int__(self) -> int:
                raise TypeError("pointer 不能直接 int()")

        self.assertEqual(window_ops._pointer_int(_Ptr()), 456)


class WindowHandleTest(unittest.TestCase):
    """从窗口对象取原生句柄；任一层缺失都返回 0 而不是抛。"""

    def test_handle_present(self) -> None:
        window = mock.MagicMock()
        window.native.Handle = 789
        self.assertEqual(window_ops.window_handle(window), 789)

    def test_missing_native(self) -> None:
        self.assertEqual(window_ops.window_handle(object()), 0)

    def test_missing_handle(self) -> None:
        window = mock.MagicMock()
        window.native.Handle = None
        self.assertEqual(window_ops.window_handle(window), 0)


class TaskbarMinimizeTest(unittest.TestCase):
    def _apply(self, user32):
        with mock.patch.object(window_ops.os, "name", "nt"), \
                mock.patch.object(window_ops, "window_handle", return_value=123), \
                mock.patch.object(window_ops.ctypes, "WinDLL", return_value=user32, create=True), \
                mock.patch.object(window_ops.ctypes, "set_last_error", create=True), \
                mock.patch.object(window_ops.ctypes, "get_last_error", return_value=0, create=True):
            return window_ops.enable_taskbar_minimize(object())

    def test_adds_native_capabilities_preserves_other_flags_and_refreshes_without_activation(self):
        user32 = mock.MagicMock()
        user32.GetWindowLongW.return_value = 0x16010000
        user32.SetWindowLongW.return_value = 0x16010000
        self.assertTrue(self._apply(user32))
        user32.SetWindowLongW.assert_called_once_with(123, -16, 0x160B0000)
        user32.SetWindowPos.assert_called_once_with(123, None, 0, 0, 0, 0, 0x0037)
        self.assertFalse(user32.SetWindowLongW.call_args.args[2] & 0x00C40000)

    def test_existing_capabilities_are_preserved_and_cache_still_refreshed(self):
        user32 = mock.MagicMock()
        user32.GetWindowLongW.return_value = 0x160B0000
        self.assertTrue(self._apply(user32))
        user32.SetWindowLongW.assert_not_called()
        user32.SetWindowPos.assert_called_once()

    def test_zero_previous_style_is_valid_when_last_error_is_zero(self):
        user32 = mock.MagicMock()
        user32.GetWindowLongW.return_value = 0
        user32.SetWindowLongW.return_value = 0
        self.assertTrue(self._apply(user32))
        user32.SetWindowLongW.assert_called_once_with(123, -16, 0x000A0000)

    def test_missing_handle_and_non_windows_do_not_call_win32(self):
        with mock.patch.object(window_ops.ctypes, "WinDLL", create=True) as load:
            with mock.patch.object(window_ops.os, "name", "posix"):
                self.assertFalse(window_ops.enable_taskbar_minimize(object()))
            with mock.patch.object(window_ops.os, "name", "nt"):
                self.assertFalse(window_ops.enable_taskbar_minimize(object()))
            load.assert_not_called()

    def test_native_failures_report_error_instead_of_claiming_success(self):
        for stage in ("GetWindowLongW", "SetWindowLongW", "SetWindowPos"):
            with self.subTest(stage=stage):
                user32 = mock.MagicMock()
                user32.GetWindowLongW.return_value = 0x16010000
                user32.SetWindowLongW.return_value = 0x16010000
                getattr(user32, stage).return_value = 0
                with mock.patch.object(window_ops.os, "name", "nt"), \
                        mock.patch.object(window_ops, "window_handle", return_value=123), \
                        mock.patch.object(window_ops.ctypes, "WinDLL", return_value=user32, create=True), \
                        mock.patch.object(window_ops.ctypes, "set_last_error", create=True), \
                        mock.patch.object(window_ops.ctypes, "get_last_error", return_value=5, create=True), \
                        mock.patch.object(window_ops, "report_error") as report:
                    self.assertFalse(window_ops.enable_taskbar_minimize(object()))
                report.assert_called_once()

    @unittest.skipUnless(sys.platform == "win32", "Windows native window style")
    def test_real_hidden_window_preserves_borderless_geometry(self):
        import ctypes
        from ctypes import wintypes
        from types import SimpleNamespace

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                         wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                         ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                         wintypes.HINSTANCE, wintypes.LPVOID]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongW.restype = ctypes.c_long
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        hwnd = user32.CreateWindowExW(0x80, "STATIC", "taskbar-style-regression",
                                     0x00010000, 0, 0, 320, 240, None, None, None, None)
        self.assertTrue(hwnd)
        try:
            style = user32.GetWindowLongW(hwnd, -16)
            before, client_before = wintypes.RECT(), wintypes.RECT()
            self.assertTrue(user32.GetWindowRect(hwnd, ctypes.byref(before)))
            self.assertTrue(user32.GetClientRect(hwnd, ctypes.byref(client_before)))
            window = SimpleNamespace(native=SimpleNamespace(Handle=hwnd))
            self.assertTrue(window_ops.enable_taskbar_minimize(window))
            self.assertTrue(window_ops.enable_taskbar_minimize(window))
            self.assertEqual(user32.GetWindowLongW(hwnd, -16), style | 0x000A0000)
            after, client_after = wintypes.RECT(), wintypes.RECT()
            self.assertTrue(user32.GetWindowRect(hwnd, ctypes.byref(after)))
            self.assertTrue(user32.GetClientRect(hwnd, ctypes.byref(client_after)))
            self.assertEqual(bytes(before), bytes(after))
            self.assertEqual(bytes(client_before), bytes(client_after))
            self.assertFalse(user32.IsWindowVisible(hwnd))
        finally:
            self.assertTrue(user32.DestroyWindow(hwnd))


class CenteredGeometryTest(unittest.TestCase):
    """按工作区居中；取不到工作区时坐标归 0、尺寸原样。"""

    def _patch_work_area(self, rect: tuple[int, int, int, int] | None):
        """把 SystemParametersInfoW 换成写入指定工作区的假实现。"""
        user32 = mock.MagicMock()

        def _fill(_action, _param, pointer, _flags):
            if rect is None:
                return 0
            box = pointer._obj
            box.left, box.top, box.right, box.bottom = rect
            return 1

        user32.SystemParametersInfoW.side_effect = _fill
        fake_windll = mock.MagicMock(user32=user32)
        return mock.patch.object(window_ops.os, "name", "nt"), \
            mock.patch.object(window_ops.ctypes, "windll", fake_windll, create=True)

    def test_non_windows_returns_zero_origin(self) -> None:
        with mock.patch.object(window_ops.os, "name", "posix"):
            self.assertEqual(window_ops.centered_geometry(1440, 900), (1440, 900, 0, 0))

    def test_centers_inside_work_area(self) -> None:
        name_patch, windll_patch = self._patch_work_area((0, 0, 1920, 1040))
        with name_patch, windll_patch:
            width, height, x, y = window_ops.centered_geometry(1000, 800)
        self.assertEqual((width, height), (1000, 800))
        self.assertEqual((x, y), (460, 120))

    def test_clamps_to_work_area(self) -> None:
        """请求比工作区大时按工作区截断。"""
        name_patch, windll_patch = self._patch_work_area((0, 0, 800, 600))
        with name_patch, windll_patch:
            width, height, x, y = window_ops.centered_geometry(1440, 900)
        self.assertEqual((width, height), (800, 600))
        self.assertEqual((x, y), (0, 0))

    def test_unavailable_work_area_falls_back(self) -> None:
        """SystemParametersInfoW 返回 0（读不到工作区）时退回原点。"""
        name_patch, windll_patch = self._patch_work_area(None)
        with name_patch, windll_patch:
            self.assertEqual(window_ops.centered_geometry(1440, 900), (1440, 900, 0, 0))

    def test_offset_work_area_keeps_origin(self) -> None:
        """多显示器工作区不从 0 起时，居中要带上左上偏移。"""
        name_patch, windll_patch = self._patch_work_area((1920, 0, 3840, 1000))
        with name_patch, windll_patch:
            width, height, x, y = window_ops.centered_geometry(600, 400)
        self.assertEqual((width, height), (600, 400))
        self.assertEqual((x, y), (2580, 300))


    def test_win32_error_falls_back(self) -> None:
        """SystemParametersInfoW 抛错时退回原点，不让启动失败。"""
        user32 = mock.MagicMock()
        user32.SystemParametersInfoW.side_effect = OSError("boom")
        with mock.patch.object(window_ops.os, "name", "nt"), \
                mock.patch.object(window_ops.ctypes, "windll",
                                  mock.MagicMock(user32=user32), create=True):
            self.assertEqual(window_ops.centered_geometry(1440, 900), (1440, 900, 0, 0))


class DragTopTest(unittest.TestCase):
    def test_top_edge_uses_pointer_monitor_native_coordinates_and_top_taskbar(self):
        from types import SimpleNamespace

        forms = mock.MagicMock()
        screen = forms.Screen.FromPoint.return_value
        screen.Bounds = SimpleNamespace(Left=-1920, Right=0, Top=-1080)
        screen.WorkingArea = SimpleNamespace(Top=-1040)
        for x, y, expected in [(-800, -1080, True), (-800, -1032, True),
                               (-800, -1031, False), (-800, -1081, False),
                               (0, -1080, False), (-1921, -1080, False)]:
            with self.subTest(x=x, y=y):
                point = SimpleNamespace(X=x, Y=y)
                forms.Cursor.Position = point
                with mock.patch.object(window_ops.os, "name", "nt"), \
                        mock.patch.dict(sys.modules, {"System.Windows.Forms": forms}):
                    self.assertEqual(window_ops.cursor_at_work_area_top(), expected)
                forms.Screen.FromPoint.assert_called_with(point)

    def test_non_windows_and_monitor_failure_do_not_snap(self):
        with mock.patch.object(window_ops.os, "name", "posix"):
            self.assertFalse(window_ops.cursor_at_work_area_top())
        forms = mock.MagicMock()
        forms.Screen.FromPoint.side_effect = OSError("monitor unavailable")
        with mock.patch.object(window_ops.os, "name", "nt"), \
                mock.patch.dict(sys.modules, {"System.Windows.Forms": forms}), \
                mock.patch.object(window_ops, "report_error") as report:
            self.assertFalse(window_ops.cursor_at_work_area_top())
        report.assert_called_once()


class MaximizedBoundsTest(unittest.TestCase):
    """最大化边界取工作区；非 Windows 与无 native 都直接返回。"""

    def test_non_windows_is_noop(self) -> None:
        with mock.patch.object(window_ops.os, "name", "posix"):
            window_ops.apply_maximized_bounds(object())

    def test_missing_native_is_noop(self) -> None:
        fake_forms = mock.MagicMock()
        with mock.patch.object(window_ops.os, "name", "nt"), \
                mock.patch.dict(sys.modules, {"System.Windows.Forms": fake_forms}):
            window_ops.apply_maximized_bounds(object())

    def test_sets_bounds_from_screen(self) -> None:
        fake_forms = mock.MagicMock()
        fake_forms.Screen.FromHandle.return_value.WorkingArea = "area"
        window = mock.MagicMock()
        window.native.Handle = 321
        with mock.patch.object(window_ops.os, "name", "nt"), \
                mock.patch.dict(sys.modules, {"System.Windows.Forms": fake_forms}):
            window_ops.apply_maximized_bounds(window)
        fake_forms.Screen.FromHandle.assert_called_with(321)
        self.assertEqual(window.native.MaximizedBounds, "area")


    def test_winforms_error_is_swallowed_with_trace(self) -> None:
        """缺 WinForms 或取屏幕失败只留痕：最大化贴边不是启动必需品。"""
        fake_forms = mock.MagicMock()
        fake_forms.Screen.FromHandle.side_effect = OSError("boom")
        window = mock.MagicMock()
        window.native.Handle = 321
        with mock.patch.object(window_ops.os, "name", "nt"), \
                mock.patch.dict(sys.modules, {"System.Windows.Forms": fake_forms}), \
                mock.patch.object(window_ops, "report_error") as report:
            window_ops.apply_maximized_bounds(window)
        report.assert_called_once()


class DarkTitlebarTest(unittest.TestCase):
    """深色标题栏：无句柄不动，非 Windows 不动，异常只留痕。"""

    def test_non_windows_is_noop(self) -> None:
        with mock.patch.object(window_ops.os, "name", "posix"):
            window_ops.apply_dark_titlebar(object())

    def test_no_handle_is_noop(self) -> None:
        with mock.patch.object(window_ops.os, "name", "nt"), \
                mock.patch.object(window_ops, "window_handle", return_value=0), \
                mock.patch.object(window_ops.ctypes, "windll", mock.MagicMock(), create=True):
            window_ops.apply_dark_titlebar(object())

    def test_calls_dwm_with_attribute_20(self) -> None:
        dwmapi = mock.MagicMock()
        fake_windll = mock.MagicMock(dwmapi=dwmapi)
        with mock.patch.object(window_ops.os, "name", "nt"), \
                mock.patch.object(window_ops, "window_handle", return_value=99), \
                mock.patch.object(window_ops.ctypes, "windll", fake_windll, create=True):
            window_ops.apply_dark_titlebar(object())
        args = dwmapi.DwmSetWindowAttribute.call_args[0]
        self.assertEqual(args[0], 99)
        self.assertEqual(args[1], 20)


    def test_dwm_error_is_swallowed_with_trace(self) -> None:
        """DWM 不可用（旧系统）只留痕：不能因此起不了窗。"""
        dwmapi = mock.MagicMock()
        dwmapi.DwmSetWindowAttribute.side_effect = OSError("boom")
        with mock.patch.object(window_ops.os, "name", "nt"), \
                mock.patch.object(window_ops, "window_handle", return_value=99), \
                mock.patch.object(window_ops.ctypes, "windll",
                                  mock.MagicMock(dwmapi=dwmapi), create=True), \
                mock.patch.object(window_ops, "report_error") as report:
            window_ops.apply_dark_titlebar(object())
        report.assert_called_once()


class ActivateWindowTest(unittest.TestCase):
    """前台激活：非 Windows、无句柄、已在前台、需挂接输入队列、不需挂接。"""

    @staticmethod
    def _windll(user32):
        return mock.MagicMock(user32=user32, kernel32=mock.MagicMock(
            GetCurrentThreadId=mock.MagicMock(return_value=789)))

    def test_non_windows_is_noop(self) -> None:
        with mock.patch.object(window_ops.os, "name", "posix"):
            window_ops.activate_window(object())

    def test_no_handle_is_noop(self) -> None:
        with mock.patch.object(window_ops.os, "name", "nt"), \
                mock.patch.object(window_ops, "window_handle", return_value=0):
            window_ops.activate_window(object())

    def test_already_foreground_stops_early(self) -> None:
        """已在前台就不发 Alt、不挂接：那些动作会抢焦点。"""
        user32 = mock.MagicMock()
        user32.GetForegroundWindow.return_value = 123
        with mock.patch.object(window_ops.os, "name", "nt"), \
                mock.patch.object(window_ops, "window_handle", return_value=123), \
                mock.patch.object(window_ops.ctypes, "windll", self._windll(user32), create=True):
            window_ops.activate_window(object())
        user32.SetForegroundWindow.assert_not_called()
        user32.AttachThreadInput.assert_not_called()

    def test_attaches_thread_input_when_foreground_is_other(self) -> None:
        user32 = mock.MagicMock()
        user32.GetForegroundWindow.return_value = 999
        user32.GetWindowThreadProcessId.return_value = 456
        with mock.patch.object(window_ops.os, "name", "nt"), \
                mock.patch.object(window_ops, "window_handle", return_value=123), \
                mock.patch.object(window_ops.ctypes, "windll", self._windll(user32), create=True):
            window_ops.activate_window(object())
        user32.AttachThreadInput.assert_any_call(789, 456, True)
        user32.AttachThreadInput.assert_any_call(789, 456, False)
        user32.SwitchToThisWindow.assert_called_with(123, True)

    def test_sets_foreground_directly_without_foreign_thread(self) -> None:
        """前台线程号取不到时，直接 SetForegroundWindow，不挂接。"""
        user32 = mock.MagicMock()
        user32.GetForegroundWindow.return_value = 999
        user32.GetWindowThreadProcessId.return_value = 0
        with mock.patch.object(window_ops.os, "name", "nt"), \
                mock.patch.object(window_ops, "window_handle", return_value=123), \
                mock.patch.object(window_ops.ctypes, "windll", self._windll(user32), create=True):
            window_ops.activate_window(object())
        user32.AttachThreadInput.assert_not_called()
        user32.SetForegroundWindow.assert_called_with(123)

    def test_win32_error_is_swallowed_with_trace(self) -> None:
        """激活失败只留痕、不抛出：抢不到焦点不该阻断启动。"""
        user32 = mock.MagicMock()
        user32.ShowWindow.side_effect = OSError("boom")
        with mock.patch.object(window_ops.os, "name", "nt"), \
                mock.patch.object(window_ops, "window_handle", return_value=123), \
                mock.patch.object(window_ops.ctypes, "windll", self._windll(user32), create=True), \
                mock.patch.object(window_ops, "report_error") as report:
            window_ops.activate_window(object())
        report.assert_called_once()
        self.assertIn("activate", report.call_args[0][0])


class WindowIconTest(unittest.TestCase):
    """窗口图标：文件不存在或非 Windows 不动。"""

    def test_missing_icon_file_is_noop(self) -> None:
        icon = Path("definitely-not-here.ico")
        with mock.patch.object(window_ops.os, "name", "nt"), \
                mock.patch.object(window_ops, "window_handle", return_value=1):
            window_ops.apply_window_icon(object(), icon)

    def test_non_windows_is_noop(self) -> None:
        icon = Path("anything.ico")
        with mock.patch.object(window_ops.os, "name", "posix"):
            window_ops.apply_window_icon(object(), icon)

    def test_sets_icon_twice_on_success(self) -> None:
        """加载到图标后发两次消息：先设大图标再设小图标。"""
        icon = Path(__file__)
        user32 = mock.MagicMock()
        user32.LoadImageW.return_value = 4242
        fake_windll = mock.MagicMock(user32=user32)
        with mock.patch.object(window_ops.os, "name", "nt"), \
                mock.patch.object(window_ops, "window_handle", return_value=7), \
                mock.patch.object(window_ops.ctypes, "windll", fake_windll, create=True):
            window_ops.apply_window_icon(object(), icon)
        self.assertEqual(user32.SendMessageW.call_count, 2)
        user32.SendMessageW.assert_any_call(7, 0x80, 1, 4242)
        user32.SendMessageW.assert_any_call(7, 0x80, 0, 4242)

    def test_load_failure_sends_nothing(self) -> None:
        """LoadImageW 返回 0（图标加载失败）时不发消息。"""
        icon = Path(__file__)
        user32 = mock.MagicMock()
        user32.LoadImageW.return_value = 0
        fake_windll = mock.MagicMock(user32=user32)
        with mock.patch.object(window_ops.os, "name", "nt"), \
                mock.patch.object(window_ops, "window_handle", return_value=7), \
                mock.patch.object(window_ops.ctypes, "windll", fake_windll, create=True):
            window_ops.apply_window_icon(object(), icon)
        user32.SendMessageW.assert_not_called()

    def test_win32_error_is_swallowed_with_trace(self) -> None:
        """图标设置失败只留痕：不能因为缺图标让窗口起不来。"""
        icon = Path(__file__)
        user32 = mock.MagicMock()
        user32.LoadImageW.side_effect = OSError("boom")
        with mock.patch.object(window_ops.os, "name", "nt"), \
                mock.patch.object(window_ops, "window_handle", return_value=7), \
                mock.patch.object(window_ops.ctypes, "windll",
                                  mock.MagicMock(user32=user32), create=True), \
                mock.patch.object(window_ops, "report_error") as report:
            window_ops.apply_window_icon(object(), icon)
        report.assert_called_once()


if __name__ == "__main__":
    unittest.main()
