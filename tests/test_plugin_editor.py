# -*- coding: utf-8 -*-
"""插件配置保存：未声明的键不阻断保存，原样留在文件里。"""
from __future__ import annotations

import unittest

from agent.shell.plugin_editor import _group_body, merge_fields


def _schema() -> dict:
    return {
        "section": "config",
        "fields": [
            {"key": "tone", "kind": "text", "label": "语气", "default": ""},
            {"key": "speed", "kind": "text", "label": "语速", "default": ""},
        ],
    }


class UndeclaredKeyTest(unittest.TestCase):
    def test_save_keeps_going_when_config_has_legacy_key(self) -> None:
        text = "[config]\n; 语气\ntone = 冷静\n; 旧版本遗留\nengine = edge\n"
        merged, error = merge_fields(text, {"tone": "温婉", "engine": "edge"}, _schema())
        self.assertEqual(error, "")
        self.assertIn("tone = 温婉", merged)

    def test_legacy_key_stays_in_file(self) -> None:
        text = "[config]\ntone = 冷静\nengine = edge\n"
        merged, error = merge_fields(text, {"tone": "温婉"}, _schema())
        self.assertEqual(error, "")
        self.assertIn("engine = edge", merged)

    def test_legacy_key_is_not_written_back_from_form(self) -> None:
        text = "[config]\ntone = 冷静\n"
        merged, error = merge_fields(text, {"tone": "温婉", "engine": "azure"}, _schema())
        self.assertEqual(error, "")
        self.assertNotIn("engine", merged)

    def test_group_save_ignores_legacy_key(self) -> None:
        body, error = _group_body(
            {"id": "g1"}, _schema(), {"tone": "温婉", "engine": "edge"}, [], {})
        self.assertEqual(error, "")
        self.assertEqual(body, ["tone = 温婉"])


if __name__ == "__main__":
    unittest.main()
