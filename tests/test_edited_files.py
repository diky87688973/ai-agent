# -*- coding: utf-8 -*-
"""本轮编辑清单在页面内存里拼，不进内核，刷新不回放。"""
from __future__ import annotations

import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


class EditedFilesPageTest(unittest.TestCase):
    def test_list_is_assembled_on_the_live_stream_only(self) -> None:
        ui = (_ROOT / "agent/shell/web_assets/classic/js/agent-ui.js").read_text(encoding="utf-8")
        self.assertIn("function noteLiveEdit(", ui)
        self.assertIn("function finishLiveEdits(", ui)
        self.assertIn("editedHold", ui)
        self.assertNotIn('ev.type==="edited_files"', ui)
        history = ui.split("function renderHistoryToolItem(", 1)[1].split("function ", 1)[0]
        self.assertNotIn("noteLiveEdit", history)
        self.assertNotIn("finishLiveEdits", history)
        self.assertFalse((_ROOT / "agent/core/edited_files.py").is_file())
