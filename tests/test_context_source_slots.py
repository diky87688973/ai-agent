# -*- coding: utf-8 -*-
"""上下文注入源的 slot 替换与回退测试。"""
from __future__ import annotations

import unittest

from agent.capabilities.slot_registry import SlotRegistry
from agent.mechanisms.context.sources import (
    ASSEMBLY_PATH,
    ContextSources,
    PluginSegments,
    SourceMeta,
)


class ContextSourceSlotTest(unittest.TestCase):
    def setUp(self) -> None:
        self.path = "app/backend/context/sources/kb/source-1"
        self.sources = ContextSources(SlotRegistry())
        self.first = self.sources.add(
            lambda cid: ["old"],
            SourceMeta(key="kb", label="KB"),
            path=self.path,
            owner="kb",
        )

    def test_replace_and_restore(self) -> None:
        binding = self.sources.add(
            lambda cid: ["new"],
            SourceMeta(key="kb", label="KB"),
            path=self.path,
            owner="override",
            replace=True,
        )
        self.assertEqual(self.sources.collect_segments("c").items[0][2], "new")
        binding()
        self.assertEqual(self.sources.collect_segments("c").items[0][2], "old")
        self.first()

    def test_duplicate_without_replace_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.sources.add(
                lambda cid: ["duplicate"],
                SourceMeta(key="kb", label="KB"),
                path=self.path,
                owner="other",
            )

    def test_source_can_be_added_again_after_dispose(self) -> None:
        self.first()
        self.sources.add(
            lambda cid: ["again"],
            SourceMeta(key="kb", label="KB"),
            path=self.path,
            owner="kb",
        )
        self.assertEqual(self.sources.collect_segments("c").items[0][2], "again")

    def test_replace_context_assembly(self) -> None:
        binding = self.sources._slots.bind(
            ASSEMBLY_PATH,
            lambda cid: PluginSegments(items=(("x", "X", "new"),), counts=(1,)),
            owner="plugin",
            mode="replace",
        )
        self.assertEqual(self.sources.collect_segments("c").items[0][2], "new")
        binding.dispose()
        self.assertEqual(self.sources.collect_segments("c").items[0][2], "old")

    def test_replace_does_not_duplicate_backend_path(self) -> None:
        """同路径 replace：注册表里只留一条，且内容是新的。"""
        sources = ContextSources(SlotRegistry())
        first = sources.add(
            lambda cid: ["old"], SourceMeta(key="kb", label="KB"),
            path=self.path, owner="kb")
        second = sources.add(
            lambda cid: ["new"], SourceMeta(key="kb", label="KB"),
            path=self.path, owner="override", replace=True)
        items = sources.collect_segments("c").items
        self.assertEqual(len(items), 1, msg="同路径 replace 不得重复注册")
        self.assertEqual(items[0][2], "new")
        second()
        self.assertEqual(sources.collect_segments("c").items[0][2], "old")
        first()


if __name__ == "__main__":
    unittest.main()
