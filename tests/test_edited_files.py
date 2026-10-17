# -*- coding: utf-8 -*-
"""本轮编辑清单在页面内存里拼，不进内核，刷新不回放。"""
from __future__ import annotations

import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


class EditedFilesPageTest(unittest.TestCase):
    def test_list_is_assembled_on_the_live_stream_only(self) -> None:
        ui = (_ROOT / "agent/shell/web_assets/classic/js/agent-ui.js").read_text(encoding="utf-8")
        feat = (_ROOT / "agent/shell/web_assets/classic/js/edited-files.js").read_text(encoding="utf-8")
        css = (_ROOT / "agent/shell/web_assets/classic/css/edited-files.css").read_text(encoding="utf-8")
        main_css = (_ROOT / "agent/shell/web_assets/classic/css/agent-ui.css").read_text(encoding="utf-8")
        bundle = (_ROOT / "agent/shell/ui_bundle.py").read_text(encoding="utf-8")
        self.assertIn("function noteLiveEdit(", feat)
        self.assertIn("function finishLiveEdits(", feat)
        self.assertIn("function clearLiveEdits(", feat)
        self.assertIn("editedHold", feat)
        self.assertIn("个文件已更改", feat)
        self.assertIn("edited-files-review", feat)
        self.assertIn('name.indexOf("file_ops")', feat)
        self.assertIn('name.indexOf("delete_file")', feat)
        self.assertIn("grouped[path].push", feat)
        self.assertNotIn("last[path]", feat)
        self.assertIn("edited-sec", css)
        views = (_ROOT / "agent/shell/web_assets/classic/js/chat-tool-views.js").read_text(encoding="utf-8")
        self.assertIn("安全回收目录, 可在此找回原文件", views)
        self.assertIn("function chatToolIsFailed(", views)
        self.assertIn("function chatToolPaintFailText(", views)
        self.assertIn('"<执行失败>"', views)
        self.assertNotIn("按星", views)
        self.assertNotIn("按星", ui)
        self.assertIn('root+" · "+(glob||"*")', views)
        self.assertIn("查看报文", views)
        self.assertIn("chat-tool-custom-view", views)
        self.assertIn("chatToolShowsRaw", views)
        self.assertIn("function chatToolPrettyJson(", views)
        self.assertIn("function chatToolFailPreview(", views)
        self.assertIn("chatToolPayloadUseful", views)
        self.assertIn('preview:String(it.preview||"")', ui)
        self.assertIn("chatToolFailPreview", ui)
        inbound = (_ROOT / "agent/shell/classic_adapter/inbound.py").read_text(encoding="utf-8")
        self.assertIn('{"data": {"ok": False, "error"', inbound)
        tool_css = (_ROOT / "agent/shell/web_assets/classic/css/chat-tool-views.css").read_text(encoding="utf-8")
        self.assertIn(".chat-tool-custom-view{max-height:400px;overflow:auto}", tool_css)
        self.assertIn(".chat-tool-fail{", tool_css)
        self.assertIn(".chat-tool-raw .chat-tool-pane{max-height:400px;overflow:auto}", tool_css)
        self.assertNotIn(".chat-tool-packet-body", tool_css)
        self.assertIn('chatToolName(script)==="glob_files"', views)
        self.assertIn('chatToolName(script)==="delete_file"', views)
        self.assertIn('main:"复制"', ui)
        self.assertIn('main:"移动"', ui)
        self.assertNotIn("function noteLiveEdit(", ui)
        self.assertNotIn("function showEditedFiles(", ui)
        self.assertNotIn(".edited-files{", main_css)
        self.assertIn("noteLiveEdit(ev,_ctxTab)", ui)
        self.assertIn("finishLiveEdits(_ctxTab)", ui)
        self.assertIn("clearLiveEdits(findConversationTab(sendCid))", ui)
        self.assertIn("editedHold", ui)
        self.assertIn(".edited-files-head", css)
        self.assertIn(".edited-files .chat-tool-chev{display:none}", css)
        self.assertIn(".edited-files .chat-diff-cap{display:none}", css)
        self.assertIn('html[data-ui-theme="light"] .edited-files', css)
        self.assertIn("edited-files.js", bundle)
        self.assertIn("edited-files.css", bundle)
        self.assertNotIn('ev.type==="edited_files"', ui)
        history = ui.split("function renderHistoryToolItem(", 1)[1].split("function ", 1)[0]
        self.assertNotIn("noteLiveEdit", history)
        self.assertNotIn("finishLiveEdits", history)
        self.assertFalse((_ROOT / "agent/core/edited_files.py").is_file())
        from agent.shell.ui_bundle import build_inline_css, build_inline_js

        self.assertIn("function showEditedFiles(", build_inline_js())
        self.assertIn(".edited-files{", build_inline_css())
