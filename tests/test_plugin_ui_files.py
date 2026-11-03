# -*- coding: utf-8 -*-
"""插件 UI 声明的命名与顶层 kind 约定。"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "plugins"
KINDS = {"ui", "settings", "ui-paths"}


class PluginUiFileTest(unittest.TestCase):
    def test_every_plugin_has_one_ui_fragment(self) -> None:
        for folder in PLUGINS.iterdir():
            if not (folder / "plugin.py").is_file():
                continue
            path = folder / "plugin-ui.json"
            self.assertTrue(path.is_file(), msg=f"缺少 plugin-ui.json：{folder.name}")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data.get("version"), 1, msg=folder.name)
            self.assertIn(data.get("kind"), KINDS, msg=folder.name)

    def test_no_stale_ui_filenames(self) -> None:
        for pattern in ("tree.json", "*_tree.json", "ui_paths.json"):
            self.assertEqual(list(PLUGINS.rglob(pattern)), [], msg=pattern)


if __name__ == "__main__":
    unittest.main()
