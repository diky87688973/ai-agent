"""插件事件声明、订阅依赖和热插拔事务。"""
from __future__ import annotations

import json
import unittest

from agent.core.events import Event
from agent.core.slot_config import SlotConfig
from agent.core.slot_spec import SlotConfigError
from agent.shell.plugin_settings import set_plugin_enabled, sync_plugins
from tests import test_plugin_hotplug as hotplug_fixture

CHANNEL = "app/plugins/example/events/completed"


class PluginEventValidationTest(unittest.TestCase):
    def test_declared_channel_and_reference_are_valid(self):
        config = SlotConfig.parse({"slots": [
            {"path": CHANNEL, "kind": "event-channel"},
            {"path": "app/plugins/listener/on_completed", "kind": "event",
             "factory": "plugin:make", "requires": {"event": CHANNEL}},
        ]})
        self.assertEqual(config.specs[CHANNEL].kind, "event-channel")

    def test_invalid_channel_and_subscription_are_rejected(self):
        valid = {"path": CHANNEL, "kind": "event-channel"}
        for update in ({"path": "app/events/completed"}, {"scope": "session"},
                       {"factory": "plugin:make"}, {"children": "keyed"},
                       {"requires": {"unused": CHANNEL}}):
            with self.subTest(update=update), self.assertRaises(SlotConfigError):
                SlotConfig.parse({"slots": [valid | update]})
        for target in ("app/missing", "app/plugins/example/container"):
            with self.subTest(target=target), self.assertRaises(SlotConfigError):
                SlotConfig.parse({"slots": [valid,
                    {"path": "app/plugins/example/container", "kind": "container"},
                    {"path": "app/plugins/listener/on_completed", "kind": "event",
                     "factory": "plugin:make", "requires": {"event": target}},
                ]})
        with self.assertRaises(SlotConfigError):
            SlotConfig.parse({"slots": [valid, valid]})
        with self.assertRaises(SlotConfigError):
            SlotConfig.parse({"slots": [valid, {
                "path": "app/plugins/listener/on_completed", "kind": "event", "scope": "session",
                "factory": "plugin:make", "requires": {"event": CHANNEL},
            }]})


class PluginEventHotplugTest(unittest.TestCase):
    setUp = hotplug_fixture.PluginHotplugTest.setUp

    def test_cross_plugin_delivery_reload_rollback_and_disable(self):
        raw = json.loads(self.fragment.read_text(encoding="utf-8"))
        raw["slots"].append({"path": CHANNEL, "kind": "event-channel"})
        self.fragment.write_text(json.dumps(raw), encoding="utf-8")
        listener = self.plugins / "listener"
        listener.mkdir()
        (listener / "plugin-meta.json").write_text('{"name":"listener"}', encoding="utf-8")
        (listener / "plugin.py").write_text(
            "def make(ctx, event):\n"
            "    path=ctx.data_dir/'received.txt'\n"
            "    path.parent.mkdir(parents=True,exist_ok=True)\n"
            "    def handle(message):\n"
            "        with path.open('a',encoding='utf-8') as stream: stream.write(message.data['value']+'\\n')\n"
            "    return handle\n", encoding="utf-8")
        fragment = listener / "plugin-slots.json"
        declaration = {"slots": [{"path": "app/plugins/listener/on_completed", "kind": "event",
                                  "factory": "plugin:make", "requires": {"event": CHANNEL}}]}
        fragment.write_text(json.dumps(declaration), encoding="utf-8")
        self.manifest.write_text("[plugin:example]\nenabled=1\n[plugin:listener]\nenabled=1\n", encoding="utf-8")
        sync_plugins(self.app, plugins_path=self.manifest, plugins_dir=self.plugins)
        self.app.event_bus.publish(Event(CHANNEL, {"value": "first"}))
        received = next((self.root / "data").rglob("received.txt"))
        self.assertEqual(received.read_text(encoding="utf-8"), "first\n")
        declaration["slots"][0]["factory"] = "plugin:missing"
        fragment.write_text(json.dumps(declaration), encoding="utf-8")
        reports = sync_plugins(self.app, plugins_path=self.manifest, plugins_dir=self.plugins)
        self.assertTrue(any(row["status"] == "error" for row in reports))
        self.app.event_bus.publish(Event(CHANNEL, {"value": "rollback"}))
        self.assertEqual(received.read_text(encoding="utf-8"), "first\nrollback\n")
        declaration["slots"][0]["factory"] = "plugin:make"
        fragment.write_text(json.dumps(declaration), encoding="utf-8")
        self.assertTrue(set_plugin_enabled("listener", False, self.app)["ok"])
        self.app.event_bus.publish(Event(CHANNEL, {"value": "disabled"}))
        self.assertEqual(received.read_text(encoding="utf-8"), "first\nrollback\n")
        self.assertTrue(set_plugin_enabled("listener", True, self.app)["ok"])
        self.app.event_bus.publish(Event(CHANNEL, {"value": "enabled"}))
        self.assertEqual(received.read_text(encoding="utf-8"), "first\nrollback\nenabled\n")
        self.assertFalse(set_plugin_enabled("example", False, self.app)["ok"])
        self.assertTrue(set_plugin_enabled("listener", False, self.app)["ok"])
        self.assertTrue(set_plugin_enabled("example", False, self.app)["ok"])
        self.assertNotIn(CHANNEL, self.app._plugin_runtime.assembly.config.specs)
