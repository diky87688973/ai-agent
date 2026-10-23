# -*- coding: utf-8 -*-
"""配置：冻结程序的数据根落到用户目录。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent import config  # noqa: E402


class FrozenDataRootTest(unittest.TestCase):
    def test_frozen_uses_user_data_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(config, "is_frozen", return_value=True), \
                    mock.patch.object(config, "user_data_root", return_value=Path(tmp)), \
                    mock.patch.dict(os.environ, {"AI_AGENT_DATA_ROOT": ""}):
                self.assertEqual(config.default_data_root(), Path(tmp))

    def test_env_override_wins_over_frozen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(config, "is_frozen", return_value=True), \
                    mock.patch.dict(os.environ, {"AI_AGENT_DATA_ROOT": tmp}):
                self.assertEqual(config.default_data_root(), Path(tmp))

    def test_windows_user_data_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(config.os, "name", "nt"), \
                    mock.patch.dict(os.environ, {"LOCALAPPDATA": tmp}):
                self.assertEqual(config.user_data_root(), Path(tmp) / "ai-agent")


if __name__ == "__main__":
    unittest.main()
