# -*- coding: utf-8 -*-
"""音色维度的契约：拼接顺序固定、非法组合一律拒绝、预设必须能自洽。"""
from __future__ import annotations

import re
import unittest

from plugins.tts import schema


class ComposeTest(unittest.TestCase):
    def test_compose_structure(self) -> None:
        """指令形状：must be…definitely not…，且五个维度都在。"""
        dims = {"age": "轻熟", "timbre": "冷冽", "persona": "冷艳强势",
                "pace": "适中", "emotion": "克制"}
        text = schema.compose(dims)
        self.assertTrue(text.startswith("must be "))
        self.assertIn("definitely not", text)
        for word in ("late twenties", "low, cold, hard", "commanding forceful", "normal pace"):
            with self.subTest(word=word):
                self.assertIn(word, text)

    def test_instruction_is_english(self) -> None:
        """英文对音色的控制明显强于中文，指令不许退回中文。"""
        for preset in schema.PRESETS:
            with self.subTest(preset=preset["id"]):
                text = schema.compose(preset["dims"])
                self.assertIsNone(re.search(r"[\u4e00-\u9fff]", text))

    def test_compose_keeps_under_length_limit(self) -> None:
        """指令不能无限制堆砌；当前最长（御姐类）约 321 字符，上限抬到 340。"""
        longest = 0
        for preset in schema.PRESETS:
            text = schema.compose(preset["dims"])
            longest = max(longest, len(text))
            self.assertLess(len(text), 340, preset["id"])
        self.assertGreater(longest, 200, "指令短得异常，可能漏了音高或否定段")

    def test_same_dims_always_same_text(self) -> None:
        dims = {"age": "少女", "timbre": "清亮", "persona": "甜美灵动",
                "pace": "轻快", "emotion": "愉悦"}
        self.assertEqual(schema.compose(dims), schema.compose(dict(dims)))

    def test_missing_dimension_rejected(self) -> None:
        with self.assertRaises(ValueError):
            schema.compose({"age": "少女", "timbre": "清亮"})

    def test_unknown_value_rejected(self) -> None:
        dims = {"age": "老人", "timbre": "清亮", "persona": "甜美灵动",
                "pace": "轻快", "emotion": "愉悦"}
        with self.assertRaises(ValueError):
            schema.compose(dims)

    def test_blank_value_rejected(self) -> None:
        dims = {"age": "  ", "timbre": "清亮", "persona": "甜美灵动",
                "pace": "轻快", "emotion": "愉悦"}
        with self.assertRaises(ValueError):
            schema.compose(dims)


class PresetTest(unittest.TestCase):
    def test_every_preset_composes(self) -> None:
        self.assertTrue(schema.PRESETS)
        for preset in schema.PRESETS:
            with self.subTest(preset=preset["id"]):
                normalized = schema.normalize(preset["dims"])
                self.assertEqual(len(normalized), len(schema.DIMENSION_ORDER))
                self.assertTrue(schema.compose(preset["dims"]))

    def test_preset_ids_unique(self) -> None:
        ids = [str(preset["id"]) for preset in schema.PRESETS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_preset_ids_are_valid_voice_ids(self) -> None:
        from plugins.tts.voice_lab import _VOICE_ID_RE

        for preset in schema.PRESETS:
            with self.subTest(preset=preset["id"]):
                self.assertRegex(str(preset["id"]), _VOICE_ID_RE)


class OptionsTest(unittest.TestCase):
    def test_payload_matches_dimensions(self) -> None:
        payload = schema.options_payload()
        self.assertEqual(payload["order"], list(schema.DIMENSION_ORDER))
        self.assertEqual(len(payload["dimensions"]), 5)
        self.assertTrue(str(payload["sample_text"]))

    def test_each_dimension_has_options(self) -> None:
        for dim in schema.DIMENSIONS:
            with self.subTest(dim=dim["key"]):
                self.assertTrue(dim["options"], "维度不能没有选项")
                for opt in dim["options"]:
                    self.assertTrue(str(opt["text"]).strip())


class DescribeTest(unittest.TestCase):
    def test_describe_is_chinese_only(self) -> None:
        """给界面看的描述必须是中文，不能泄露英文指令。"""
        for preset in schema.PRESETS:
            with self.subTest(preset=preset["id"]):
                text = schema.describe(preset["dims"])
                self.assertIsNotNone(re.search(r"[\u4e00-\u9fff]", text))
                self.assertIsNone(re.search(r"[A-Za-z]{3,}", text))

    def test_describe_covers_all_dimensions(self) -> None:
        dims = {"age": "少女", "timbre": "气声", "persona": "甜美灵动",
                "pace": "舒缓", "emotion": "温和"}
        parts = schema.describe(dims).split("，")
        self.assertEqual(len(parts), len(schema.DIMENSION_ORDER))


class VoiceIdTest(unittest.TestCase):
    def test_regex_accepts_and_rejects(self) -> None:
        from plugins.tts.voice_lab import _VOICE_ID_RE

        for good in ("fanyin", "qingling", "a1", "my-voice", "my_voice2"):
            with self.subTest(good=good):
                self.assertTrue(_VOICE_ID_RE.match(good))
        for bad in ("", "Fanyin", "1voice", "my voice", "音色", "a" * 65):
            with self.subTest(bad=bad):
                self.assertIsNone(_VOICE_ID_RE.match(bad))


if __name__ == "__main__":
    unittest.main()
