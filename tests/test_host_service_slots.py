# -*- coding: utf-8 -*-
"""宿主服务路径的替换与恢复测试。"""
from __future__ import annotations

import unittest

from agent.capabilities.slot_registry import SlotRegistry
from agent.core.context import AppContext


class HostServiceSlotTest(unittest.TestCase):
    def test_replace_service_and_restore(self) -> None:
        slots = SlotRegistry()
        context = AppContext(slots)
        context.register("svc", "old")
        self.assertEqual(context.get("svc"), "old")
        binding = slots.bind(
            "app/host/services/svc", "new", owner="plugin",
            mode="replace")
        self.assertEqual(context.get("svc"), "new")
        binding.dispose()
        self.assertEqual(context.get("svc"), "old")

    def test_dispose_removes_default_slot(self) -> None:
        slots = SlotRegistry()
        context = AppContext(slots)
        disposer = context.register("svc", "old")
        disposer()
        self.assertNotIn("app/host/services/svc", slots.nodes)
        with self.assertRaises(KeyError):
            context.get("svc")


if __name__ == "__main__":
    unittest.main()
