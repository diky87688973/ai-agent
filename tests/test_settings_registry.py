# -*- coding: utf-8 -*-
"""插件系统设置注册表契约。"""
from __future__ import annotations

import unittest

from agent.capabilities.settings_registry import SettingsRegistry, SettingsRegistryError


class SettingsRegistryTest(unittest.TestCase):
    def test_panel_item_and_save_callback(self) -> None:
        registry = SettingsRegistry()
        registry.add_panel("theme_style", "settings/interface", "界面", order=1)
        saved = []
        registry.add_item(
            "theme_style", "settings/interface", "theme_style",
            kind="select", label="界面风格", default="dsh",
            options=({"value": "dsh", "label": "DSH"}, {"value": "minimal", "label": "极简"}),
            save=lambda value: saved.append(value) or {"ok": True},
        )
        self.assertEqual([panel.panel_id for panel in registry.panels_in_order()],
                         ["settings/interface"])
        self.assertEqual(registry.values(), {"settings/interface/theme_style": "dsh"})
        self.assertTrue(registry.save({"settings/interface/theme_style": "minimal"})["ok"])
        self.assertEqual(saved, ["minimal"])

    def test_invalid_select_and_missing_parent(self) -> None:
        registry = SettingsRegistry()
        with self.assertRaises(SettingsRegistryError):
            registry.add_item("p", "settings/interface", "x", kind="select",
                              label="X", save=lambda value: {"ok": True})
        registry.add_panel("p", "settings/interface", "界面")
        with self.assertRaises(SettingsRegistryError):
            registry.add_item("p", "settings/interface", "x", kind="select",
                              label="X", options=(), save=lambda value: {"ok": True})
        with self.assertRaises(SettingsRegistryError):
            registry.save({"settings/interface/missing": "x"})

    def test_failed_save_rolls_back_committed_items(self) -> None:
        registry = SettingsRegistry()
        registry.add_panel("p", "settings/custom", "自定义")
        state = {"a": "old", "b": "old"}

        def save_a(value):
            state["a"] = value
            return {"ok": True}

        def save_b(value):
            state["b"] = value
            return {"ok": False, "error": "拒绝"}

        registry.add_item("p", "settings/custom", "a", kind="text", label="A",
                          save=save_a, load=lambda: state["a"])
        registry.add_item("p", "settings/custom", "b", kind="text", label="B",
                          save=save_b, load=lambda: state["b"])
        with self.assertRaises(SettingsRegistryError):
            registry.save({"settings/custom/a": "new", "settings/custom/b": "new-b"})
        self.assertEqual(state, {"a": "old", "b": "old"})

    def test_drop_plugin_removes_items_and_panels(self) -> None:
        registry = SettingsRegistry()
        registry.add_panel("p", "settings/custom", "自定义")
        registry.add_item("p", "settings/custom", "item", kind="text",
                          label="字段", save=lambda value: {"ok": True})
        self.assertEqual(registry.drop_plugin("p"), 2)
        self.assertEqual(registry.panels, {})
        self.assertEqual(registry.items, {})


if __name__ == "__main__":
    unittest.main()
