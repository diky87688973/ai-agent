# -*- coding: utf-8 -*-
"""音色工作台写回配置：旧配置缺 voice_id 键时补一行，而不是拒绝。"""
from __future__ import annotations

import unittest

from plugins.tts.voice_lab import _append_config_key


class AppendConfigKeyTest(unittest.TestCase):
    def test_missing_key_is_appended_at_section_end(self) -> None:
        text = "[config]\nengine = breeze\nmodel_dir = D:\\models\n"
        out = _append_config_key(text, "voice_id", "ruanmeng")
        self.assertIn("voice_id = ruanmeng", out)
        self.assertLess(out.index("model_dir"), out.index("voice_id"))

    def test_existing_keys_survive(self) -> None:
        text = "[config]\nengine = breeze\n"
        out = _append_config_key(text, "voice_id", "cixiang")
        self.assertIn("engine = breeze", out)
        self.assertEqual(out.count("="), 2)

    def test_missing_section_is_created(self) -> None:
        out = _append_config_key("", "voice_id", "fanyin")
        self.assertEqual(out, "[config]\nvoice_id = fanyin\n")

    def test_key_goes_before_next_section(self) -> None:
        text = "[config]\nengine = breeze\n\n[extra]\nfoo = 1\n"
        out = _append_config_key(text, "voice_id", "huopo")
        self.assertLess(out.index("voice_id"), out.index("[extra]"))


if __name__ == "__main__":
    unittest.main()
