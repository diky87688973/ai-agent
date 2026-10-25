# -*- coding: utf-8 -*-
"""请求尾部注册表：顺序、幂等撤销、来源异常隔离。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.mechanisms.prompt_tail import PromptTail  # noqa: E402


class PromptTailTest(unittest.TestCase):
    def test_renders_in_registration_order_and_disposes_idempotently(self) -> None:
        tail = PromptTail()
        first = tail.add(lambda _cid: "first")
        tail.add(lambda _cid: "second")
        self.assertEqual(tail.render("cid"), "first\n\nsecond")
        first()
        first()
        self.assertEqual(tail.render("cid"), "second")

    def test_failing_source_does_not_block_other_sources(self) -> None:
        tail = PromptTail()
        def boom(_cid: str) -> str:
            raise RuntimeError("boom")
        tail.add(boom)
        tail.add(lambda _cid: "ok")
        self.assertEqual(tail.render("cid"), "ok")

    def test_subagent_hidden_source_is_not_rendered(self) -> None:
        tail = PromptTail()
        tail.add(lambda _cid: "parent only", subagent_visible=False)
        tail.add(lambda _cid: "everyone")
        self.assertEqual(tail.render("cid", is_subagent=True), "everyone")
        self.assertEqual(tail.render("cid"), "parent only\n\neveryone")

    def test_empty_source_does_not_add_separator(self) -> None:
        tail = PromptTail()
        tail.add(lambda _cid: " ")
        tail.add(lambda _cid: "text")
        self.assertEqual(tail.render("cid"), "text")

    def test_non_callable_source_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PromptTail().add("nope")


if __name__ == "__main__":
    unittest.main()
