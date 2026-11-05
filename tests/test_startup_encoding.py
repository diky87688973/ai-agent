"""启动脚本在旧编码环境下统一控制台与管道输出。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = "主界面 文件根 唤醒调度器 中文路径 ✅"


@unittest.skipUnless(os.name == "nt", "Windows 启动脚本")
class StartupEncodingTest(unittest.TestCase):
    def _probe(self, console: bool) -> tuple[dict, bytes, bytes]:
        with tempfile.TemporaryDirectory(prefix="agent-编码-") as directory:
            root = Path(directory)
            report = root / "report.json"
            probe = root / "probe.py"
            probe.write_text(
                "import ctypes, json, sys\n"
                "from pathlib import Path\n"
                f"sample = {SAMPLE!r}\n"
                "print(sample, flush=True)\n"
                "print(sample, file=sys.stderr, flush=True)\n"
                "result = dict(stdout=sys.stdout.encoding, stderr=sys.stderr.encoding, "
                "utf8=sys.flags.utf8_mode, codepage=ctypes.windll.kernel32.GetConsoleOutputCP())\n"
                f"Path({str(report)!r}).write_text(json.dumps(result), encoding='utf-8')\n",
                encoding="utf-8",
            )
            # 执行实际编码初始化段；依赖安装与服务启动不属于编码回归。
            prefix = (ROOT / "start.bat").read_text(encoding="utf-8").split(
                "rem ---- 1. Find Python", 1)[0]
            command = subprocess.list2cmdline([sys.executable, str(probe)])
            batch = root / "probe.bat"
            batch.write_text(prefix + command + "\nexit /b %errorlevel%\n", encoding="utf-8")
            env = dict(os.environ, PYTHONUTF8="0", PYTHONIOENCODING="cp936",
                       PYTHONLEGACYWINDOWSSTDIO="1")
            options = {}
            if console:
                startup = subprocess.STARTUPINFO()
                startup.dwFlags = subprocess.STARTF_USESHOWWINDOW
                startup.wShowWindow = 0
                options = dict(creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=startup)
            else:
                options = dict(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            result = subprocess.run(
                [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(batch)],
                env=env, timeout=30, check=True, **options,
            )
            return json.loads(report.read_text(encoding="utf-8")), result.stdout, result.stderr

    def test_redirected_logs_are_utf8_in_legacy_environment(self) -> None:
        report, stdout, stderr = self._probe(False)
        self.assertIn(SAMPLE, stdout.decode("utf-8"))
        self.assertEqual(stderr.decode("utf-8").strip(), SAMPLE)
        self.assertEqual(report["stdout"], "utf-8")
        self.assertEqual(report["stderr"], "utf-8")
        self.assertEqual(report["utf8"], 1)

    def test_native_console_uses_utf8_codepage(self) -> None:
        report, _, _ = self._probe(True)
        self.assertEqual(report["codepage"], 65001)
        self.assertEqual(report["stdout"], "utf-8")
        self.assertEqual(report["stderr"], "utf-8")
        self.assertEqual(report["utf8"], 1)
