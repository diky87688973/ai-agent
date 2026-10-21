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


class ImageLightboxDefaultModeTest(unittest.TestCase):
    """预览默认以 1:1 打开并双向居中。

    两处必须同时成立，少一处就看不见效果：
    JS 侧的尺寸与滚动归中，CSS 侧的对齐不能把它抵消掉。
    """

    def setUp(self) -> None:
        self.js = (
            ROOT / "agent/shell/web_assets/classic/js/image-lightbox.js"
        ).read_text(encoding="utf-8")
        self.css = (
            ROOT / "agent/shell/web_assets/classic/css/chat-messages.css"
        ).read_text(encoding="utf-8")

    def test_default_mode_is_pixel_not_fit(self) -> None:
        self.assertIn('el._cwaMode = "pixel";', self.js)
        # 旧写法会把用户上一次选的模式带到下一次打开，与“默认”矛盾
        self.assertNotIn('el._cwaMode = el._cwaMode || "fit"', self.js)
        self.assertNotIn('el._cwaMode = "fit"', self.js)

    def test_pixel_mode_centers_both_axes(self) -> None:
        block = self.js[self.js.index('if (mode === "pixel") {'):]
        block = block[: block.index("return;")]
        self.assertIn('img.style.margin = "auto"', block)
        self.assertIn("centerLightboxStage(el)", block)
        # 铺满模式必须清掉外边距，否则会继承上一种模式的定位
        self.assertIn('img.style.margin = "0"', self.js)

    def test_stage_scroll_is_centered_not_left_top(self) -> None:
        self.assertIn("function centerLightboxStage(el)", self.js)
        start = self.js.index("function centerLightboxStage(el)")
        block = self.js[start:start + 320]
        self.assertIn("scrollLeft", block)
        self.assertIn("scrollTop", block)

    def test_css_does_not_pin_pixel_mode_to_a_corner(self) -> None:
        self.assertIn("justify-content:safe center", self.css)
        self.assertIn("align-items:safe center", self.css)
        # 原先把 1:1 钉在左上角，正是“打开就贴角”的直接原因
        self.assertNotIn("is-pixel{align-items:flex-start", self.css)

    def test_pixel_padding_is_small_enough_to_still_center(self) -> None:
        """1:1 的内边距不能大：图+内边距超过视口时，margin:auto 失效、图贴顶。

        实测：视口高 919px、图 900px，旧内边距上下共 104px 直接让它溢出。
        """
        start = self.css.index(".img-lightbox-stage.is-pixel{")
        rule = self.css[start:self.css.index("}", start)]
        self.assertIn("padding:8px", rule)
        for too_big in ("padding:48px", "56px"):
            self.assertNotIn(too_big, rule)


class ToolShotPreviewClickTest(unittest.TestCase):
    """工具壳详情里的图片点开同一个预览。"""

    def setUp(self) -> None:
        self.js = (
            ROOT / "agent/shell/web_assets/classic/js/chat-tool-views.js"
        ).read_text(encoding="utf-8")

    def test_both_image_views_are_clickable(self) -> None:
        # read_image 与 desktop_*（看屏/截图）两个视图各一处
        self.assertEqual(self.js.count("bindToolShotPreview(img);"), 2)

    def test_click_delegates_to_the_shared_lightbox(self) -> None:
        start = self.js.index("function bindToolShotPreview(img)")
        block = self.js[start:start + 1200]
        self.assertIn('AIA.openImageLightbox', block)
        self.assertIn("chat-tool-shot-clickable", block)

    def test_missing_aia_degrades_without_breaking_the_card(self) -> None:
        """预览是附加能力：拿不到 `AIA` 就不该把工具卡弄坏。"""
        start = self.js.index("function bindToolShotPreview(img)")
        block = self.js[start:start + 1200]
        self.assertIn('window.AIA&&typeof AIA.openImageLightbox', block)
        self.assertNotIn("throw", block)


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
