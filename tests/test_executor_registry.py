# -*- coding: utf-8 -*-
"""执行器 leaf 的插口绑定与回退测试。"""
from __future__ import annotations

import unittest
from unittest import mock

from agent.capabilities.builtin import commit_write
from agent.capabilities.slot_registry import SlotRegistry
from agent.mechanisms.executors import ExecutorRegistry


def _executor(tag: str):
    return lambda arguments: {"tag": tag, "arguments": dict(arguments)}


class ExecutorSlotTest(unittest.TestCase):
    def setUp(self) -> None:
        self.slots = SlotRegistry()
        self.registry = ExecutorRegistry(self.slots)
        self.registry.add("write_file", _executor("old"), "host")

    def test_replace_and_restore(self) -> None:
        binding = self.registry.replace("write_file", _executor("new"), "plugin")
        self.assertEqual(self.registry.get("write_file")({"a": 1})["tag"], "new")
        binding.dispose()
        self.assertEqual(self.registry.get("write_file")({"a": 1})["tag"], "old")

    def test_add_with_replace_option(self) -> None:
        self.registry.add("write_file", _executor("new"), "plugin", replace=True)
        self.assertEqual(self.registry.get("write_file")({})["tag"], "new")

    def test_names_lists_replaced_executor_slots(self) -> None:
        self.registry.replace("archive", _executor("new"), "plugin")
        self.assertIn("archive", self.registry.names())
        self.assertIn("write_file", self.registry.names())

    def test_commit_write_prefers_replaced_executor(self) -> None:
        static = {"write_file": _executor("static")}
        tool = commit_write.build(static, self.registry)
        self.registry.replace("write_file", _executor("new"), "plugin")
        gate = mock.Mock()
        record = {"tool": "write_file", "arguments": {}}
        gate.peek.return_value = record
        gate.take_record.return_value = record
        with mock.patch.object(commit_write, "session_gate", return_value=gate):
            result = tool.execute({"confirm_id": "cid"})
        self.assertEqual(result["tag"], "new")


if __name__ == "__main__":
    unittest.main()
