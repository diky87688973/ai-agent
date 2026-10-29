# -*- coding: utf-8 -*-
"""工具参数契约：未声明的参数必须在进入工具前拒绝。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.capabilities.builtin.read_file import ReadFileTool
from agent.capabilities.registry import ToolRegistry
from agent.core.tool_call import ToolCallRequest, ToolPipeline


class ToolArgumentContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "sample.txt"
        self.path.write_text("一\n二\n三\n", encoding="utf-8")
        self.registry = ToolRegistry()
        self.registry.register(ReadFileTool())
        self.pipeline = ToolPipeline()

    def test_unknown_aliases_are_rejected_before_execution(self) -> None:
        result = self.pipeline.execute(
            self.registry,
            ToolCallRequest(call_id="c1", name="read_file", arguments={
                "path": str(self.path),
                "start_line": 1,
                "end_line": 2,
            }),
            None,
        )
        self.assertFalse(result.ok)
        self.assertIn("start_line", result.error)
        self.assertIn("end_line", result.error)
        self.assertIn("line_start", result.error)
        self.assertIn("line_end", result.error)

    def test_session_create_has_one_name_parameter(self) -> None:
        from agent.capabilities.builtin.session_tools import SessionCreateTool

        self.assertIn("name", SessionCreateTool.parameters)
        self.assertNotIn("name_prefix", SessionCreateTool.parameters)

    def test_empty_schema_rejects_every_argument(self) -> None:
        class _NoArgs:
            name = "no_args"
            description = "无参数工具"
            parameters: dict = {}

            def execute(self, arguments):
                raise AssertionError("不应执行")

        registry = ToolRegistry()
        registry.register(_NoArgs())
        result = self.pipeline.execute(
            registry,
            ToolCallRequest(call_id="c3", name="no_args", arguments={"path": "x"}),
            None,
        )
        self.assertFalse(result.ok)
        self.assertIn("path", result.error)

    def test_business_failure_does_not_double_wrap_ok(self) -> None:
        class _Failing:
            name = "failing"
            description = "失败工具"
            parameters = {
                "value": {"type": "integer"},
            }

            def execute(self, arguments):
                return {"ok": False, "error": "业务失败"}

        registry = ToolRegistry()
        registry.register(_Failing())
        result = self.pipeline.execute(
            registry,
            ToolCallRequest(call_id="c4", name="failing", arguments={"value": 1}),
            None,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "业务失败")
        self.assertIsNone(result.data)

    def test_declared_arguments_still_work(self) -> None:
        result = self.pipeline.execute(
            self.registry,
            ToolCallRequest(call_id="c2", name="read_file", arguments={
                "path": str(self.path),
                "line_start": 1,
                "line_end": 2,
            }),
            None,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.data["content"], "一\n二")


if __name__ == "__main__":
    unittest.main()
