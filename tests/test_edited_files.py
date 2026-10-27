# -*- coding: utf-8 -*-
"""本回合编辑清单：会话页内存拼装，不进内核，刷新不回放。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.shell.web.ui_bundle import read_ui_js  # noqa: E402


class EditedFilesPageTest(unittest.TestCase):
    def test_list_is_assembled_on_the_live_stream_only(self) -> None:
        feat = (_ROOT / "agent/shell/web/web_assets/classic/js/edited-files.js").read_text(
            encoding="utf-8"
        )
        ui = read_ui_js()
        bundle = (_ROOT / "agent/shell/web/ui_bundle.py").read_text(encoding="utf-8")
        from agent.shell.web.ui_bundle import build_inline_css, build_inline_js

        self.assertIn("function noteLiveEdit(", feat)
        self.assertIn("function finishLiveEdits(", feat)
        self.assertIn("function clearLiveEdits(", feat)
        self.assertIn("grouped[path].push", feat)
        self.assertNotIn("function noteLiveEdit(", ui)
        self.assertIn("noteLiveEdit(ev,_ctxTab)", ui)
        self.assertIn("finishLiveEdits(_ctxTab)", ui)
        self.assertIn("clearLiveEdits(findConversationTab(sendCid))", ui)
        history = ui.split("function renderHistoryToolItem(", 1)[1].split("function ", 1)[0]
        self.assertNotIn("noteLiveEdit", history)
        self.assertNotIn("finishLiveEdits", history)
        self.assertFalse((_ROOT / "agent/core/edited_files.py").is_file())
        self.assertIn("edited-files.js", bundle)
        self.assertIn("file-icons.js", bundle)
        self.assertIn("aiAgentFileIcons", build_inline_js())
        self.assertIn(".file-type-ico{", build_inline_css())
        self.assertNotIn('ev.type==="edited_files"', ui)


if __name__ == "__main__":
    unittest.main()
