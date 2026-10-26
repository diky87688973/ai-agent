# -*- coding: utf-8 -*-
"""更新器进程边界：按安装路径停止旧 GUI。"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from agent.update.processes import (
    cleanup_launcher_archives,
    find_pids,
    stop_old_launcher,
)


@unittest.skipUnless(os.name == "nt", "仅 Windows 有按映像路径终止进程的语义")
class ProcessStopTest(unittest.TestCase):
    def test_removes_old_launcher_archives(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "updates" / "launcher"
            folder.mkdir(parents=True)
            (folder / "agent-gui.exe.old-1").write_text("old", encoding="utf-8")
            (folder / "agent-gui.exe.old-2").write_text("old", encoding="utf-8")
            removed = cleanup_launcher_archives(root, attempts=1)
            self.assertEqual(len(removed), 2)
            self.assertEqual(list(folder.iterdir()), [])

    def test_stops_matching_running_executable(self) -> None:
        tmp = tempfile.mkdtemp()
        root = Path(tmp)
        executable = root / "agent-gui.exe"
        shutil.copy2(Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe", executable)
        process = subprocess.Popen(
            [str(executable), "/c", "ping", "-n", "30", "127.0.0.1"],
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if process.pid in find_pids(executable):
                    break
                time.sleep(0.05)
            killed = stop_old_launcher(root, wait_seconds=0)
            self.assertIn(process.pid, killed)
            self.assertIsNotNone(process.wait(timeout=5))
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
            shutil.rmtree(tmp, ignore_errors=True)
