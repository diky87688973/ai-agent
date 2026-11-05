# -*- coding: utf-8 -*-
"""AI角色扮演插件装配测试：临时清单、工具/端点/启动脚本、卸载与事件出口。"""
from __future__ import annotations

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
from agent.shell.service_keys import SERVICE_CLASSIC_ADAPTER, SERVICE_RUNNER  # noqa: E402


class AICosplayAppTest(unittest.TestCase):
    def setUp(self) -> None:
        from tests.testkit import isolate_data
        isolate_data(self)
        self._tmp = tempfile.TemporaryDirectory(prefix="ai_cosplay_plugin_")
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        manifest = base / "plugins.ini"
        manifest.write_text("\n".join(
            f"[plugin:{folder.name}]\nenabled={int(folder.name in {'ai_cosplay', 'web_ui'})}\n"
            for folder in (_ROOT / "plugins").iterdir()
            if (folder / "plugin-meta.json").is_file()), encoding="utf-8")
        self.app = build_app(plugins_dir=_ROOT / "plugins", plugins_path=manifest)
        self.addCleanup(self.app.dispose)

    def test_loaded_wiring(self) -> None:
        self.assertEqual(self.app.plugin_host.loaded_names(), ["ai_cosplay", "web_ui"])
        tool = self.app.registry.get("ai_speek")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.label, "AI扮演")
        self.assertEqual(set(tool.parameters), {"msg"})

        contribs = self.app.plugin_host.contributions
        self.assertEqual(
            [(route.method, route.path) for route in contribs.routes_of("ai_cosplay")],
            [("GET", "config"), ("GET", "status"), ("POST", "played")],
        )
        ui = self.app.plugin_host.ui
        item = next(
            (row for row in ui.catalog()["entries"]
             if row.get("path") == "app/shell/web-ui/runtime/left-panel/ai_cosplay"),
            None)
        if item is None:
            item = next(
                (row for row in ui.pending
                 if row.get("path") == "app/shell/web-ui/runtime/left-panel/ai_cosplay"),
                None)
        self.assertIsNotNone(item)
        scripts = item["metadata"]["props"]["scripts"]
        self.assertEqual(scripts, ["ui/player.js", "ui/tool-view.js"])
        self.assertIsNotNone(self.app.plugin_host.runtime("ai_cosplay"))
        self.assertIsInstance(
            self.app.context.get(SERVICE_PLUGIN_EVENTS), PluginEventPublisher
        )

    def test_voice_directive_is_in_request_tail(self) -> None:
        runtime = self.app.plugin_host.runtime("ai_cosplay")
        with mock.patch.object(runtime, "provider_ready", return_value=True):
            text = self.app.prompt_tail.render("cid-12345678")
            runner = self.app.context.get(SERVICE_RUNNER)
            note = runner._mode_note("cid-12345678")
        self.assertIn("ai_speek", text)
        self.assertIn("必须", text)
        self.assertIn("陛下", text)
        self.assertIn("臣妾", text)
        self.assertIn("温婉", text)
        self.assertTrue(note.startswith("## 当前模式"))
        self.assertNotIn("## Todo-List：**必须实时追踪并更新任务进度**", note)
        self.assertLess(note.index("## 当前模式"), note.index("## AI说话"))
        self.assertIn(text, note)

    def test_publisher_tracks_connections(self) -> None:
        publisher = self.app.context.get(SERVICE_PLUGIN_EVENTS)
        self.assertFalse(publisher.connected())
        classic = self.app.context.get(SERVICE_CLASSIC_ADAPTER)
        box = classic.attach()
        try:
            self.assertTrue(publisher.connected())
            self.assertEqual(
                publisher("ai_cosplay", "stop", {"conversation_id": "cid-12345678"}),
                1,
            )
            self.assertEqual(box.get_nowait()["type"], "plugin_event")
        finally:
            classic.detach(box)

    def test_unload_clears_everything(self) -> None:
        self.app.plugin_host.unload("ai_cosplay")
        self.assertEqual(self.app.plugin_host.loaded_names(), ["web_ui"])
        self.assertIsNone(self.app.registry.get("ai_speek"))
        contribs = self.app.plugin_host.contributions
        self.assertEqual(contribs.routes_of("ai_cosplay"), [])
        self.assertIsNone(self.app.plugin_host.runtime("ai_cosplay"))


if __name__ == "__main__":
    unittest.main()
