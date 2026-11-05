# -*- coding: utf-8 -*-
"""write_path_keys：只认工具声明 + 注册表查找；卸工具后解析不到路径。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.capabilities.registry import ToolPlugin, ToolRegistry  # noqa: E402
from agent.mechanisms.quality import QualityGate, resolve_write_path  # noqa: E402


class _KeyedTool(ToolPlugin):
    name = "keyed_write_tool"
    description = "带写路径键的假工具"
    parameters: dict = {}
    needs_preview = True
    write_path_keys = ("dest", "alt")

    def execute(self, arguments):
        return {}


class WritePathKeysLifecycleTest(unittest.TestCase):
    def test_resolve_uses_declared_keys_not_default_path(self) -> None:
        args = {"path": "/wrong", "dest": "/right", "alt": "/other"}
        self.assertEqual(resolve_write_path(args, ("dest", "alt")), "/right")
        self.assertEqual(resolve_write_path(args, ()), "")
        self.assertEqual(resolve_write_path(args, ("missing",)), "")

    def test_gate_lookup_tracks_registry(self) -> None:
        reg = ToolRegistry()
        gate = QualityGate(
            path_keys_for=lambda n: tuple(
                getattr(reg.get(n), "write_path_keys", ()) or ()
            )
            if reg.get(n) is not None
            else ()
        )
        self.assertEqual(gate.path_keys("keyed_write_tool"), ())
        dispose = reg.register(_KeyedTool())
        self.assertEqual(gate.path_keys("keyed_write_tool"), ("dest", "alt"))
        cid = gate.register_preview(
            "keyed_write_tool", {"dest": "a.txt", "path": "ignored.txt"}
        )
        self.assertEqual(gate.peek(cid)["path"], "a.txt")
        dispose()
        self.assertEqual(gate.path_keys("keyed_write_tool"), ())

    def test_register_then_dispose_drops_tool_from_registry(self) -> None:
        """工具的注册与撤销：注册后查得到，dispose 后查不到。"""
        reg = ToolRegistry()
        dispose = reg.register(_KeyedTool())
        self.assertIsNotNone(reg.get("keyed_write_tool"), "注册后应能查到工具")
        dispose()
        self.assertIsNone(reg.get("keyed_write_tool"), "撤销后查不到")

    def test_drop_plugin_removes_skills_from_registry(self) -> None:
        """skills 工具由片段声明：装配后在注册表里，卸载后从注册表消失。"""
        from agent.app import build_app
        from tests.testkit import isolate_data

        isolate_data(self)
        app = build_app()
        self.addCleanup(app.dispose)
        reg = app.registry
        plugin = reg.get("skills")
        self.assertIsNotNone(plugin)
        self.assertEqual(tuple(getattr(plugin, "write_path_keys", ()) or ()), ())
        app.plugin_host.unload("skills")
        self.assertIsNone(reg.get("skills"))


if __name__ == "__main__":
    unittest.main()
