# -*- coding: utf-8 -*-
"""工具管道 slot 的替换与回退。"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from agent.capabilities.slot_registry import SlotRegistry
from agent.core.tool_call import PIPELINE_PATH, ToolCallRequest, ToolPipeline, ToolResult


class _Registry:
    def get(self, name):
        return None


class ToolPipelineSlotTest(unittest.TestCase):
    def test_replace_pipeline(self) -> None:
        slots = SlotRegistry()
        pipeline = ToolPipeline(slots)
        call = ToolCallRequest(call_id="c1", name="missing")
        ctx = SimpleNamespace(conversation_id="")
        default = pipeline.execute(_Registry(), call, ctx)
        self.assertFalse(default.ok)
        binding = slots.bind(
            PIPELINE_PATH,
            lambda registry, call, ctx: ToolResult(call_id=call.call_id, ok=True,
                                                    data={"new": True}),
            owner="plugin",
            mode="replace",
        )
        self.assertTrue(pipeline.execute(_Registry(), call, ctx).ok)
        binding.dispose()
        self.assertFalse(pipeline.execute(_Registry(), call, ctx).ok)


if __name__ == "__main__":
    unittest.main()
