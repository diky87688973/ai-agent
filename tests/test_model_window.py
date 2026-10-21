# -*- coding: utf-8 -*-
"""上下文窗口属于模型：配置读取、目录条目与按会话解析。

窗口是模型条目的物理上限（占用率的分母），压缩阈值是预算，两者不能混用：
换模型就该换分母。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.capabilities.model_catalog import ModelCatalog, ModelEntry  # noqa: E402
from agent.config import (  # noqa: E402
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_SUMMARY_TOKEN_FALLBACK,
    compression_threshold,
)


class _AppWindowTest(unittest.TestCase):
    def _app(self, entries=(), default_model="a"):
        from agent.app import App
        from agent.core.context import (
            SERVICE_LIVE_STATE,
            SERVICE_MODEL_CATALOG,
            AppContext,
        )
        from agent.mechanisms.live_state import LiveState

        context = AppContext()
        catalog = ModelCatalog()
        if entries:
            catalog.set_source("test", list(entries))
            context.register(SERVICE_MODEL_CATALOG, catalog)
        context.register(SERVICE_LIVE_STATE, LiveState(default_model=default_model))
        return App(context)

    def test_catalog_entry_window_wins(self) -> None:
        app = self._app(
            entries=[
                ModelEntry.from_options(
                    id="a", provider="openai", options={"context_window": 128000}),
                ModelEntry.from_options(
                    id="b", provider="openai", options={"context_window": 1000000}),
            ],
            default_model="a",
        )
        self.assertEqual(app.context_window_for("cid"), 128000)
        app.live_state.set_model("cid", "b")
        self.assertEqual(app.context_window_for("cid"), 1000000)

    def test_entry_without_window_uses_the_shared_default(self) -> None:
        app = self._app(entries=[
            ModelEntry.from_options(id="a", provider="openai"),
        ])
        self.assertEqual(app.context_window_for("cid"), DEFAULT_CONTEXT_WINDOW)

    def test_stale_model_converges_to_the_default_window(self) -> None:
        """会话还拿着已删除的模型 id：先收敛回默认，窗口跟着默认走。"""
        app = self._app(entries=[
            ModelEntry.from_options(id="a", provider="openai",
                                    options={"context_window": 128000}),
        ], default_model="gone")
        self.assertEqual(app.context_window_for("cid"), 128000)


    def test_compression_percent_comes_from_the_current_model(self) -> None:
        app = self._app(entries=[
            ModelEntry.from_options(
                id="a", provider="openai",
                options={"context_window": 128000, "compression_percent": 80}),
        ])
        self.assertEqual(app.compression_percent_for("cid"), 80)

    def test_compression_percent_defaults_to_70(self) -> None:
        app = self._app(entries=[
            ModelEntry.from_options(id="a", provider="openai",
                                    options={"context_window": 128000}),
        ])
        self.assertEqual(app.compression_percent_for("cid"), 70)


class CompressionThresholdTest(unittest.TestCase):
    def test_window_percent(self) -> None:
        self.assertEqual(compression_threshold(1_000_000, 70), 700_000)
        self.assertEqual(compression_threshold(128_000, 70), 89_600)
        self.assertEqual(compression_threshold(128_000, 90), 115_200)
        self.assertEqual(compression_threshold(128_000, 10), 12_800)

    def test_missing_window_uses_fallback(self) -> None:
        self.assertEqual(compression_threshold(0, 70), DEFAULT_SUMMARY_TOKEN_FALLBACK)
        self.assertEqual(compression_threshold(0, 70, 32000), 32000)

    def test_bad_percent_uses_70(self) -> None:
        self.assertEqual(compression_threshold(100_000, 0), 70_000)
        self.assertEqual(compression_threshold(100_000, 95), 70_000)


class EntryWindowTest(unittest.TestCase):
    def test_entry_exposes_the_window(self) -> None:
        entry = ModelEntry.from_options(
            id="a", provider="openai", options={"context_window": "64000"})
        self.assertEqual(entry.context_window, 64000)

    def test_bad_metadata_is_zero_not_an_exception(self) -> None:
        entry = ModelEntry.from_options(
            id="a", provider="openai", options={"context_window": "many"})
        self.assertEqual(entry.context_window, 0)

    def test_compression_percent_defaults_and_clamps(self) -> None:
        entry = ModelEntry.from_options(id="a", provider="openai")
        self.assertEqual(entry.compression_percent, 70)
        bad = ModelEntry.from_options(
            id="a", provider="openai", options={"compression_percent": 95})
        self.assertEqual(bad.compression_percent, 70)


if __name__ == "__main__":
    unittest.main()
