# -*- coding: utf-8 -*-
"""AI说话插件装配测试：临时清单、工具/端点/启动脚本、卸载与事件出口。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.app import build_app  # noqa: E402
from agent.core.context import SERVICE_PLUGIN_EVENTS  # noqa: E402
from agent.shell.classic_adapter.plugin_events import PluginEventPublisher  # noqa: E402
from agent.shell.service_keys import SERVICE_CLASSIC_ADAPTER  # noqa: E402


class AISpeakAppTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ai_speak_plugin_")
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        manifest = base / "plugins.ini"
        manifest.write_text("[plugin:ai_speak]\nversion = 1.0\n", encoding="utf-8")
        env = mock.patch.dict(os.environ, {"AI_AGENT_DATA_ROOT": str(base / "data")})
        env.start()
        self.addCleanup(env.stop)
        self.app = build_app(plugins_dir=_ROOT / "plugins", plugins_path=manifest)
        self.addCleanup(self.app.dispose)

    def test_loaded_wiring(self) -> None:
        self.assertEqual(self.app.plugin_host.loaded_names(), ["ai_speak"])
        tool = self.app.registry.get("ai_speak")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.label, "AI说话")
        self.assertEqual(set(tool.parameters), {"msg"})

        contribs = self.app.plugin_host.contributions
        self.assertEqual(
            [(route.method, route.path) for route in contribs.routes_of("ai_speak")],
            [("GET", "config"), ("GET", "status")],
        )
        scripts = [row["rel_path"] for row in
                   (item.as_dict() for item in contribs.all_boot_scripts())]
        self.assertEqual(scripts, ["ui/player.js", "ui/tool-view.js"])
        self.assertIsNotNone(self.app.plugin_host.runtime("ai_speak"))
        self.assertIsInstance(
            self.app.context.get(SERVICE_PLUGIN_EVENTS), PluginEventPublisher
        )

    def test_publisher_tracks_connections(self) -> None:
        publisher = self.app.context.get(SERVICE_PLUGIN_EVENTS)
        self.assertFalse(publisher.connected())
        classic = self.app.context.get(SERVICE_CLASSIC_ADAPTER)
        box = classic.attach()
        try:
            self.assertTrue(publisher.connected())
            self.assertEqual(
                publisher("ai_speak", "stop", {"conversation_id": "cid-12345678"}),
                1,
            )
            self.assertEqual(box.get_nowait()["type"], "plugin_event")
        finally:
            classic.detach(box)

    def test_unload_clears_everything(self) -> None:
        self.app.plugin_host.unload("ai_speak")
        self.assertEqual(self.app.plugin_host.loaded_names(), [])
        self.assertIsNone(self.app.registry.get("ai_speak"))
        contribs = self.app.plugin_host.contributions
        self.assertEqual(contribs.routes_of("ai_speak"), [])
        self.assertEqual(contribs.all_boot_scripts(), [])
        self.assertIsNone(self.app.plugin_host.runtime("ai_speak"))


if __name__ == "__main__":
    unittest.main()
