# -*- coding: utf-8 -*-
"""压缩 build-context 插口的替换与回退测试。"""
from __future__ import annotations

import unittest

from agent.capabilities.slot_registry import SlotRegistry
from agent.mechanisms.compaction.compactor import (
    BUILD_CONTEXT_PATH,
    POLICY_PATH,
    SUMMARIZE_PATH,
    ContextCompactor,
)


class CompactionSlotTest(unittest.TestCase):
    def test_replace_build_context_and_restore(self) -> None:
        slots = SlotRegistry()
        compactor = ContextCompactor(slots=slots)
        messages = [{"role": "user", "content": "old"}]
        baseline = compactor.build_context(messages)
        binding = slots.bind(
            BUILD_CONTEXT_PATH,
            lambda rows, note="": [{"role": "system", "content": "new"}],
            owner="plugin",
            mode="replace",
        )
        self.assertEqual(
            compactor.build_context(messages),
            [{"role": "system", "content": "new"}],
        )
        binding.dispose()
        self.assertEqual(compactor.build_context(messages), baseline)

    def test_instances_do_not_share_default_policy_or_summarizer(self) -> None:
        slots = SlotRegistry()
        calls = []

        def first(*args, **kwargs):
            calls.append("first")
            return "first summary"

        def second(*args, **kwargs):
            calls.append("second")
            return "second summary"

        c1 = ContextCompactor(first, full_user_rounds=2, slots=slots)
        c2 = ContextCompactor(second, full_user_rounds=5, slots=slots)
        context = type("Context", (), {"system_text": lambda self: ""})()
        self.assertIs(c1._policy_view(), c1._policy)
        self.assertIs(c2._policy_view(), c2._policy)
        self.assertEqual(c1._policy_view().full_user_rounds, 2)
        self.assertEqual(c2._policy_view().full_user_rounds, 5)
        self.assertEqual(c1._summary_body([], [], context, []), "first summary")
        self.assertEqual(c2._summary_body([], [], context, []), "second summary")
        self.assertEqual(calls, ["first", "second"])

    def test_replace_summarize_and_policy(self) -> None:
        slots = SlotRegistry()
        compactor = ContextCompactor(slots=slots)
        summary = slots.bind(
            SUMMARIZE_PATH, lambda *args, **kwargs: "new summary",
            owner="plugin", mode="replace")
        policy = slots.bind(
            POLICY_PATH, object(), owner="plugin", mode="replace")
        context = type("Context", (), {"system_text": lambda self: ""})()
        body = compactor._summary_body([], [], context, [])
        self.assertEqual(body, "new summary")
        self.assertIs(compactor._policy_view(), policy.implementation)
        summary.dispose()
        policy.dispose()


if __name__ == "__main__":
    unittest.main()
