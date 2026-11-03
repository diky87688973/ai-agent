# -*- coding: utf-8 -*-
"""端口清理：监听过滤、进程强杀与端口释放。"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.gui import port_cleanup  # noqa: E402


class PortCleanupTest(unittest.TestCase):
    def test_windows_listener_filter_uses_local_host(self) -> None:
        output = """  TCP    127.0.0.1:3156       0.0.0.0:0      LISTENING       111
  TCP    127.0.0.2:3156       0.0.0.0:0      LISTENING       222
  TCP    0.0.0.0:3156         0.0.0.0:0      LISTENING       333
  TCP    127.0.0.1:9999       0.0.0.0:0      LISTENING       444
"""
        completed = subprocess.CompletedProcess([], 0, stdout=output)
        fake_os = mock.Mock()
        fake_os.name = "nt"
        with mock.patch.object(port_cleanup, "os", fake_os), \
                mock.patch.object(port_cleanup.subprocess, "run", return_value=completed):
            self.assertEqual(port_cleanup.listening_pids("127.0.0.1", 3156), [111, 333])
            self.assertEqual(port_cleanup.listening_pids("127.0.0.2", 3156), [222, 333])

    def test_kill_pid_uses_windows_tree_kill(self) -> None:
        completed = subprocess.CompletedProcess([], 0)
        fake_os = mock.Mock()
        fake_os.name = "nt"
        fake_os.getpid.return_value = 1
        with mock.patch.object(port_cleanup, "os", fake_os), \
                mock.patch.object(port_cleanup.subprocess, "run", return_value=completed) as run:
            self.assertTrue(port_cleanup.kill_pid(1234))
        self.assertEqual(run.call_args.args[0][:3], ["taskkill", "/PID", "1234"])

    def test_force_stop_waits_for_release(self) -> None:
        with mock.patch.object(port_cleanup, "listening_pids", side_effect=[[123], []]), \
                mock.patch.object(port_cleanup, "kill_pid", return_value=True) as kill, \
                mock.patch.object(port_cleanup.time, "monotonic", side_effect=[0.0, 0.0]):
            self.assertTrue(port_cleanup.force_stop_agent_port(
                "127.0.0.1", 3156, lambda *_args, **_kwargs: False))
        kill.assert_called_once_with(123)

    def test_force_stop_stops_when_kill_fails(self) -> None:
        with mock.patch.object(port_cleanup, "listening_pids", return_value=[123]), \
                mock.patch.object(port_cleanup, "kill_pid", return_value=False) as kill:
            self.assertFalse(port_cleanup.force_stop_agent_port(
                "127.0.0.1", 3156, lambda *_args, **_kwargs: True))
        kill.assert_called_once_with(123)


if __name__ == "__main__":
    unittest.main()
