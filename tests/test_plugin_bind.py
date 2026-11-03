# -*- coding: utf-8 -*-
"""插件通过公开 API 绑定任意暴露 slot。"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from agent.capabilities.plugin_context import PluginContext
from agent.capabilities.registry import ToolRegistry
from agent.capabilities.slot_registry import SlotRegistry, route_slot_path


class PluginBindTest(unittest.TestCase):
    def test_bind_route_slot(self) -> None:
        slots = SlotRegistry()
        ctx = PluginContext("probe", ToolRegistry(), host=SimpleNamespace(slots=slots))
        binding = ctx.bind_route(
            "GET", "/probe",
            lambda handler, query, body=None: (200, {"ok": True}))
        key = route_slot_path("GET", "/probe")
        self.assertEqual(slots.resolve(key)(None, {})[1], {"ok": True})
        binding()
        self.assertEqual([b.owner for b in slots.bindings_of(key)], [])

    def test_bind_route_uses_canonical_key(self) -> None:
        slots = SlotRegistry()
        ctx = PluginContext("probe", ToolRegistry(), host=SimpleNamespace(slots=slots))
        ctx.bind_route("POST", "/api/chat/send",
                       lambda handler, query, body=None: (200, {"ok": True}))
        key = route_slot_path("POST", "/api/chat/send")
        self.assertIn(key, slots.nodes)
        self.assertEqual(slots.resolve(key)(None, {}, {})[1], {"ok": True})

    def test_bind_unknown_path_rejected(self) -> None:
        ctx = PluginContext("probe", ToolRegistry(),
                            host=SimpleNamespace(slots=SlotRegistry()))
        with self.assertRaises(ValueError):
            ctx.bind("app/not/exposed", lambda: None)


if __name__ == "__main__":
    unittest.main()
