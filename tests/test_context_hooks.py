# -*- coding: utf-8 -*-
"""完整上下文拼装钩子。"""
from __future__ import annotations

import unittest

from agent.mechanisms.context.hooks import ContextAssemblyHooks


class ContextAssemblyHooksTest(unittest.TestCase):
    def test_hook_receives_full_context_and_can_replace_it(self) -> None:
        hooks = ContextAssemblyHooks()
        seen = {}

        def hook(messages, cid):
            seen["cid"] = cid
            return [*messages, {"role": "user", "content": "visual"}]

        disposer = hooks.add(hook)
        result = hooks.apply([{"role": "user", "content": "hi"}], "cid-1")
        self.assertEqual(result[-1]["content"], "visual")
        self.assertEqual(seen["cid"], "cid-1")
        disposer()
        self.assertEqual(
            hooks.apply([{"role": "user", "content": "hi"}], "cid-1"),
            [{"role": "user", "content": "hi"}],
        )

    def test_invalid_result_is_ignored(self) -> None:
        hooks = ContextAssemblyHooks()
        hooks.add(lambda messages, cid: "bad")
        result = hooks.apply([{"role": "user", "content": "hi"}], "cid")
        self.assertEqual(result, [{"role": "user", "content": "hi"}])

    def test_hooks_run_in_order(self) -> None:
        hooks = ContextAssemblyHooks()
        hooks.add(lambda messages, cid: [*messages, {"role": "user", "content": "a"}])
        hooks.add(lambda messages, cid: [*messages, {"role": "user", "content": "b"}])
        result = hooks.apply([{"role": "user", "content": "start"}], "cid")
        self.assertEqual([m["content"] for m in result], ["start", "a", "b"])


if __name__ == "__main__":
    unittest.main()
