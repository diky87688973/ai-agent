# -*- coding: utf-8 -*-
"""主题风格插件：片段声明与风格资源清单。"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.capabilities.settings_registry import SettingsRegistry, seed_default_panels  # noqa: E402
from agent.core.slot_fragments import load_merged  # noqa: E402
from agent.shell.settings_panel import host_catalog  # noqa: E402

PLUGIN_ROOT = ROOT / "plugins" / "theme_style"


class ThemeStylePluginTest(unittest.TestCase):
    def test_fragment_declares_setting_and_style_route(self) -> None:
        """设置条目与 `GET style` 路由都由片段声明，且归 theme_style。"""
        config = load_merged(ROOT)
        item = "app/settings/interface/theme_style"
        self.assertIn(item, config.specs)
        self.assertEqual(config.specs[item].kind, "setting")
        self.assertEqual(config.origin_of(item), "theme_style")
        # 条目形状（kind=select）由工厂造出来，片段只给工厂名，不重复写一份 kind
        self.assertEqual(config.specs[item].factory, "plugin:make_setting")

        routes = {path: spec for path, spec in config.specs.items()
                  if spec.kind == "route"}
        route = "app/plugins/theme_style/routes/style"
        self.assertIn(route, routes)
        self.assertEqual(routes[route].method, "GET")
        self.assertEqual(config.origin_of(route), "theme_style")

    def test_style_assets_and_theme_lists(self) -> None:
        catalog = json.loads((PLUGIN_ROOT / "styles" / "catalog.json").read_text(encoding="utf-8"))
        styles = {item["id"]: item for item in catalog["styles"]}
        self.assertIn("dsh", styles)
        self.assertIn("minimal", styles)
        for style in styles.values():
            manifest = json.loads((PLUGIN_ROOT / style["manifest"]).read_text(encoding="utf-8"))
            self.assertEqual(set(manifest["themes"]), {"dark", "light"})
            for theme in ("dark", "light"):
                for css in manifest["themes"][theme]["css"]:
                    self.assertTrue((PLUGIN_ROOT / css).is_file(), css)

    def test_host_catalog_includes_plugin_item(self) -> None:
        registry = SettingsRegistry()
        seed_default_panels(registry)
        registry.add_item(
            "theme_style", "app/settings/interface", "theme_style",
            kind="select", label="界面风格", default="dsh",
            options=({"value": "dsh", "label": "DSH"}, {"value": "minimal", "label": "极简"}),
            save=lambda value: {"ok": True},
        )
        app = SimpleNamespace(plugin_host=SimpleNamespace(settings=registry))
        catalog = host_catalog(app=app)
        section = next(item for item in catalog["sections"] if item["id"] == "app/settings/interface")
        field = next(item for item in section["fields"] if item.get("id") == "app/settings/interface/theme_style")
        self.assertTrue(field["plugin"])
        self.assertEqual(field["kind"], "select")

    def test_boot_script_separate_from_core(self) -> None:
        self.assertTrue((PLUGIN_ROOT / "ui" / "theme-style.js").is_file())
        self.assertTrue((PLUGIN_ROOT / "styles" / "minimal" / "dark.css").is_file())
        self.assertTrue((PLUGIN_ROOT / "styles" / "minimal" / "light.css").is_file())


if __name__ == "__main__":
    unittest.main()
