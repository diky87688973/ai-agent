# -*- coding: utf-8 -*-
"""依赖图不变量（A2）：环为零、装配根不被反向依赖、层序可机检。

`scripts/check_imports.py` 是门禁实现；这里把它当断言库用，
再补一条门禁扫不到的：运行期导入 `agent.shell.web` 不得把 `agent.app` 带进来。
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

import check_imports  # noqa: E402


class DependencyGraphTest(unittest.TestCase):
    """当前仓库必须零违规、零强连通分量。"""

    def test_no_direction_violations(self) -> None:
        self.assertEqual(check_imports.check(), [])

    def test_no_cycles(self) -> None:
        self.assertEqual(check_imports.cycles(), [])

    def test_entry_is_the_top_layer(self) -> None:
        self.assertEqual(check_imports.LAYERS[-1], "entry")
        self.assertLess(
            check_imports.RANK["shell"], check_imports.RANK["entry"]
        )

    def test_shell_does_not_import_the_composition_root(self) -> None:
        """运行期导入壳层不应把装配根拉进 `sys.modules`。"""
        code = (
            "import sys;"
            "import agent.shell.web.server, agent.shell.cli.interactive, agent.shell.cli.headless;"
            "assert 'agent.app' not in sys.modules, 'shell 反向导入了装配根';"
            "print('ok')"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code], cwd=str(_ROOT),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertIn("ok", proc.stdout)

    def test_entry_may_import_the_composition_root(self) -> None:
        """入口层是唯一允许导入装配根的地方（这正是它存在的理由）。"""
        code = (
            "import sys;"
            "import agent.entry.web;"
            "assert 'agent.app' in sys.modules;"
            "print('ok')"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code], cwd=str(_ROOT),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
