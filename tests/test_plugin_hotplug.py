"""插件代在公开设置入口完成启停、失败恢复和轮次延迟。"""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from agent.app import build_app
from agent.shell.plugin_settings import (
    list_plugins,
    set_plugin_enabled,
    sync_plugins,
    write_plugin_config,
)
from agent.shell.settings_panel import handle_get


class PluginHotplugTest(unittest.TestCase):
    def test_deferred_config_failure_is_queryable_and_preserves_saved_text(self) -> None:
        config = self.plugin / "plugin-config.ini"
        config.write_text("[example]\nvalue=old\n", encoding="utf-8")
        original = self.app.registry.get("example_tool")
        source = self.plugin / "plugin.py"
        source.write_text("def make(ctx): raise RuntimeError('deferred factory failure')\n",
                          encoding="utf-8")
        with self.app.context.slot_lifecycle.turn():
            result = write_plugin_config("example", text="value=new\n", app=self.app)
            self.assertTrue(result["ok"])
            request_id = result["reports"][0]["request_id"]
            operation = list_plugins(app=self.app)["operations"][-1]
            self.assertEqual(operation["status"], "queued")
        operation = next(item for item in list_plugins(app=self.app)["operations"]
                         if item["request_id"] == request_id)
        self.assertEqual(operation["status"], "failed")
        self.assertIn("deferred factory failure", operation["error"])
        self.assertIn("value=new", config.read_text(encoding="utf-8"))
        self.assertIs(self.app.registry.get("example_tool"), original)

    def test_operation_history_is_bounded_readonly_and_has_terminal_states(self) -> None:
        lifecycle = self.app.context.slot_lifecycle
        with lifecycle.turn():
            receipt = lifecycle.request(lambda: None, label="probe")
            self.assertFalse(receipt.applied)
            self.assertEqual(lifecycle.operations[-1]["status"], "queued")
        self.assertEqual(lifecycle.operations[-1]["request_id"], receipt.request_id)
        self.assertEqual(lifecycle.operations[-1]["status"], "succeeded")
        with self.assertRaises(TypeError):
            lifecycle.operations[-1]["status"] = "failed"
        for _ in range(70):
            lifecycle.request(lambda: None)
        self.assertEqual(len(lifecycle.operations), 64)
        with lifecycle.turn():
            for _ in range(64):
                lifecycle.request(lambda: None)
            with self.assertRaises(RuntimeError):
                lifecycle.request(lambda: None)
        self.assertTrue(all(item["status"] == "succeeded" for item in lifecycle.operations))

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="agent_hotplug_")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.plugins = self.root / "plugins"
        self.plugin = self.plugins / "example"
        self.plugin.mkdir(parents=True)
        self.manifest = self.root / "plugins.ini"
        self.manifest.write_text("[plugin:example]\nenabled=1\n", encoding="utf-8")
        (self.plugin / "plugin-meta.json").write_text(
            json.dumps({"name": "example", "version": "1"}), encoding="utf-8")
        (self.plugin / "plugin.py").write_text(
            "from agent.capabilities.registry import ToolPlugin\n"
            "class Example(ToolPlugin):\n"
            "    name='example_tool'\n"
            "    def execute(self, arguments): return 'ok'\n"
            "def make(ctx): return Example()\n", encoding="utf-8")
        self.fragment = self.plugin / "plugin-slots.json"
        self.fragment.write_text(json.dumps({"slots": [{
            "path": "app/plugins/example/tools/example_tool", "kind": "tool",
            "factory": "plugin:make"}]}), encoding="utf-8")
        self.app = build_app(data_root=self.root / "data", plugins_dir=self.plugins,
                             plugins_path=self.manifest)
        self.addCleanup(self.app.dispose)

    def toggle(self, enabled: bool):
        return set_plugin_enabled("example", enabled, self.app,
                                  plugins_path=self.manifest, plugins_dir=self.plugins)

    def test_disable_and_enable_restores_tool(self) -> None:
        original_host = self.app.context
        self.assertIsNotNone(self.app.registry.get("example_tool"))
        self.assertTrue(self.toggle(False)["ok"])
        self.assertIsNone(self.app.registry.get("example_tool"))
        self.assertTrue(self.toggle(True)["ok"])
        self.assertEqual(self.app.registry.get("example_tool").execute({}), "ok")
        self.assertIs(self.app.context, original_host)

    def test_changes_wait_for_all_active_turns(self) -> None:
        lifecycle = self.app.context.slot_lifecycle
        with lifecycle.turn() as snapshot:
            with lifecycle.turn():
                self.assertTrue(self.toggle(False)["ok"])
                self.assertIsNotNone(self.app.registry.get("example_tool"))
                self.assertIs(lifecycle.snapshots.current, snapshot)
            self.assertIsNotNone(self.app.registry.get("example_tool"))
        self.assertIsNone(self.app.registry.get("example_tool"))
        self.assertGreater(lifecycle.snapshots.version, snapshot.version)
        self.assertTrue(self.toggle(True)["ok"])
        with lifecycle.turn():
            self.app.plugin_host.unload("example")
            self.app.plugin_host.unload("missing")
            self.assertIn("example", self.app.plugin_host.loaded_names())
        self.assertNotIn("example", self.app.plugin_host.loaded_names())
        self.assertIsNone(self.app.registry.get("example_tool"))

    def test_bad_factory_keeps_previous_generation(self) -> None:
        previous = self.app.registry.get("example_tool")
        raw = json.loads(self.fragment.read_text(encoding="utf-8"))
        raw["slots"][0]["factory"] = "plugin:missing"
        self.fragment.write_text(json.dumps(raw), encoding="utf-8")
        reports = sync_plugins(self.app, plugins_path=self.manifest,
                               plugins_dir=self.plugins)
        self.assertTrue(any(row["status"] == "error" for row in reports))
        self.assertIs(self.app.registry.get("example_tool"), previous)
        self.assertIn("example", self.app.plugin_host.loaded_names())

    def test_binding_failure_restores_previous_generation(self) -> None:
        previous = self.app.registry.get("example_tool")
        raw = json.loads(self.fragment.read_text(encoding="utf-8"))
        raw["slots"].append({"path": "app/plugins/example/tools/duplicate",
                             "kind": "tool", "factory": "plugin:make"})
        self.fragment.write_text(json.dumps(raw), encoding="utf-8")
        reports = sync_plugins(self.app, plugins_path=self.manifest,
                               plugins_dir=self.plugins)
        self.assertTrue(any(row["status"] == "error" for row in reports))
        self.assertIs(self.app.registry.get("example_tool"), previous)
        self.assertIn("example", self.app.plugin_host.loaded_names())

    def test_pure_declarative_plugin_can_be_enabled(self) -> None:
        self.toggle(False)
        (self.plugin / "plugin.py").unlink()
        self.fragment.write_text(json.dumps({"slots": [{
            "path": "app/plugins/example", "kind": "container"}]}), encoding="utf-8")
        self.assertTrue(self.toggle(True)["ok"])
        self.assertIn("example", self.app.plugin_host.loaded_names())

    def test_snapshot_structure_rejects_mutation(self) -> None:
        snapshot = self.app.context.slot_lifecycle.snapshots.current
        with self.assertRaises(TypeError):
            snapshot.config.specs["bad"] = None
        with self.assertRaises(TypeError):
            snapshot.built["bad"] = None

    def test_reload_reads_changed_source_without_restart(self) -> None:
        source = self.plugin / "plugin.py"
        source.write_text(source.read_text(encoding="utf-8").replace("'ok'", "'v2'"),
                          encoding="utf-8")
        self.assertEqual(sync_plugins(self.app, plugins_path=self.manifest,
                                      plugins_dir=self.plugins), [])
        self.assertEqual(self.app.registry.get("example_tool").execute({}), "v2")

    def test_last_queued_request_wins(self) -> None:
        with self.app.context.slot_lifecycle.turn():
            self.toggle(False)
            self.toggle(True)
        self.assertIsNotNone(self.app.registry.get("example_tool"))

    def test_disabled_manifest_prevents_initial_construction(self) -> None:
        self.toggle(False)
        other = build_app(data_root=self.root / "other-data", plugins_dir=self.plugins,
                          plugins_path=self.manifest)
        try:
            self.assertIsNone(other.registry.get("example_tool"))
            self.assertNotIn("example", other.plugin_host.loaded_names())
        finally:
            other.dispose()

    def test_plugin_directory_removal_retracts_its_capabilities(self) -> None:
        self.plugin.rename(self.root / "retired-example")
        reports = sync_plugins(self.app, plugins_path=self.manifest, plugins_dir=self.plugins)
        self.assertEqual(reports, [])
        self.assertIsNone(self.app.registry.get("example_tool"))
        self.assertNotIn("example", self.app.plugin_host.loaded_names())

    def test_external_manifest_path_controls_fragment_and_factory(self) -> None:
        external = self.root / "external-source"
        self.plugin.rename(external)
        source = external / "plugin.py"
        source.write_text(source.read_text(encoding="utf-8").replace("'ok'", "'external'"),
                          encoding="utf-8")
        self.manifest.write_text(
            f"[plugin:example]\nenabled=1\npath={external.as_posix()}\n", encoding="utf-8")
        with mock.patch("agent.capabilities.plugins.get_plugin_tree_only", return_value=False):
            reports = sync_plugins(self.app, plugins_path=self.manifest, plugins_dir=self.plugins)
        self.assertEqual(reports, [])
        self.assertEqual(self.app.registry.get("example_tool").execute({}), "external")
        self.assertEqual(self.app.plugin_host.plugin_root("example"), external)

    def test_external_factory_is_rejected_when_tree_policy_is_required(self) -> None:
        previous = self.app.registry.get("example_tool")
        external = self.root / "external-source"
        self.plugin.rename(external)
        self.manifest.write_text(
            f"[plugin:example]\nenabled=1\npath={external.as_posix()}\n", encoding="utf-8")
        with mock.patch("agent.capabilities.plugins.get_plugin_tree_only", return_value=True):
            reports = sync_plugins(self.app, plugins_path=self.manifest, plugins_dir=self.plugins)
        self.assertTrue(any(row["status"] == "error" for row in reports))
        self.assertIs(self.app.registry.get("example_tool"), previous)

    def test_parallel_turn_keeps_old_tool_until_reader_exits(self) -> None:
        entered = threading.Event()
        release = threading.Event()
        def read_turn() -> None:
            with self.app.context.slot_lifecycle.turn():
                entered.set()
                release.wait(5)
        thread = threading.Thread(target=read_turn)
        thread.start()
        try:
            self.assertTrue(entered.wait(5))
            self.assertTrue(self.toggle(False)["ok"])
            self.assertIsNotNone(self.app.registry.get("example_tool"))
        finally:
            release.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertIsNone(self.app.registry.get("example_tool"))


