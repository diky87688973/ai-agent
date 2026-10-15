# -*- coding: utf-8 -*-
"""web-ui-config.ini：对话区工具条目与步骤面板的展示开关。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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
        html = (ROOT / "agent/shell/web_assets/classic/agent-ui.html").read_text(encoding="utf-8")
        css = (ROOT / "agent/shell/web_assets/classic/css/agent-ui.css").read_text(encoding="utf-8")
        tool_css = (ROOT / "agent/shell/web_assets/classic/css/chat-tool-views.css").read_text(encoding="utf-8")
        js = (ROOT / "agent/shell/web_assets/classic/js/agent-ui.js").read_text(encoding="utf-8")
        tool_js = (ROOT / "agent/shell/web_assets/classic/js/chat-tool-views.js").read_text(encoding="utf-8")
        bundle = (ROOT / "agent/shell/ui_bundle.py").read_text(encoding="utf-8")
        web = (ROOT / "agent/shell/web.py").read_text(encoding="utf-8")
        self.assertIn("{{WEB_UI_JSON}}", html)
        self.assertIn('data-tool-steps', html)
        self.assertIn('html[data-tool-steps="off"] #tabSteps', css)
        self.assertIn('html[data-tool-steps="off"] #paneSteps', css)
        self.assertNotIn('html[data-tool-steps="off"] #classicSidePane', css)
        self.assertIn('data-side-empty', html)
        self.assertIn('html[data-side-empty] #classicSidePane', css)
        self.assertIn("function countOpenSideTabs()", js)
        self.assertIn("function syncClassicSide()", js)
        self.assertIn("function filePathFromHref(", js)
        self.assertIn("function showToolSteps()", js)
        self.assertIn('return {main:"网页",fname:url}', js)
        self.assertIn("function chatToolWasCanceled(", tool_js)
        self.assertIn("function chatToolSyncStatusTitle(", tool_js)
        self.assertIn('else if(ev.user_confirm_required||ev.approval_required)o.chatToolRow.classList.add("is-running")', tool_js)
        self.assertIn('row._title.title=label', tool_js)
        self.assertIn("openUserConfirmModalFromToolEnd(ev, o.chatToolRow)", js)
        self.assertIn("function openApprovalModalFromToolEnd(", js)
        self.assertIn('return {main:"审批",fname:d||"（无描述）"}', js)
        self.assertIn('reject.textContent="驳回"', js)
        self.assertIn('agree.textContent="同意"', js)
        self.assertIn("chatThinkPaintAt<300", tool_js.replace(" ", ""))
        self.assertIn("function chatThinkElapsedLabel(", tool_js)
        self.assertIn('return "用时 "+total+" 秒"', tool_js)
        self.assertIn('return "用时 "+h+" 小时 "+m+" 分 "+s+" 秒"', tool_js)
        self.assertIn("function sealChatThinkElapsed(", tool_js)
        self.assertIn("is-canceled", tool_css)
        self.assertIn("chat-tool-marquee", tool_css)
        self.assertNotIn("function mountChatToolItem(", js)
        self.assertIn("function mountChatToolItem(", tool_js)
        self.assertIn("function registerChatToolView(", tool_js)
        self.assertIn("chatToolViewPreview", tool_js)
        self.assertIn("chatToolExpandPaths", tool_js)
        self.assertIn('chatToolName(script)==="read_image"', tool_js)
        self.assertIn('chatToolName(script)==="read_file"', tool_js)
        self.assertIn("function chatReadFileContent(", tool_js)
        self.assertIn("尺寸: ", tool_js)
        self.assertIn("地址: ", tool_js)
        self.assertIn('n==="run_command"||n==="python_inline"', tool_js)
        self.assertIn('chatToolName(script)==="skill_manage"', tool_js)
        self.assertIn("function chatReviewPath(", tool_js)
        self.assertIn("加载技能", tool_js)
        self.assertIn("chat-tool-md", tool_js)
        self.assertIn("renderMarkdown", tool_js)
        self.assertIn('chatToolName(script)==="file_undo"', tool_js)
        self.assertIn("function chatVersionStamp(", tool_js)
        self.assertIn("function chatPaintDiffPane(", tool_js)
        self.assertIn('path+" to "+stamp', tool_js)
        self.assertIn(".chat-tool-row{", tool_css.replace(" ", ""))
        self.assertIn("max-width:400px", tool_css)
        self.assertIn("max-height:400px", tool_css)
        self.assertIn("chat-tool-views.css", bundle)
        self.assertIn("chat-tool-views.js", bundle)
        self.assertIn("{{WEB_UI_JSON}}", web)
        self.assertIn("get_web_ui", web)


if __name__ == "__main__":
    unittest.main()
