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
from agent.config import DEFAULT_CONTEXT_WINDOW  # noqa: E402


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


class EntryWindowTest(unittest.TestCase):
    def test_entry_exposes_the_window(self) -> None:
        entry = ModelEntry.from_options(
            id="a", provider="openai", options={"context_window": "64000"})
        self.assertEqual(entry.context_window, 64000)

    def test_bad_metadata_is_zero_not_an_exception(self) -> None:
        entry = ModelEntry.from_options(
            id="a", provider="openai", options={"context_window": "many"})
        self.assertEqual(entry.context_window, 0)


if __name__ == "__main__":
    unittest.main()
