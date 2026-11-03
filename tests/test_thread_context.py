# -*- coding: utf-8 -*-
"""线程启动时继承当前执行快照。"""
from __future__ import annotations

import unittest

from agent.capabilities.slot_registry import SlotRegistry
from agent.core.thread_context import thread_with_context


class ThreadContextTest(unittest.TestCase):
    def test_thread_inherits_execution_snapshot(self) -> None:
        slots = SlotRegistry()
        path = "app/test/thread"
        slots.register_slot(path, default=lambda: "old")
        seen = []
        with slots.execution_snapshot():
            slots.bind(path, lambda: "new", owner="plugin")
            thread = thread_with_context(target=lambda: seen.append(slots.resolve(path)()))
            thread.start()
            thread.join(2)
        self.assertEqual(seen, ["old"])


if __name__ == "__main__":
    unittest.main()
