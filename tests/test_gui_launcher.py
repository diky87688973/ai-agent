# -*- coding: utf-8 -*-
"""GUI 启动器：服务子进程必须随窗口启动，并在窗口关闭后终止。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.gui import launcher, window_ops  # noqa: E402


class GuiLauncherTest(unittest.TestCase):
    def test_startup_helpers_do_not_create_windows_console(self):
        from agent.gui import port_cleanup

        root = Path(__file__).resolve().parent.parent
        with mock.patch.object(launcher, "_app_root", return_value=root), \
                mock.patch.object(launcher.shutil, "which", return_value="python.exe"), \
                mock.patch.object(launcher.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
                mock.patch.object(launcher.subprocess, "run") as run:
            run.return_value.returncode = 0
            for platform in ("nt", "posix"):
                with mock.patch.object(launcher.os, "name", platform):
                    self.assertEqual(launcher._python_command(), ["python.exe"])
                self.assertEqual(run.call_args.kwargs["creationflags"], 0x08000000 if platform == "nt" else 0)
            with mock.patch.object(port_cleanup.os, "name", "nt"):
                run.return_value.stdout = ""
                self.assertEqual(port_cleanup.listening_pids("127.0.0.1", 3156), [])
                self.assertEqual(run.call_args.kwargs["creationflags"], 0x08000000)
                self.assertTrue(port_cleanup.kill_pid(987654))
                self.assertEqual(run.call_args.kwargs["creationflags"], 0x08000000)

    def test_launch_owns_child_and_stops_it(self) -> None:
        child = object()
        with mock.patch.object(launcher, "_pick_port", return_value=8899), \
                mock.patch.object(launcher, "_spawn_server", return_value=child) as spawn, \
                mock.patch.object(launcher, "_wait_health", return_value=True), \
                mock.patch.object(launcher, "_open_window", return_value=True), \
                mock.patch.object(launcher, "_stop_server") as stop:
            code = launcher.launch("127.0.0.1", 0)
        self.assertEqual(code, 0)
        spawn.assert_called_once()
        args = spawn.call_args.args
        self.assertEqual(args[:2], ("127.0.0.1", 8899))
        self.assertTrue(args[2])
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

    def test_occupied_explicit_port_restarts_old_agent(self) -> None:
        child = object()
        with mock.patch.object(launcher, "_is_agent_health", return_value=True), \
                mock.patch.object(launcher, "_force_stop_agent_port", return_value=True) as force, \
                mock.patch.object(launcher, "_spawn_server", return_value=child) as spawn, \
                mock.patch.object(launcher, "_wait_health", return_value=True), \
                mock.patch.object(launcher, "_open_window", return_value=True), \
                mock.patch.object(launcher, "_stop_server"):
            code = launcher.launch("127.0.0.1", 8899)
        self.assertEqual(code, 0)
        force.assert_called_once()
        self.assertEqual(force.call_args.args[:2], ("127.0.0.1", 8899))
        spawn.assert_called_once()

        with mock.patch.object(launcher, "_is_agent_health", return_value=True), \
                mock.patch.object(launcher, "_force_stop_agent_port", return_value=False), \
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
        with mock.patch.object(window_ops, "window_handle", return_value=123), \
                mock.patch.object(window_ops.os, "name", "nt"), \
                mock.patch.object(window_ops.ctypes, "windll", fake_windll, create=True):
            window_ops.activate_window(object())
        user32.SetForegroundWindow.assert_called_with(123)
        user32.SetFocus.assert_called_with(123)
        user32.AttachThreadInput.assert_any_call(789, 456, True)

    def test_activate_window_without_handle(self) -> None:
        with mock.patch.object(window_ops, "window_handle", return_value=0):
            window_ops.activate_window(object())

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

    def test_window_close_stops_supervisor_and_destroys_window(self) -> None:
        supervisor = mock.MagicMock()
        window = mock.MagicMock()
        api = launcher._WindowApi(supervisor)
        api._window = window
        self.assertTrue(api.close())
        supervisor.stop.assert_called_once()
        window.destroy.assert_called_once()

    def test_drag_top_bridge_requires_window_and_uses_native_monitor_query(self):
        api = launcher._WindowApi()
        with mock.patch.object(window_ops, "cursor_at_work_area_top", return_value=True) as query:
            self.assertFalse(api.cursor_at_work_area_top())
            query.assert_not_called()
            api._window = mock.MagicMock()
            self.assertTrue(api.cursor_at_work_area_top())
            query.assert_called_once()
            api._window.maximize.assert_not_called()

    def test_native_shown_callback_enables_taskbar_minimize(self) -> None:
        from types import SimpleNamespace

        class Hook:
            def __iadd__(self, callback):
                self.callback = callback
                return self

        window = SimpleNamespace(events=SimpleNamespace(shown=Hook(), loaded=Hook()),
                                 native=None, expose=mock.MagicMock())
        fake = mock.MagicMock(settings={})
        fake.create_window.return_value = window
        fake.start.side_effect = lambda **_kwargs: window.events.shown.callback()
        with mock.patch.dict(sys.modules, {"webview": fake}), \
                mock.patch.object(launcher, "_storage_path", return_value=Path(".")), \
                mock.patch.object(launcher.threading, "Timer"), \
                mock.patch.object(window_ops, "activate_window"), \
                mock.patch.object(window_ops, "apply_maximized_bounds"), \
                mock.patch.object(window_ops, "enable_taskbar_minimize", return_value=True) as enable:
            self.assertTrue(launcher._open_window("http://127.0.0.1:1/"))
        enable.assert_called_once_with(window)
        self.assertIs(window.events.loaded.callback, window.events.shown.callback)
        self.assertTrue(fake.create_window.call_args.kwargs["frameless"])

    def test_pick_port_and_storage_path(self) -> None:
        port = launcher._pick_port("127.0.0.1")
        self.assertGreater(port, 0)
        self.assertIsInstance(launcher._storage_path(), Path)


if __name__ == "__main__":
    unittest.main()
