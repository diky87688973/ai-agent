# -*- coding: utf-8 -*-
"""对话区窄宽守卫：不锁固定最小宽度，输入区按钮组允许换行。"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.shell.web.ui_bundle import read_ui_css  # noqa: E402


class ChatMinWidthTest(unittest.TestCase):
    """对话区可随窗口缩窄，控件通过换行避免越界。"""

    def _css(self) -> str:
        return read_ui_css()

    def test_chat_allows_narrow_layout(self) -> None:
        m = re.search(r"\.chat\{[^}]*min-width:0", self._css())
        self.assertIsNotNone(m, msg="样式表里 .chat 不应锁固定最小宽度")

    def test_composer_footer_wraps(self) -> None:
        m = re.search(r"\.composer-foot\{[^}]*flex-wrap:wrap", self._css())
        self.assertIsNotNone(m, msg="输入区按钮组必须允许换行")


if __name__ == "__main__":
    unittest.main()
