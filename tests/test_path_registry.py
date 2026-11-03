# -*- coding: utf-8 -*-
"""插件路径注册表与插口协议。"""
from __future__ import annotations

import unittest

from agent.capabilities.path_registry import PathRegistry, PathRegistryError


class PathRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = PathRegistry()
        self.registry.add_slot("app/shell/web-ui", kind="root", children="fixed",
                               fixed_children=("nav",), owner="web_ui")
        self.registry.add_slot("app/shell/web-ui/nav", kind="container", children="fixed",
                               fixed_children=("buttons",), owner="web_ui")
        self.registry.add_slot("app/shell/web-ui/nav/buttons", kind="container",
                               children="keyed", allowed_kinds=("button",),
                               owner="*")

    def test_registers_path_and_cleans_owner(self) -> None:
        self.registry.register("app/shell/web-ui/nav", kind="container", owner="web_ui")
        self.registry.register("app/shell/web-ui/nav/buttons/update", kind="button",
                               owner="auto_update")
        self.assertEqual(self.registry.get("app/shell/web-ui/nav/buttons/update").owner,
                         "auto_update")
        self.assertEqual(self.registry.drop_owner("auto_update"), 1)
        with self.assertRaises(PathRegistryError):
            self.registry.get("app/shell/web-ui/nav/buttons/update")

    def test_rejects_arbitrary_child_and_kind(self) -> None:
        with self.assertRaises(PathRegistryError):
            self.registry.register("app/shell/web-ui/foo", kind="button", owner="p")
        with self.assertRaises(PathRegistryError):
            self.registry.register("app/shell/web-ui/nav/buttons/update", kind="panel",
                                   owner="p")
        self.registry.register("app/shell/web-ui/nav/buttons/update", kind="button",
                               owner="p")
        with self.assertRaises(PathRegistryError):
            self.registry.register("app/shell/web-ui/nav/buttons/update", kind="button",
                                   owner="p")


if __name__ == "__main__":
    unittest.main()
