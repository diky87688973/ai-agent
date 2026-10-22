# -*- coding: utf-8 -*-
"""JS 事件绑定审计：静态扫描只列候选，不自动判失败。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.scan_js_events import render, scan_text  # noqa: E402


class ScanJsEventsTest(unittest.TestCase):
    def test_collects_add_listener_property_and_delegation(self) -> None:
        text = (
            'document.addEventListener("click", handle);\n'
            'card.addEventListener("click", handle);\n'
            'button.onclick = handle;\n'
        )
        bindings = scan_text(text, "fixture.js")
        self.assertEqual([b.kind for b in bindings],
                         ["addEventListener", "addEventListener", "property"])
        self.assertTrue(bindings[0].delegated)
        self.assertFalse(bindings[1].delegated)
        self.assertEqual(bindings[1].event, "click")
        self.assertEqual(bindings[2].event, "click")

    def test_collects_inline_html_and_renders_report(self) -> None:
        bindings = scan_text('<button onclick="save()">保存</button>', "fixture.html")
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0].kind, "inline-html")
        text = render(bindings, 1)
        self.assertIn("JS 事件绑定审计", text)
        self.assertIn("inline-html", text)


if __name__ == "__main__":
    unittest.main()
