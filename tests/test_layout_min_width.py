# -*- coding: utf-8 -*-
"""对话区最小宽度守卫：样式表与脚本里的数字必须一致，且大到能容下控件。

数值取自布局测量（669px 时"发送"越界 1px，670px 起为 0），这里只守两件事：
两处同值、且不小于测得下界。调小会让控件重新出界。
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.shell.ui_bundle import read_ui_css, read_ui_js  # noqa: E402

#: 测得下界：更窄时输入区最右侧控件越过容器右边界
MEASURED_MIN_PX = 670


class ChatMinWidthTest(unittest.TestCase):
    """对话区最小宽度：两处同值 + 不小于测得下界。"""

    def _css_px(self) -> int:
        m = re.search(r"\.chat\{[^}]*min-width:(\d+)px", read_ui_css())
        self.assertIsNotNone(m, msg="样式表里找不到 .chat 的 min-width")
        return int(m.group(1))

    def _js_px(self) -> int:
        m = re.search(r"var MIN_CHAT_PX=(\d+)", read_ui_js())
        self.assertIsNotNone(m, msg="脚本里找不到 MIN_CHAT_PX")
        return int(m.group(1))

    def test_two_places_agree(self) -> None:
        self.assertEqual(self._css_px(), self._js_px(),
                         msg="样式表与脚本的最小宽度必须同值，否则拖拽与布局会各算各的")

    def test_not_smaller_than_measured(self) -> None:
        got = self._css_px()
        self.assertGreaterEqual(
            got, MEASURED_MIN_PX,
            msg=f"最小宽度 {got}px 小于测得下界 {MEASURED_MIN_PX}px，控件会顶出边界")
        js = read_ui_js()
        self.assertIn("mainInnerWidth()-RESIZER_PX-MIN_CHAT_PX", js,
                      msg="右栏上限必须扣掉对话区最小宽度")


if __name__ == "__main__":
    unittest.main()
