# -*- coding: utf-8 -*-
"""插件开关的依赖级联：关掉被依赖的插件时，依赖方必须一起关。

否则依赖方装配失败 → 整个开关回滚 → 表现为「插件关不掉、只报请求失败」。
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from agent.shell.plugin_settings import _dependents, set_plugin_enabled

ROOT = Path(__file__).resolve().parents[1]
PLUGINS_DIR = ROOT / "plugins"
MANIFEST = ROOT / "plugins.ini"


class DependentsTest(unittest.TestCase):
    def test_tts_is_required_by_ai_cosplay(self) -> None:
        self.assertIn("ai_cosplay", _dependents("tts", PLUGINS_DIR))

    def test_leaf_plugin_has_no_dependents(self) -> None:
        self.assertEqual(_dependents("ai_cosplay", PLUGINS_DIR), [])

    def test_unknown_plugin_has_no_dependents(self) -> None:
        self.assertEqual(_dependents("no_such_plugin", PLUGINS_DIR), [])


class DisableCascadeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.manifest = Path(self._tmp.name) / "plugins.ini"
        shutil.copyfile(MANIFEST, self.manifest)
        self.tts_before = self._enabled("tts")
        self.cosplay_before = self._enabled("ai_cosplay")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _enabled(self, plugin: str) -> str:
        lines = self.manifest.read_text(encoding="utf-8").splitlines()
        section = f"[plugin:{plugin}]"
        for index, line in enumerate(lines):
            if line.strip() == section:
                for follow in lines[index + 1:]:
                    if follow.strip().startswith("["):
                        break
                    if follow.strip().startswith("enabled"):
                        return follow.split("=", 1)[1].strip()
        return ""

    def test_disabling_tts_also_disables_ai_cosplay(self) -> None:
        result = set_plugin_enabled("tts", False, app=None,
                                    plugins_path=self.manifest,
                                    plugins_dir=PLUGINS_DIR)
        self.assertTrue(result["ok"])
        self.assertEqual(result["disabled"], ["ai_cosplay"])
        self.assertEqual(self._enabled("tts"), "0")
        self.assertEqual(self._enabled("ai_cosplay"), "0")

    def test_disabling_leaf_keeps_tts_untouched(self) -> None:
        result = set_plugin_enabled("ai_cosplay", False, app=None,
                                    plugins_path=self.manifest,
                                    plugins_dir=PLUGINS_DIR)
        self.assertTrue(result["ok"])
        self.assertEqual(result["disabled"], [])
        self.assertEqual(self._enabled("ai_cosplay"), "0")
        self.assertEqual(self._enabled("tts"), self.tts_before)

    def test_enable_has_no_cascade(self) -> None:
        result = set_plugin_enabled("tts", True, app=None,
                                    plugins_path=self.manifest,
                                    plugins_dir=PLUGINS_DIR)
        self.assertTrue(result["ok"])
        self.assertEqual(result["disabled"], [])
        self.assertEqual(self._enabled("ai_cosplay"), self.cosplay_before)


if __name__ == "__main__":
    unittest.main()
