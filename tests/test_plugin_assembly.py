# -*- coding: utf-8 -*-
"""插件目录自包含的启动期装配覆盖。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.boot.plugin_assembly import PluginAssemblyError, discover
from agent.core.slot import SlotLeaf
from agent.core.slot_tree import SlotTree


def make_base(ctx):
    return SlotLeaf(ctx.node.path)


def make_group(ctx):
    return SlotLeaf(ctx.node.path)


class PluginAssemblyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.plugins = self.root / "plugins"
        self.plugins.mkdir()
        self.tree_file = self.root / "slot_tree.json"
        self.tree_file.write_text(json.dumps({
            "root": "app",
            "nodes": [
                {"path": "app/group",
                 "factory": "tests.test_plugin_assembly:make_group"},
                {"path": "app/group/node",
                 "factory": "tests.test_plugin_assembly:make_base"},
                {"path": "app/group/meta",
                 "factory": "tests.test_plugin_assembly:make_base",
                 "metadata": {"flag": "base"}},
                {"path": "app/security",
                 "factory": "tests.test_plugin_assembly:make_group",
                 "frozen": True},
                {"path": "app/security/child",
                 "factory": "tests.test_plugin_assembly:make_base"},
            ],
        }), encoding="utf-8")

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

    def test_assembly_file_replaces_startup_node(self) -> None:
        root = self._plugin(assembly={
            "kind": "assembly",
            "nodes": [{"path": "app/group/node", "factory": "assembly:make"}],
        })
        (root / "helper.py").write_text(
            "from agent.core.slot import SlotLeaf\n"
            "class Replaced(SlotLeaf):\n"
            "    pass\n"
            "def make(ctx):\n"
            "    return Replaced(ctx.node.path)\n",
            encoding="utf-8")
        (root / "assembly.py").write_text(
            "from .helper import make\n",
            encoding="utf-8")

        overlay = discover(self.plugins, [])
        self.assertEqual([item["name"] for item in overlay.manifest], ["newplug"])
        tree = SlotTree.load(self.tree_file, overrides=overlay.nodes)
        plugin = tree.materialize(tree.node("app/group/node"))
        self.assertEqual(type(plugin).__name__, "Replaced")

    def test_metadata_patch_keeps_base_factory(self) -> None:
        root = self._plugin(assembly={
            "kind": "assembly",
            "nodes": [{"path": "app/group/meta", "metadata": {"flag": "plugin"}}],
        })
        overlay = discover(self.plugins, [])
        tree = SlotTree.load(self.tree_file, overrides=overlay.nodes)
        node = tree.node("app/group/meta")
        self.assertEqual(node.metadata["flag"], "plugin")
        self.assertTrue(node.factory.endswith("make_base"))

    def test_manifest_disable_wins(self) -> None:
        self._plugin(assembly={
            "kind": "assembly",
            "nodes": [{"path": "app/group/node", "factory": "assembly:make"}],
        })
        overlay = discover(self.plugins, [{"name": "newplug", "enabled": "0"}])
        self.assertEqual(overlay.nodes, ())
        self.assertEqual(overlay.manifest[0]["enabled"], "0")

    def test_auto_load_without_assembly_only_adds_manifest(self) -> None:
        self._plugin(auto_load=True)
        overlay = discover(self.plugins, [])
        self.assertEqual([item["name"] for item in overlay.manifest], ["newplug"])
        self.assertEqual(overlay.nodes, ())

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

    def test_factory_cannot_escape_plugin_root(self) -> None:
        self._plugin(assembly={
            "kind": "assembly",
            "nodes": [{"path": "app/group/node", "factory": "../evil:make"}],
        })
        with self.assertRaises(PluginAssemblyError):
            discover(self.plugins, [])

    def test_frozen_subtree_cannot_be_replaced(self) -> None:
        self._plugin(assembly={
            "kind": "assembly",
            "nodes": [{"path": "app/security/child",
                       "metadata": {"flag": "plugin"}}],
        })
        overlay = discover(self.plugins, [])
        with self.assertRaisesRegex(Exception, "冻结节点"):
            SlotTree.load(self.tree_file, overrides=overlay.nodes)

    def test_new_node_can_be_appended(self) -> None:
        root = self._plugin(assembly={
            "kind": "assembly",
            "nodes": [{"path": "app/new_node", "factory": "assembly:make"}],
        })
        (root / "assembly.py").write_text(
            "from agent.core.slot import SlotLeaf\n"
            "def make(ctx):\n"
            "    return SlotLeaf(ctx.node.path)\n",
            encoding="utf-8")
        overlay = discover(self.plugins, [])
        tree = SlotTree.load(self.tree_file, overrides=overlay.nodes)
        self.assertIsNotNone(tree.node("app/new_node"))

    def test_duplicate_override_requires_replace(self) -> None:
        root = self._plugin(assembly={
            "kind": "assembly",
            "nodes": [{"path": "app/group/node", "replace": False,
                       "metadata": {"flag": "plugin"}}],
        })
        overlay = discover(self.plugins, [])
        with self.assertRaisesRegex(Exception, "不允许替换"):
            SlotTree.load(self.tree_file, overrides=overlay.nodes)


if __name__ == "__main__":
    unittest.main()
