# -*- coding: utf-8 -*-
"""基础设置插件的面板与条目契约。"""
from __future__ import annotations

import unittest

from plugins.base_settings.plugin import register


class _Ctx:
    def __init__(self) -> None:
        self.panels = []
        self.items = []

    def add_settings_panel(self, panel_id, title, *, replace=False):
        self.panels.append((panel_id, title))
        return lambda: None

    def add_settings_item(self, parent, item_id, **kwargs):
        self.items.append((parent, item_id, kwargs))
        return lambda: None

    def add_ui_item(self, path, kind, props=None, order=None):
        return lambda: None


class BaseSettingsPluginTest(unittest.TestCase):
    def test_registers_host_panels_and_items(self) -> None:
        ctx = _Ctx()
        register(ctx)
        self.assertEqual([panel[0] for panel in ctx.panels], [
            "app/settings/agent", "app/settings/context",
            "app/settings/interface", "app/settings/plugin",
        ])
        self.assertEqual(len(ctx.items), 10)
        self.assertTrue(all(item[2]["save"] for item in ctx.items))

    def test_does_not_register_model_panel(self) -> None:
        ctx = _Ctx()
        register(ctx)
        self.assertNotIn("app/settings/model", [panel[0] for panel in ctx.panels])


if __name__ == "__main__":
    unittest.main()
