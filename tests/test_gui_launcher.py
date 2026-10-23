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


if __name__ == "__main__":
    unittest.main()
