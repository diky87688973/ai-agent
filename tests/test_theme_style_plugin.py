# -*- coding: utf-8 -*-
"""主题风格插件：注册点与风格资源清单。"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from agent.capabilities.settings_registry import SettingsRegistry, seed_default_panels
from agent.shell.settings_panel import host_catalog
from plugins.theme_style.plugin import register

ROOT = Path(__file__).resolve().parent.parent / "plugins" / "theme_style"


class ThemeStylePluginTest(unittest.TestCase):
    def test_register_adds_settings_item_route_and_boot_script(self) -> None:
        fields = []
        routes = []
        ctx = SimpleNamespace(
            data_dir=ROOT,
            add_route=lambda method, path, handler: routes.append((method, path)) or (lambda: None),
            add_settings_item=lambda *args, **kwargs: fields.append((args, kwargs)) or (lambda: None),
            add_ui_item=lambda *args, **kwargs: (lambda: None),
        )
        self.assertEqual(len(register(ctx)), 3)
        self.assertEqual(fields[0][0], ("settings/interface", "theme_style"))
        self.assertEqual(fields[0][1]["kind"], "select")
        self.assertEqual(routes, [("GET", "style")])

    def test_style_assets_and_theme_lists(self) -> None:
        catalog = json.loads((ROOT / "styles" / "catalog.json").read_text(encoding="utf-8"))
        styles = {item["id"]: item for item in catalog["styles"]}
        self.assertIn("dsh", styles)
        self.assertIn("minimal", styles)
        for style in styles.values():
            manifest = json.loads((ROOT / style["manifest"]).read_text(encoding="utf-8"))
            self.assertEqual(set(manifest["themes"]), {"dark", "light"})
            for theme in ("dark", "light"):
                for css in manifest["themes"][theme]["css"]:
                    self.assertTrue((ROOT / css).is_file(), css)

    def test_host_catalog_includes_plugin_item(self) -> None:
        registry = SettingsRegistry()
        seed_default_panels(registry)
        registry.add_item(
            "theme_style", "settings/interface", "theme_style",
            kind="select", label="界面风格", default="dsh",
            options=({"value": "dsh", "label": "DSH"}, {"value": "minimal", "label": "极简"}),
            save=lambda value: {"ok": True},
        )
        app = SimpleNamespace(plugin_host=SimpleNamespace(settings=registry))
        catalog = host_catalog(app=app)
        section = next(item for item in catalog["sections"] if item["id"] == "settings/interface")
        field = next(item for item in section["fields"] if item.get("id") == "settings/interface/theme_style")
        self.assertTrue(field["plugin"])
        self.assertEqual(field["kind"], "select")

    def test_boot_script_separate_from_core(self) -> None:
        self.assertTrue((ROOT / "ui" / "theme-style.js").is_file())
        self.assertTrue((ROOT / "styles" / "minimal" / "dark.css").is_file())
        self.assertTrue((ROOT / "styles" / "minimal" / "light.css").is_file())


if __name__ == "__main__":
    unittest.main()
