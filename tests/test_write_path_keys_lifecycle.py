# -*- coding: utf-8 -*-
"""write_path_keys：只认工具声明 + 注册表查找；卸工具后解析不到路径。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.capabilities.contributions import ContributionRegistry  # noqa: E402
from agent.capabilities.plugins import PluginContext, PluginHost  # noqa: E402
from agent.capabilities.registry import ToolPlugin, ToolRegistry  # noqa: E402
from agent.mechanisms.context import ContextSources  # noqa: E402
from agent.mechanisms.executors import ExecutorRegistry  # noqa: E402
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

    def test_plugin_context_rollback_drops_tool_from_registry(self) -> None:
        reg = ToolRegistry()
        ctx = PluginContext("probe", reg)

        def _register(c: PluginContext) -> None:
            c.register_tool(_KeyedTool())
            raise RuntimeError("装载中途失败")

        with self.assertRaises(RuntimeError):
            try:
                _register(ctx)
            except Exception:
                for d in reversed(list(ctx._disposers)):
                    d()
                raise
        self.assertIsNone(reg.get("keyed_write_tool"))

    def test_drop_plugin_removes_skills_from_registry(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        if not (_ROOT / "plugins" / "skills").is_dir():
            self.skipTest("无 plugins/skills")
        reg = ToolRegistry()
        host = PluginHost(
            _ROOT / "plugins",
            reg,
            event_bus=None,
            context_sources=ContextSources(),
            contributions=ContributionRegistry(),
            plugin_data_root=base / "pdata",
            executors=ExecutorRegistry(),
        )
        reports = host.load_enabled(["skills"])
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0].status, "loaded", msg=reports[0].message)
        plugin = reg.get("skills")
        self.assertIsNotNone(plugin)
        self.assertEqual(tuple(plugin.write_path_keys), ("source", "name"))
        host.unload("skills")
        self.assertIsNone(reg.get("skills"))


if __name__ == "__main__":
    unittest.main()
