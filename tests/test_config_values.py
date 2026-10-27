# -*- coding: utf-8 -*-
"""配置读取的数值回退与压缩阈值边界。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.config import compression_threshold, get_backup_retention_days, get_context, get_update


class ConfigValueFallbackTest(unittest.TestCase):
    def _ini(self, text: str) -> Path:
        raw = tempfile.NamedTemporaryFile("w", suffix=".ini", delete=False,
                                          encoding="utf-8")
        raw.write(text)
        raw.close()
        self.addCleanup(Path(raw.name).unlink)
        return Path(raw.name)

    def test_compression_threshold_coerces_bool_and_strings(self) -> None:
        self.assertEqual(compression_threshold(True), 1)
        self.assertEqual(compression_threshold("1000", "50"), 500)
        self.assertEqual(compression_threshold("bad", "bad"), 64000)

    def test_bad_numeric_values_fall_back_to_defaults(self) -> None:
        path = self._ini("[update]\ncheck_interval_minutes = nope\n"
                         "[agent]\nbackup_retention_days = nope\n"
                         "[context]\nfull_user_rounds = nope\n")
        self.assertEqual(get_update(path)["check_interval_minutes"], 30)
        self.assertEqual(get_backup_retention_days(path), 7)
        self.assertEqual(get_context(path)["full_user_rounds"], 5)

