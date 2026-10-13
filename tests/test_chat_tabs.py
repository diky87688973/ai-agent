# -*- coding: utf-8 -*-
"""会话标签栏：最后一个会话不给关。

`closeConversationTab` 有守卫（`conversationTabs.length<=1` 直接返回），
标签栏也据此**不渲染关闭按钮** —— 关到只剩一个时 `wc` 变假、按钮被移除。
两处必须一致：只做守卫会让用户点一个不会生效的 ×；
只隐藏按钮而没有守卫，则任何直接调用都会把界面关成空的。
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

_UI_JS = _ROOT / "agent/shell/web_assets/classic/js/agent-ui.js"


def _fn_body(src: str, name: str) -> str:
    """取某个函数的源码片段（到下一个顶层 function 为止）。"""
    i = src.index(f"function {name}(")
    j = src.find("\nfunction ", i + 10)
    return src[i:j if j > 0 else len(src)]


class LastTabCannotCloseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.src = _UI_JS.read_text(encoding="utf-8")

    def test_close_guard_rejects_the_last_tab(self) -> None:
        """守卫必须在改任何状态**之前**返回。"""
        body = _fn_body(self.src, "closeConversationTab")
        guard = re.search(r"if\(conversationTabs\.length<=1\)\s*return;", body)
        self.assertIsNotNone(guard, msg="closeConversationTab 缺少最后一个标签的守卫")
        # 守卫出现在数组改动之前
        splice = body.index("conversationTabs.splice")
        self.assertLess(guard.start(), splice, msg="守卫必须在 splice 之前")

    def test_close_button_is_rendered_only_when_closable(self) -> None:
        """标签栏按 `wc`（多于一个标签）决定建不建关闭按钮，否则移除。"""
        body = _fn_body(self.src, "renderChatTabs")
        self.assertRegex(body, r"var wc=conversationTabs\.length>1;",
                         msg="缺少「是否可关」的判据")
        self.assertIn("chat-tab-close", body)
        # 分支形状：wc 为真才创建，否则移除
        self.assertRegex(body, r"if\(wc\)\{[\s\S]*?createElement\(\"button\"\)")
        self.assertRegex(body, r"else\{if\(xc\)xc\.remove\(\);\}")

    def test_closing_rerenders_the_tab_bar(self) -> None:
        """关闭后必须重绘 —— 否则最后一个标签会留着点不动的 ×。"""
        body = _fn_body(self.src, "closeConversationTab")
        self.assertIn("renderChatTabs()", body)


if __name__ == "__main__":
    unittest.main()
