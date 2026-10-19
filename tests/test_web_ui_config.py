# -*- coding: utf-8 -*-
"""web-ui-config.ini：对话区工具条目与步骤面板的展示开关。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.shell.ui_bundle import read_ui_js
from agent.shell.web_ui_config import get_web_ui

ROOT = Path(__file__).resolve().parent.parent


class WebUiConfigTest(unittest.TestCase):
    def test_missing_file_defaults_items_on_steps_off(self) -> None:
        cfg = get_web_ui(Path(tempfile.gettempdir()) / "web-ui-missing.ini")
        self.assertTrue(cfg["display_tool_items"])
        self.assertFalse(cfg["display_tool_steps"])

    def test_only_digit_one_turns_a_flag_on(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "web-ui-config.ini"
            path.write_text(
                "[web-ui]\n"
                "display_tool_items = 0\n"
                "display_tool_steps = 1\n",
                encoding="utf-8",
            )
            cfg = get_web_ui(path)
        self.assertFalse(cfg["display_tool_items"])
        self.assertTrue(cfg["display_tool_steps"])

    def test_blank_value_keeps_the_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "web-ui-config.ini"
            path.write_text(
                "[web-ui]\n"
                "display_tool_items =\n"
                "display_tool_steps =\n",
                encoding="utf-8",
            )
            cfg = get_web_ui(path)
        self.assertTrue(cfg["display_tool_items"])
        self.assertFalse(cfg["display_tool_steps"])

    def test_classic_page_wires_the_placeholder(self) -> None:
        """配置注入与工具卡拆分：占位符、开关属性、工具视图脚本进包。"""
        html = (ROOT / "agent/shell/web_assets/classic/agent-ui.html").read_text(
            encoding="utf-8"
        )
        js = read_ui_js()
        tool_js = (
            ROOT / "agent/shell/web_assets/classic/js/chat-tool-views.js"
        ).read_text(encoding="utf-8")
        bundle = (ROOT / "agent/shell/ui_bundle.py").read_text(encoding="utf-8")
        routes = (ROOT / "agent/shell/web_routes.py").read_text(encoding="utf-8")
        self.assertIn("{{WEB_UI_JSON}}", html)
        self.assertIn("data-tool-steps", html)
        self.assertIn("function showToolSteps()", js)
        self.assertNotIn("function mountChatToolItem(", js)
        self.assertIn("function mountChatToolItem(", tool_js)
        self.assertIn("chat-tool-views.js", bundle)
        self.assertIn("{{WEB_UI_JSON}}", routes)
        self.assertIn("get_web_ui", routes)


class ToolDetailLayoutTest(unittest.TestCase):
    """工具详情只有两种形态，不能混着来。

    自定义视图（看图、看屏、diff…）由 `attachChatToolPacket` 把请求/响应收进
    「查看报文」按钮；一旦视图自己挂了 `.chat-tool-layer--req/res`，
    `chatToolShowsRaw` 为真、装箱被跳过，JSON 就会挤在图片上面。
    """

    def setUp(self) -> None:
        self.js = (
            ROOT / "agent/shell/web_assets/classic/js/chat-tool-views.js"
        ).read_text(encoding="utf-8")

    def test_desktop_views_do_not_mount_raw_panels(self) -> None:
        block = self.js[self.js.index("/* ── 桌面 IO 的详情区"):
                        self.js.index("window.aiAgentChatTools")]
        self.assertNotIn("chatToolViewDefault.mount", block)
        self.assertNotIn("chatToolViewDefault.fill", block)
        self.assertNotIn('"请求"', block)
        self.assertNotIn('"响应"', block)
        # 与 read_image 同一句：无标题的 shot 层，图片与尺寸/来源直接进自定义视图。
        self.assertIn('addChatToolLayer(row._body,"","shot")', block)
        self.assertEqual(block.count('addChatToolLayer(row._body,"","shot")'), 1)

    def test_desktop_shot_reuses_the_read_image_meta_block(self) -> None:
        block = self.js[self.js.index("/* ── 桌面 IO 的详情区"):
                        self.js.index("window.aiAgentChatTools")]
        for cls in ("chat-tool-shot", "chat-tool-shot-miss", "chat-tool-shot-meta",
                    "chat-tool-shot-path"):
            self.assertIn(cls, block)
        self.assertLess(block.index('"尺寸: "'), block.index('"窗口: "'))


if __name__ == "__main__":
    unittest.main()
