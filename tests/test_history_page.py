# -*- coding: utf-8 -*-
"""历史分页纯函数：轮次、字符预算、页边界与不可变出参。"""
from __future__ import annotations

import unittest

from agent.core.events import Event
from agent.shell.classic_adapter.history_page import (
    HISTORY_PAGE_CHARS,
    fold_rounds,
    item_cost,
    select_page,
)


def _input(seq: int, text: str) -> Event:
    return Event("input_claimed", {"content": text, "_seq": seq})


def _model(seq: int, text: str) -> Event:
    return Event("model_message", {"content": text, "_seq": seq})


class ItemCostTest(unittest.TestCase):
    def test_user_and_attachments(self) -> None:
        self.assertEqual(item_cost({"role": "user", "content": "abcd"}), 4)
        self.assertEqual(item_cost({
            "role": "user", "content": "a",
            "attachments": [{"name": "image0.png"}],
        }), 1 + len("image0.png"))

    def test_tool_uses_script_args_preview_and_images(self) -> None:
        item = {
            "role": "tool", "script": "read_file",
            "args": {"path": "a"}, "preview": "{}",
            "output": "x" * 5, "images": [{"mime": "image/png"}],
        }
        self.assertGreater(item_cost(item), len("read_file") + 5)
        self.assertEqual(item_cost({"role": "tool"}), 0)


class FoldRoundsTest(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual(fold_rounds([]), [])
        page = select_page([], before=None)
        self.assertEqual(page.items, ())
        self.assertFalse(page.has_more)
        self.assertIsNone(page.next_before)

    def test_round_anchor_and_order(self) -> None:
        rounds = fold_rounds([_input(10, "甲"), _model(11, "答"), _input(20, "乙")])
        self.assertEqual([r.anchor for r in rounds], [10, 20])
        self.assertEqual([i["content"] for i in rounds[0].items], ["甲", "答"])
        self.assertEqual([i["content"] for i in rounds[1].items], ["乙"])

    def test_residual_events_before_first_input(self) -> None:
        rounds = fold_rounds([_model(1, "残"), _input(2, "问")])
        self.assertEqual([r.anchor for r in rounds], [None, 2])
        page = select_page(rounds, before=None, budget=1)
        self.assertTrue(page.has_more)
        self.assertEqual(page.next_before, 2)

    def test_tool_lifecycle_stays_in_round(self) -> None:
        rounds = fold_rounds([
            _input(1, "问"),
            Event("tool_started", {"call_id": "c1", "name": "read_file", "arguments": {}}),
            Event("tool_progress", {"call_id": "c1", "text": "x"}),
            Event("tool_done", {"call_id": "c1", "result": {"ok": True}}),
            _input(9, "下一问"),
        ])
        self.assertEqual(len(rounds), 2)
        tool = [i for i in rounds[0].items if i.get("role") == "tool"][0]
        self.assertEqual(tool["status"], "done")
        self.assertEqual(tool.get("output"), "x")

    def test_chars_equal_sum_items(self) -> None:
        rounds = fold_rounds([_input(1, "a"), _model(2, "bb")])
        self.assertEqual(rounds[0].chars, 3)


class SelectPageTest(unittest.TestCase):
    def _rounds(self, sizes):
        events = []
        seq = 1
        for text in sizes:
            events.extend([_input(seq, text), _model(seq + 1, "r")])
            seq += 2
        return fold_rounds(events)

    def test_budget_reaches_threshold_and_includes_whole_round(self) -> None:
        rounds = self._rounds(["a" * 6000, "b" * 6000, "c" * 6000])
        page = select_page(rounds, before=None, budget=10000)
        self.assertEqual(page.has_more, True)
        self.assertGreaterEqual(page.chars, 10000)
        self.assertEqual(page.items[0]["content"], "b" * 6000)
        self.assertEqual(page.next_before, rounds[-2].anchor)

    def test_single_round_over_budget_is_returned_whole(self) -> None:
        rounds = self._rounds(["x" * 20000])
        page = select_page(rounds, before=None, budget=10000)
        self.assertEqual(len(page.items), 2)
        self.assertGreater(page.chars, 10000)
        self.assertFalse(page.has_more)

    def test_before_is_exclusive(self) -> None:
        rounds = self._rounds(["a", "b", "c"])
        page = select_page(rounds, before=rounds[1].anchor)
        self.assertEqual([i["content"] for i in page.items if i["role"] == "user"], ["a"])
        self.assertFalse(page.has_more)

    def test_before_older_than_everything_returns_empty(self) -> None:
        rounds = self._rounds(["a", "b"])
        page = select_page(rounds, before=1)
        self.assertEqual(page.items, ())
        self.assertFalse(page.has_more)
        self.assertIsNone(page.next_before)

    def test_exact_before_does_not_return_that_round(self) -> None:
        rounds = self._rounds(["a", "b"])
        page = select_page(rounds, before=rounds[-1].anchor)
        texts = [i["content"] for i in page.items if i["role"] == "user"]
        self.assertEqual(texts, ["a"])

    def test_page_values_are_copies(self) -> None:
        rounds = self._rounds(["a"])
        page = select_page(rounds, before=None)
        page.items[0]["content"] = "changed"
        self.assertEqual(rounds[0].items[0]["content"], "a")
        self.assertIsInstance(page.items, tuple)

    def test_next_before_only_when_has_more(self) -> None:
        rounds = self._rounds(["a"])
        page = select_page(rounds, before=None)
        self.assertFalse(page.has_more)
        self.assertIsNone(page.next_before)

    def test_full_traversal_has_no_missing_or_duplicate_rounds(self) -> None:
        texts = [f"round-{i:02d}-" + ("x" * 1500) for i in range(12)]
        rounds = self._rounds(texts)
        seen = []
        before = None
        pages = 0
        while True:
            page = select_page(rounds, before=before)
            seen.extend(i["content"] for i in page.items if i.get("role") == "user")
            pages += 1
            if not page.has_more:
                break
            self.assertIsNotNone(page.next_before)
            self.assertLess(page.next_before, before if before is not None else 10**18)
            before = page.next_before
            self.assertLess(pages, 30)
        self.assertGreater(pages, 1)
        self.assertEqual(len(seen), len(texts))
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(set(seen), set(texts))

    def test_budget_constant(self) -> None:
        self.assertEqual(HISTORY_PAGE_CHARS, 10000)


if __name__ == "__main__":
    unittest.main()
