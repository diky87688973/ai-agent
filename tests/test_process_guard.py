# -*- coding: utf-8 -*-
"""子进程守护的契约：可调用、不抛异常、失败由调用方兜底。"""
from __future__ import annotations

import subprocess
import sys
import unittest

from agent.common.process_guard import adopt


class AdoptTest(unittest.TestCase):
    def test_rejects_invalid_pid(self) -> None:
        self.assertFalse(adopt(0))
        self.assertFalse(adopt(-1))

    def test_returns_bool_for_real_child(self) -> None:
        """真起一个子进程交给作业对象；不断言必然成功——父进程若已在别的
        作业对象里，嵌套可能被拒，那属于环境限制，不该让本用例变红。"""
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        try:
            self.assertIsInstance(adopt(proc.pid), bool)
        finally:
            proc.wait(timeout=30)

    def test_adopted_child_dies_with_parent(self) -> None:
        """父进程退出后子进程必须消失——这条是守护的实质，不能只测返回值。"""
        if sys.platform != "win32":
            self.skipTest("作业对象仅 Windows 有")
        script = (
            "import subprocess, sys; sys.path.insert(0, r'D:\\FanFiles\\Fan_AI_Agent'); "
            "from agent.common.process_guard import adopt; "
            "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)']); "
            "print(p.pid, flush=True); adopt(p.pid)"
        )
        done = subprocess.run([sys.executable, "-c", script],
                              capture_output=True, text=True, timeout=60)
        pid_text = (done.stdout or "").strip()
        self.assertTrue(pid_text.isdigit(), msg=f"未拿到子进程 pid：{done.stdout}{done.stderr}")
        child = int(pid_text)
        alive = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"if (Get-Process -Id {child} -ErrorAction SilentlyContinue) {{ 'alive' }} else {{ 'gone' }}"],
            capture_output=True, text=True, timeout=30)
        if alive.stdout.strip() == "alive":
            subprocess.run(["taskkill", "/PID", str(child), "/F"], capture_output=True)
            self.fail(f"父进程退出后子进程 {child} 仍存活")


if __name__ == "__main__":
    unittest.main()