class WebUIHotplugTest(unittest.TestCase):
    def test_ui_without_python_entry_can_be_reenabled(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent_webui_hotplug_") as tmp:
            root = Path(tmp)
            plugins = Path(__file__).resolve().parents[1] / "plugins"
            manifest = root / "plugins.ini"
            names = [p.name for p in plugins.iterdir() if (p / "plugin-meta.json").is_file()]
            manifest.write_text("\n".join(
                f"[plugin:{name}]\nenabled={int(name in {'web_ui', 'skills'})}\n"
                for name in names), encoding="utf-8")
            app = build_app(data_root=root / "data", plugins_dir=plugins,
                            plugins_path=manifest)
            try:
                _, payload = handle_get("/api/settings/plugins", {}, app)
                active = {row["name"] for row in payload["plugins"] if row["enabled"]}
                self.assertEqual(active, {"web_ui", "skills"})
                skills = app.registry.get("skills")
                for enabled in (False, True, False, True):
                    result = set_plugin_enabled("web_ui", enabled, app,
                                                plugins_path=manifest, plugins_dir=plugins)
                    self.assertTrue(result["ok"], result)
                    paths = app._slot_assembly.config.paths()
                    self.assertEqual("app/shell/web-ui/nav/buttons" in paths, enabled)
                    self.assertIs(app.registry.get("skills"), skills)
                    self.assertEqual("web_ui" in app.plugin_host.loaded_names(), enabled)
            finally:
                app.dispose()
