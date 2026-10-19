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
        block = self.js[self.js.index("/* ── Visual Operator 的详情区"):
                        self.js.index("window.aiAgentChatTools")]
        self.assertNotIn("chatToolViewDefault.mount", block)
        self.assertNotIn("chatToolViewDefault.fill", block)
        self.assertNotIn('"请求"', block)
        self.assertNotIn('"响应"', block)
        # 与 read_image 同一句：无标题的 shot 层，图片与尺寸/来源直接进自定义视图。
        self.assertIn('addChatToolLayer(row._body,"","shot")', block)
        self.assertEqual(block.count('addChatToolLayer(row._body,"","shot")'), 1)

    def test_desktop_shot_reuses_the_read_image_meta_block(self) -> None:
        block = self.js[self.js.index("/* ── Visual Operator 的详情区"):
                        self.js.index("window.aiAgentChatTools")]
        for cls in ("chat-tool-shot", "chat-tool-shot-miss", "chat-tool-shot-meta",
                    "chat-tool-shot-path"):
            self.assertIn(cls, block)
        self.assertLess(block.index('"尺寸: "'), block.index('"窗口: "'))


class WaitTitleFormatTest(unittest.TestCase):
    """`desktop_wait` 等待中倒计时，结束后在标题末尾带上实际等待时长。"""

    def setUp(self) -> None:
        self.js = (ROOT / "agent/shell/web_assets/classic/js/tools/titles.js"
                   ).read_text(encoding="utf-8")

    def test_short_durations_keep_one_decimal_of_seconds(self) -> None:
        self.assertIn("function desktopDurationText(ms)", self.js)
        block = self.js[self.js.index("function desktopDurationText(ms)"):][:400]
        self.assertIn("total<10000", block)
        self.assertIn('" 秒"', block)
        self.assertNotIn("毫秒", block)

    def test_wait_title_prints_the_waited_time(self) -> None:
        block = self.js[self.js.index('if(kind==="wait"){'):]
        block = block[:block.index('return {main:"等待条件"')]
        self.assertIn('label+=" · "+desktopDurationText(d.waited_ms)', block)
        self.assertNotIn("已达成", block)
        self.assertNotIn("未达成", block)
        self.assertNotIn("已等待", block)

    def test_countdown_uses_the_timeout_as_its_duration(self) -> None:
        block = self.js[self.js.index("function desktopWaitSeconds("):]
        block = block[:block.index("function desktopWaitTickText(")]
        self.assertIn('argGet(args,"timeout_ms")', block)
        self.assertIn("Math.ceil(ms/1000)", block)

    def test_countdown_says_timeout_once_the_deadline_passes(self) -> None:
        block = self.js[self.js.index("function desktopWaitTickText("):]
        block = block[:block.index("var _desktopWaitTickers")]
        self.assertIn("function desktopWaitTickText(script,args,left,elapsedMs)", block)
        self.assertIn('"剩余 "', block)
        self.assertIn('"已超时 "', block)
        self.assertNotIn("已达成", block)
        self.assertNotIn("未达成", block)

    def test_ticker_keeps_counting_overtime_until_the_result_arrives(self) -> None:
        block = self.js[self.js.index("function desktopStartWaitTicker("):]
        self.assertIn("if(kind!==\"wait\"&&left<=0)desktopStopWaitTicker(key)", block)
        self.assertIn("entry.applys[i](left,entry.total,elapsed)", block)
        for rel in ("chat/llm-rounds.js", "chat-tool-views.js"):
            text = (ROOT / "agent/shell/web_assets/classic/js" / rel).read_text(
                encoding="utf-8")
            self.assertIn("function(left,total,elapsed)", text, msg=rel)
            self.assertIn("desktopWaitTickText(", text, msg=rel)

    def test_nothing_is_reported_from_the_server_while_waiting(self) -> None:
        stream = (ROOT / "agent/shell/web_assets/classic/js/chat/llm-rounds.js"
                  ).read_text(encoding="utf-8")
        self.assertNotIn("desktopWaitAnchor", stream)
        self.assertNotIn("desktopWaitAnchor", self.js)
        wait_tool = (ROOT / "plugins/visual_operator/tools/wait.py").read_text(
            encoding="utf-8")
        self.assertNotIn("emit_progress", wait_tool)

    def test_long_durations_are_written_in_units(self) -> None:
        block = self.js[self.js.index("function desktopDurationText(ms)"):][:1400]
        for unit in ('" 天"', '" 小时"', '" 分"'):
            self.assertIn(unit, block)
        self.assertIn("rest/86400", block)


if __name__ == "__main__":
    unittest.main()
