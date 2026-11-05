# -*- coding: utf-8 -*-
"""插件目录自包含的启动期装配覆盖。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.boot.plugin_assembly import discover


class PluginAssemblyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.plugins = self.root / "plugins"
        self.plugins.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _plugin(self, name: str = "newplug", *, assembly=None,
                auto_load: bool = False) -> Path:
        root = self.plugins / name
        root.mkdir()
        (root / "plugin.py").write_text(
            "def register(ctx):\n    return []\n", encoding="utf-8")
        if auto_load:
            (root / "plugin-meta.json").write_text(
                json.dumps({"auto_load": True}), encoding="utf-8")
        if assembly is not None:
            (root / "plugin-assembly.json").write_text(
                json.dumps(assembly), encoding="utf-8")
        return root

    def test_manifest_disable_wins(self) -> None:
        self._plugin(assembly={
            "kind": "assembly",
            "nodes": [{"path": "app/group/node", "factory": "assembly:make"}],
        })
        overlay = discover(self.plugins, [{"name": "newplug", "enabled": "0"}])
        self.assertEqual(overlay.manifest[0]["enabled"], "0")

    def test_auto_load_without_assembly_only_adds_manifest(self) -> None:
        self._plugin(auto_load=True)
        overlay = discover(self.plugins, [])
        self.assertEqual([item["name"] for item in overlay.manifest], ["newplug"])

    def test_auto_loaded_plugin_registers_without_manifest_entry(self) -> None:
        from agent.capabilities.plugins import PluginHost
        from agent.capabilities.registry import ToolRegistry

        self._plugin(auto_load=True)
        overlay = discover(self.plugins, [])
        host = PluginHost(self.plugins, ToolRegistry())
        reports = host.load_manifest(overlay.manifest)
        self.assertEqual([report.status for report in reports], ["loaded"])

    def test_boot_app_loads_auto_plugin_with_empty_manifest(self) -> None:
        from agent.app import build_app

        self._plugin(auto_load=True)
        manifest = self.root / "plugins.ini"
        manifest.write_text("", encoding="utf-8")
        app = build_app(
            plugins_dir=self.plugins,
            plugins_path=manifest,
            data_root=self.root / "data",
        )
        try:
            self.assertTrue(app.plugin_host.reports())
            self.assertEqual(app.plugin_host.reports()[-1].name, "newplug")
            self.assertEqual(app.plugin_host.reports()[-1].status, "loaded")
        finally:
            app.dispose()


if __name__ == "__main__":
    unittest.main()
