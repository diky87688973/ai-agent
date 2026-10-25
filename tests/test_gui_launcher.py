# -*- coding: utf-8 -*-
"""GUI 启动器：服务子进程必须随窗口启动，并在窗口关闭后终止。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.gui import launcher  # noqa: E402


class GuiLauncherTest(unittest.TestCase):
    def test_launch_owns_child_and_stops_it(self) -> None:
        child = object()
        with mock.patch.object(launcher, "_pick_port", return_value=8899), \
                mock.patch.object(launcher, "_spawn_server", return_value=child) as spawn, \
                mock.patch.object(launcher, "_wait_health", return_value=True), \
                mock.patch.object(launcher, "_open_window", return_value=True), \
                mock.patch.object(launcher, "_stop_server") as stop:
            code = launcher.launch("127.0.0.1", 0)
        self.assertEqual(code, 0)
        spawn.assert_called_once_with("127.0.0.1", 8899)
        stop.assert_called_once_with(child)

    def test_failed_window_still_stops_child(self) -> None:
        child = object()
        with mock.patch.object(launcher, "_spawn_server", return_value=child), \
                mock.patch.object(launcher, "_wait_health", return_value=True), \
                mock.patch.object(launcher, "_open_window", return_value=False), \
                mock.patch.object(launcher, "_stop_server") as stop:
            code = launcher.launch("127.0.0.1", 8899)
        self.assertEqual(code, 1)
        stop.assert_called_once_with(child)

    def test_occupied_explicit_port_does_not_spawn(self) -> None:
        with mock.patch.object(launcher, "_is_agent_health", return_value=True), \
                mock.patch.object(launcher, "_spawn_server") as spawn:
            code = launcher.launch("127.0.0.1", 8899)
        self.assertEqual(code, 1)
        spawn.assert_not_called()

    def test_missing_entry_returns_nonzero(self) -> None:
        with mock.patch.object(launcher, "_spawn_server", return_value=None):
            code = launcher.launch("127.0.0.1", 8899)
        self.assertEqual(code, 1)


    def test_activate_window_uses_windows_api(self) -> None:
        user32 = mock.MagicMock()
        user32.GetForegroundWindow.return_value = 999
        user32.GetWindowThreadProcessId.return_value = 456
        kernel32 = mock.MagicMock()
        kernel32.GetCurrentThreadId.return_value = 789
        fake_windll = mock.MagicMock(user32=user32, kernel32=kernel32)
        with mock.patch.object(launcher, "_window_handle", return_value=123), \
                mock.patch.object(launcher.os, "name", "nt"), \
                mock.patch.object(launcher.ctypes, "windll", fake_windll, create=True):
            launcher._activate_window(object())
        user32.SetForegroundWindow.assert_called_with(123)
        user32.SetFocus.assert_called_with(123)
        user32.AttachThreadInput.assert_any_call(789, 456, True)

    def test_activate_window_without_handle(self) -> None:
        with mock.patch.object(launcher, "_window_handle", return_value=0):
            launcher._activate_window(object())

    def test_open_window_enables_text_selection(self) -> None:
        class _Events:
            shown = mock.MagicMock()
            loaded = mock.MagicMock()

        class _Window:
            events = _Events()
            native = None
            expose = mock.MagicMock()

        fake = mock.MagicMock()
        fake.settings = {}
        fake.create_window.return_value = _Window()
        with mock.patch.dict(sys.modules, {"webview": fake}):
            self.assertTrue(launcher._open_window("http://127.0.0.1:1/"))
        self.assertTrue(fake.create_window.call_args.kwargs["text_select"])

    def test_pick_port_and_storage_path(self) -> None:
        port = launcher._pick_port("127.0.0.1")
        self.assertGreater(port, 0)
        self.assertIsInstance(launcher._storage_path(), Path)


if __name__ == "__main__":
    unittest.main()
