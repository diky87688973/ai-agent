# -*- coding: utf-8 -*-
"""UI 路径的 pending、替换和 catalog 测试。"""
from __future__ import annotations

import unittest

from agent.capabilities.ui_registry import UiRegistry


class UiRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = UiRegistry()
        self.registry.add_slot("app/shell/web-ui", kind="container", children="fixed",
                               fixed_children=("nav",))
        self.registry.add_slot("app/shell/web-ui/nav", kind="container", children="fixed",
                               fixed_children=("buttons",))
        self.registry.add_slot("app/shell/web-ui/nav/buttons", kind="container", children="keyed")

    def test_item_replace_and_restore(self) -> None:
        base = self.registry.add_item(
            "app/shell/web-ui/nav/buttons/style", kind="button", owner="theme",
            props={"label": "旧"}, order=1)
        binding = self.registry.add_item(
            "app/shell/web-ui/nav/buttons/style", kind="button", owner="plugin",
            props={"label": "新"}, order=1, replace=True)
        entry = self.registry.catalog()["entries"][0]
        self.assertEqual(entry["owner"], "plugin")
        self.assertEqual(entry["metadata"]["props"]["label"], "新")
        binding()
        self.assertEqual(self.registry.catalog()["entries"][0]["owner"], "theme")
        base()

    def test_duplicate_without_replace_rejected(self) -> None:
        self.registry.add_item("app/shell/web-ui/nav/buttons/a", kind="button", owner="a")
        with self.assertRaises(ValueError):
            self.registry.add_item("app/shell/web-ui/nav/buttons/a", kind="button", owner="b")

    def test_pending_item_flushes_when_parent_registered(self) -> None:
        registry = UiRegistry()
        item = registry.add_item("app/shell/web-ui/pending", kind="button", owner="a")
        self.assertEqual(registry.catalog()["entries"], [])
        registry.add_slot("app/shell/web-ui", kind="container", children="keyed")
        self.assertEqual(len(registry.catalog()["entries"]), 1)
        item()

    def test_drop_owner_removes_item(self) -> None:
        self.registry.add_item("app/shell/web-ui/nav/buttons/a", kind="button", owner="a")
        self.registry.add_item("app/shell/web-ui/nav/buttons/b", kind="button", owner="b")
        self.assertEqual(self.registry.drop_owner("a"), 1)
        self.assertEqual([e["owner"] for e in self.registry.catalog()["entries"]], ["b"])


if __name__ == "__main__":
    unittest.main()
