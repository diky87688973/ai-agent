# -*- coding: utf-8 -*-
"""插件 UI 贡献替换：同路径替换、旧实现回退、disposer 顺序。"""
from __future__ import annotations

import unittest

from agent.capabilities.plugin_context import PluginContext
from agent.core.slot_tree import SlotTree


class _FakeUi:
    def __init__(self) -> None:
        self.items = {}
        self.calls = []

    def add_item(self, path, *, kind, owner, handler=None, props=None,
                 order=None, replace=False):
        if path in self.items and not replace:
            raise ValueError("duplicate")
        self.items[path] = {"kind": kind, "owner": owner, "props": dict(props or {})}
        self.calls.append(("add", path, owner))
        def drop():
            if self.items.get(path, {}).get("owner") == owner:
                self.items.pop(path, None)
                self.calls.append(("drop", path, owner))
        return drop


class PluginContextReplaceTest(unittest.TestCase):
    def test_ui_item_replace_restores_previous_owner(self) -> None:
        ui = _FakeUi()
        tree = SlotTree([], root="app")
        path = "app/shell/web-ui/input/buttons/example"
        first = PluginContext("first", registry=None, ui=ui, tree=tree)
        first.add_ui_item(path, kind="button", props={"label": "first"})
        self.assertEqual(ui.items[path]["owner"], "first")

        second = PluginContext("second", registry=None, ui=ui, tree=tree)
        second.add_ui_item(path, kind="button", props={"label": "second"},
                           replace=True)
        self.assertEqual(ui.items[path]["owner"], "second")
        self.assertEqual(ui.items[path]["props"]["label"], "second")

        second_disp = second.owned_disposers()[-1]
        second_disp()
        self.assertEqual(ui.items[path]["owner"], "first")
        self.assertEqual(ui.items[path]["props"]["label"], "first")
        tree.dispose_all()


if __name__ == "__main__":
    unittest.main()
