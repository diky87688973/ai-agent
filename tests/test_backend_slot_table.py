# -*- coding: utf-8 -*-
"""后端扩展点协议表：唯一权威，且与宿主启动后的注册结果逐条相同。

这张表原先有两份（`slot_tree.json` 的 `backend_slots` 段与代码常量），
旧数据文件删除后本用例把「集合不变」钉住：任何一条被增删改，这里就红。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.capabilities.backend_paths import (  # noqa: E402
    BASE_BACKEND_SLOTS,
    seed_backend_slots,
)
from agent.capabilities.path_registry import PathRegistry  # noqa: E402

EXPECTED = (
    "backend/tools",
    "backend/tools/<tool>",
    "backend/tools/subagents/visibility",
    "backend/tools/pipeline/pre-gates",
    "backend/tools/pipeline/pre-gates/<plugin>",
    "backend/tools/pipeline/post-observers",
    "backend/tools/pipeline/post-observers/<plugin>",
    "backend/context/sources",
    "backend/context/sources/<plugin>",
    "backend/context/assembly-hooks",
    "backend/context/assembly-hooks/<plugin>",
    "backend/context/usage-segments",
    "backend/context/usage-segments/<plugin>",
    "backend/prompt/sections",
    "backend/prompt/sections/<section>",
    "backend/prompt/mode-tails",
    "backend/events/subscriptions",
    "backend/events/subscriptions/<event>",
    "backend/http/routes",
    "backend/models/catalog",
    "backend/models/providers",
    "backend/models/routing",
    "backend/runtime",
)


class BackendSlotTableTest(unittest.TestCase):
    """协议表与登记结果必须逐条相等。"""

    def test_table_has_exactly_the_expected_paths(self) -> None:
        self.assertEqual(len(BASE_BACKEND_SLOTS), len(EXPECTED))
        self.assertEqual(tuple(row["path"] for row in BASE_BACKEND_SLOTS), EXPECTED)

    def test_seeded_registry_matches_table_one_to_one(self) -> None:
        registry = PathRegistry()
        seed_backend_slots(registry)
        self.assertEqual(len(registry.slots), len(EXPECTED))
        self.assertEqual(sorted(registry.slots), sorted(
            "app/" + path for path in EXPECTED))

    def test_child_policy_survives_seeding(self) -> None:
        registry = PathRegistry()
        seed_backend_slots(registry)
        tool = registry.slots["app/backend/tools/<tool>"]
        self.assertEqual(tool.children, "fixed")
        self.assertEqual(tool.fixed_children, ("executor", "post-write"))
        sources = registry.slots["app/backend/context/sources"]
        self.assertEqual(sources.children, "keyed")

    def test_old_data_file_is_gone(self) -> None:
        """旧数据文件删除后不得回流：协议表是唯一权威。"""
        self.assertFalse((_ROOT / "agent" / "boot" / "slot_tree.json").exists())


if __name__ == "__main__":
    unittest.main()
