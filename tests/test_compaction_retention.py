# -*- coding: utf-8 -*-
"""压缩摘要保留最近轮次及逐级降级回归。"""
from __future__ import annotations

import unittest
from typing import Any

from agent.core.model_call import StreamDelta
from agent.mechanisms.compaction.compactor import (
    CHECKPOINT_PREAMBLE,
    SUMMARY_OPEN_TAG,
    ContextCompactor,
    make_provider_summarizer,
)
from agent.mechanisms.context import ContextPipeline


class _Spy:
    def __init__(self, text: str = "NEW SUMMARY") -> None:
        self.reqs = []
        self.text = text

    def stream(self, request: Any):
        self.reqs.append(request)
        yield StreamDelta(kind="text", text=self.text)
        yield StreamDelta(kind="done")


def _rounds(count: int, *, start: int = 1) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for index in range(start, start + count):
        out.extend([
            {"role": "user", "content": f"PAST-{index}"},
            {"role": "assistant", "content": f"ANSWER-{index}"},
        ])
    return out


def _text(value: Any) -> str:
    return "\n".join(str(message.get("content") or "") for message in value)


class CompactionRetentionTest(unittest.TestCase):
    def test_summary_request_and_reassembly_keep_recent_five_once(self) -> None:
        messages = _rounds(8)
        pipe = ContextPipeline("retention-five", full_user_rounds=5)
        pipe.append_system("SYSTEM")
        pipe.set_dialogue(messages, covered_end=0)
        tail = [{"role": "user", "content": "CURRENT INPUT"}]
        assembled = pipe.assembles(tail)
        spy = _Spy()
        compactor = ContextCompactor(
            make_provider_summarizer(spy, max_chars=200),
            summary_token_threshold=1,
            full_user_rounds=5,
        )

        report = compactor.ensure_before_append(
            pipe, messages, mode_note="", assembled=assembled,
        )

        self.assertIsNotNone(report)
        self.assertEqual(compactor.covered_end, 6)
        request_text = _text(spy.reqs[0].messages)
        for index in (1, 2, 3):
            self.assertIn(f"PAST-{index}", request_text)
        for index in range(4, 9):
            self.assertNotIn(f"PAST-{index}", request_text)
        self.assertNotIn("CURRENT INPUT", request_text)

        pipe.set_summary_messages(compactor.summary_messages())
        pipe.set_dialogue(messages, covered_end=compactor.covered_end)
        rendered = _text(pipe.assembles(tail))
        for index in range(4, 9):
            self.assertEqual(rendered.count(f"PAST-{index}"), 1)
        self.assertEqual(rendered.count("NEW SUMMARY"), 1)
        self.assertEqual(rendered.count(CHECKPOINT_PREAMBLE), 1)

    def test_configured_width_falls_only_until_one_round_can_be_compacted(self) -> None:
        messages = _rounds(5)
        pipe = ContextPipeline("retention-drop", full_user_rounds=5)
        pipe.set_dialogue(messages, covered_end=0)
        assembled = pipe.assembles([])
        spy = _Spy()
        compactor = ContextCompactor(
            make_provider_summarizer(spy, max_chars=200),
            summary_token_threshold=1,
            full_user_rounds=5,
        )

        report = compactor.ensure_before_append(
            pipe, messages, assembled=assembled,
        )

        self.assertIsNotNone(report)
        self.assertEqual(compactor.covered_end, 2)
        self.assertEqual(
            sum(1 for message in messages[compactor.covered_end:]
                if message.get("role") == "user"),
            4,
        )
        self.assertNotIn("PAST-2", _text(spy.reqs[0].messages))

    def test_one_round_is_the_floor_and_is_not_compacted(self) -> None:
        messages = _rounds(1)
        pipe = ContextPipeline("retention-floor", full_user_rounds=5)
        pipe.set_dialogue(messages, covered_end=0)
        assembled = pipe.assembles([])
        spy = _Spy()
        compactor = ContextCompactor(
            make_provider_summarizer(spy, max_chars=200),
            summary_token_threshold=1,
            full_user_rounds=5,
        )

        report = compactor.ensure_before_append(
            pipe, messages, assembled=assembled,
        )

        self.assertIsNone(report)
        self.assertEqual(compactor.covered_end, 0)
        self.assertEqual(spy.reqs, [])

    def test_consecutive_compactions_do_not_duplicate_summary_or_recent_rounds(self) -> None:
        messages = _rounds(7)
        pipe = ContextPipeline("retention-twice", full_user_rounds=3)
        pipe.set_dialogue(messages, covered_end=0)
        spy = _Spy("SUMMARY-1")
        compactor = ContextCompactor(
            make_provider_summarizer(spy, max_chars=200),
            summary_token_threshold=1,
            full_user_rounds=3,
        )

        first = compactor.ensure_before_append(
            pipe, messages, assembled=pipe.assembles([]),
        )
        self.assertIsNotNone(first)
        self.assertEqual(compactor.covered_end, 8)

        pipe.set_summary_messages(compactor.summary_messages())
        pipe.set_dialogue(messages, covered_end=compactor.covered_end)
        spy.text = "SUMMARY-2"
        second = compactor.ensure_before_append(
            pipe, messages, assembled=pipe.assembles([]),
        )
        self.assertIsNotNone(second)
        self.assertEqual(compactor.covered_end, 10)

        second_request = _text(spy.reqs[1].messages)
        self.assertIn("SUMMARY-1", second_request)
        self.assertIn("PAST-5", second_request)
        self.assertNotIn("PAST-6", second_request)
        self.assertNotIn("PAST-7", second_request)

        pipe.set_summary_messages(compactor.summary_messages())
        pipe.set_dialogue(messages, covered_end=compactor.covered_end)
        rendered = _text(pipe.assembles([]))
        for index in (6, 7):
            self.assertEqual(rendered.count(f"PAST-{index}"), 1)
        self.assertEqual(rendered.count(SUMMARY_OPEN_TAG), 1)
        self.assertEqual(rendered.count("SUMMARY-2"), 1)
        self.assertNotIn("PAST-1", rendered)


if __name__ == "__main__":
    unittest.main()
