# -*- coding: utf-8 -*-
"""AI说话文本规范、切分、合成净化与配置测试。"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PLUGIN = _ROOT / "plugins" / "ai_speak"


def _load(name: str, filename: str):
    path = _PLUGIN / filename
    spec = importlib.util.spec_from_file_location(name, str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_TEXT = _load("ai_speak_text_test", "text.py")
_CONFIG = _load("ai_speak_config_test", "config.py")


class SplitTest(unittest.TestCase):
    def test_chinese_and_english_sentences(self) -> None:
        cases = [
            ("主子，文件写好了，您看一眼？", 128, 1),
            ("第一句。第二句！", 128, 1),
            ("他说“好。”", 128, 1),
            ('He said "hi."', 128, 1),
            ("Wait... what?", 128, 1),
            ("3.14。", 128, 1),
            ("10:30。", 128, 1),
            ("2026-10-19。", 128, 1),
            ("5+3。", 128, 1),
            ("-5。", 128, 1),
            ("进度 10%。", 128, 1),
        ]
        for msg, limit, count in cases:
            with self.subTest(msg=msg):
                self.assertEqual(len(_TEXT.split_message(msg, limit)), count)

    def test_packing_respects_limit(self) -> None:
        self.assertEqual(
            _TEXT.split_message("一。二。三。", 4),
            ("一。二。", "三。"),
        )
        self.assertEqual(
            _TEXT.split_message("Hello. World!", 8),
            ("Hello.", "World!"),
        )
        self.assertEqual(
            _TEXT.split_message("Hello. World!", 20),
            ("Hello. World!",),
        )

    def test_configured_limit_is_not_capped(self) -> None:
        msg = "一" * 200 + "。" + "二" * 200 + "。"
        self.assertEqual(len(_TEXT.split_message(msg, 300)), 2)
        self.assertEqual(len(_TEXT.split_message(msg, 1000)), 1)

    def test_message_limit(self) -> None:
        valid = "啊" * 511 + "。"
        self.assertEqual(len(_TEXT.split_message(valid, 1000)), 1)
        with self.assertRaises(_TEXT.MessageValidationError) as ctx:
            _TEXT.split_message("啊" * 512 + "。", 1000)
        self.assertEqual(ctx.exception.code, "too_long")

    def test_single_piece_over_limit(self) -> None:
        with self.assertRaises(_TEXT.MessageValidationError) as ctx:
            _TEXT.split_message("a" * 128 + "。", 128)
        self.assertEqual(ctx.exception.code, "segment_too_long")
        self.assertIn("129", str(ctx.exception))

    def test_quoted_end_is_a_boundary(self) -> None:
        self.assertEqual(
            _TEXT.split_message('He said "hi."', 128),
            ('He said "hi."',),
        )
        self.assertEqual(
            _TEXT.split_message("他说“好。”", 128),
            ("他说“好。”",),
        )

    def test_numeric_separators_are_not_boundaries(self) -> None:
        for msg in ("3.14。", "1,000。", "10:30。"):
            with self.subTest(msg=msg):
                self.assertEqual(_TEXT.split_message(msg, 128), (msg,))


class ValidationTest(unittest.TestCase):
    def assert_code(self, msg: str, code: str) -> None:
        with self.assertRaises(_TEXT.MessageValidationError) as ctx:
            _TEXT.split_message(msg, 128)
        self.assertEqual(ctx.exception.code, code, str(ctx.exception))

    def test_rejects_empty_and_missing_end(self) -> None:
        self.assert_code("", "empty")
        self.assert_code("   ", "empty")
        self.assert_code("abc", "missing_end")
        self.assert_code('"Hello"', "missing_end")

    def test_rejects_forbidden_characters(self) -> None:
        for ch in ("😀", "@", "#", "&", "[", "]", "=", "\\", "\n", "\t", "１"):
            with self.subTest(ch=ch):
                self.assert_code(f"abc{ch}。", "invalid_char")

    def test_rejects_empty_pairs(self) -> None:
        for msg in ("“”。", '"".', "()。", "''。"):
            with self.subTest(msg=msg):
                self.assert_code(msg, "empty_pair")

    def test_rejects_unmatched_pairs(self) -> None:
        self.assert_code("他说“好。", "unmatched_open")
        self.assert_code("他说好。”", "unmatched_close")
        self.assert_code('He said "hi.', "unmatched_open")

    def test_rejects_math_context(self) -> None:
        for msg in ("5+。", "5--3。", "5**3。", "-abc。", "abc-。", "5+3-。",
                    "5/。", "5×。", "5÷。"):
            with self.subTest(msg=msg):
                self.assert_code(msg, "invalid_math")

    def test_rejects_percent_without_number(self) -> None:
        for msg in ("%5。", "abc%。", "abc%5。"):
            with self.subTest(msg=msg):
                self.assert_code(msg, "invalid_percent")

    def test_rejects_leading_boundary(self) -> None:
        for msg in ("。你好。", "，你好。"):
            with self.subTest(msg=msg):
                self.assert_code(msg, "leading_boundary")


class SpeechTextTest(unittest.TestCase):
    def test_quotes_and_apostrophes(self) -> None:
        self.assertEqual(_TEXT.to_speech_text('他说“好。”'), "他说好。")
        self.assertEqual(_TEXT.to_speech_text('He said "hi."'), "He said hi.")
        self.assertEqual(_TEXT.to_speech_text("don't stop."), "don't stop.")

    def test_percent(self) -> None:
        cases = {
            "10%": "百分之十",
            "3.5%": "百分之三点五",
            "100%": "百分之百",
            "1,000%": "百分之一千",
            "0%": "百分之零",
            "10 %": "百分之十",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(_TEXT.to_speech_text(raw), expected)

    def test_math(self) -> None:
        cases = {
            "5+3": "五加三",
            "10-2": "十减二",
            "3*4": "三乘四",
            "10/2": "十除以二",
            "3×4": "三乘四",
            "10÷2": "十除以二",
            "5＋3": "五加三",
            "-5": "负五",
            "100+1": "一百加一",
            "3.5+2": "三点五加二",
            "1,000-2": "一千减二",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(_TEXT.to_speech_text(raw), expected)

    def test_dates_and_identifiers_are_not_math(self) -> None:
        for raw in ("2026-10-19", "2026-10", "well-known", "GPT-4", "10:30", "3.14"):
            with self.subTest(raw=raw):
                self.assertEqual(_TEXT.to_speech_text(raw), raw)

    def test_thousands_separator_removed(self) -> None:
        self.assertEqual(_TEXT.to_speech_text("1,000"), "1000")
        self.assertEqual(_TEXT.to_speech_text("1,000,000"), "1000000")


class ConfigTest(unittest.TestCase):
    def test_missing_file_uses_defaults(self) -> None:
        cfg = _CONFIG.load_config(Path(tempfile.gettempdir()) / "ai_speak_missing.ini")
        self.assertEqual(cfg.engine, "edge")
        self.assertEqual(cfg.voice, "zh-CN-XiaoxiaoNeural")
        self.assertEqual(cfg.max_segment_chars, 128)
        self.assertEqual(cfg.play_interval_ms, 0)
        self.assertFalse(cfg.sync_playback)
        self.assertEqual(cfg.speed, 1.0)
        self.assertEqual(cfg.warnings, ())

    def test_values_and_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plugin-config.ini"
            path.write_text(
                "[config]\nengine = edge\nvoice = v\n"
                "max_segment_chars = 300\nplay_interval_ms = 250\n"
                "sync_playback = on\nspeed = 1.5\n",
                encoding="utf-8",
            )
            cfg = _CONFIG.load_config(path)
            self.assertEqual(cfg.max_segment_chars, 300)
            self.assertEqual(cfg.play_interval_ms, 250)
            self.assertTrue(cfg.sync_playback)
            self.assertEqual(cfg.speed, 1.5)

            path.write_text(
                "[config]\nmax_segment_chars = 0\nplay_interval_ms = -3\n"
                "sync_playback = maybe\nspeed = 9\n",
                encoding="utf-8",
            )
            cfg = _CONFIG.load_config(path)
            self.assertEqual(cfg.max_segment_chars, 128)
            self.assertEqual(cfg.play_interval_ms, 0)
            self.assertFalse(cfg.sync_playback)
            self.assertEqual(cfg.speed, 1.0)
            self.assertEqual(len(cfg.warnings), 4)

    def test_invalid_engine_and_voice_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plugin-config.ini"
            path.write_text("[config]\nengine = console\n", encoding="utf-8")
            with self.assertRaises(_CONFIG.ConfigError):
                _CONFIG.load_config(path)
            path.write_text("[config]\nengine = edge\nvoice = \n", encoding="utf-8")
            with self.assertRaises(_CONFIG.ConfigError):
                _CONFIG.load_config(path)


if __name__ == "__main__":
    unittest.main()
