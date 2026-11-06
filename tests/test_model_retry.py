# -*- coding: utf-8 -*-
"""模型流层 `RemoteDisconnected` 重试的公共契约。"""
from __future__ import annotations

import unittest
from http.client import RemoteDisconnected
from unittest import mock

from agent.core.model_call import StreamDelta
from agent.core.modules import model_mod
from agent.core.modules.model_mod import ModelModule
from agent.core.ports import LogicalRequest, Ports
from agent.core.session_log import SessionLog


class _StreamModel:
    def __init__(self, *, failures: int = 0, chunk_before_error: bool = False) -> None:
        self.attempts = 0
        self.failures = int(failures)
        self.chunk_before_error = bool(chunk_before_error)
        self.on_attempt = None

    def name_for(self, _request) -> str:
        return "retry-model"

    def stream(self, _request):
        self.attempts += 1
        if callable(self.on_attempt):
            self.on_attempt(self.attempts)
        if self.attempts <= self.failures:
            if self.chunk_before_error:
                yield StreamDelta(kind="text", text="半截")
            raise RemoteDisconnected("remote peer closed")
        yield StreamDelta(kind="text", text="成功")


class _ToolPort:
    @staticmethod
    def schemas():
        return []


def _ports(events, cancel=None) -> Ports:
    return Ports(
        emit=events.append,
        log=SessionLog(),
        conversation_id="retry-cid",
        tools=_ToolPort(),
        cancel=cancel,
    )


def _drain(generator):
    try:
        while True:
            next(generator)
    except StopIteration as exc:
        return exc.value
    raise AssertionError("generator did not finish")


class RemoteDisconnectedRetryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.backoff = mock.patch.object(
            model_mod, "RETRY_BACKOFF_SECONDS", (0.0, 0.0, 0.0, 0.0, 0.0))
        self.backoff.start()
        self.addCleanup(self.backoff.stop)
        self.report = mock.patch.object(model_mod, "report_error")
        self.report.start()
        self.addCleanup(self.report.stop)

    def test_succeeds_after_five_retries(self) -> None:
        events = []
        model = _StreamModel(failures=5)
        state = _drain(ModelModule()._stream(
            _ports(events), model, LogicalRequest(messages=[], tools=[])))

        self.assertEqual(model.attempts, 6)
        self.assertEqual(state["text_parts"], ["成功"])
        self.assertEqual(state["retries"], 5)
        done = [event for event in events if event.type == "llm_done"]
        self.assertEqual(done[0].data["retries"], 5)

    def test_six_disconnects_emit_one_terminal_failure(self) -> None:
        events = []
        model = _StreamModel(failures=6)
        state = _drain(ModelModule()._stream(
            _ports(events), model, LogicalRequest(messages=[], tools=[])))

        self.assertEqual(model.attempts, 6)
        self.assertEqual(state["retries"], 5)
        self.assertIn("RemoteDisconnected", state["failure"])
        self.assertEqual(sum(event.type == "llm_failed" for event in events), 1)
        self.assertEqual(sum(event.type == "llm_ended" for event in events), 1)
        self.assertEqual(events[-1].data["status"], "failed")

    def test_does_not_retry_after_a_chunk(self) -> None:
        events = []
        model = _StreamModel(failures=1, chunk_before_error=True)
        state = _drain(ModelModule()._stream(
            _ports(events), model, LogicalRequest(messages=[], tools=[])))

        self.assertEqual(model.attempts, 1)
        self.assertEqual(state["retries"], 0)
        self.assertIn("RemoteDisconnected", state["failure"])
        self.assertTrue(any(event.type == "assistant_delta" for event in events))

    def test_cancel_during_backoff_stops_before_next_attempt(self) -> None:
        state = {"canceled": False}
        events = []
        model = _StreamModel(failures=5)
        model.on_attempt = lambda _attempt: state.__setitem__("canceled", True)

        result = _drain(ModelModule()._stream(
            _ports(events, cancel=lambda: state["canceled"]),
            model,
            LogicalRequest(messages=[], tools=[]),
        ))

        self.assertEqual(model.attempts, 1)
        self.assertTrue(result["stopped"])
        self.assertEqual(events[-1].type, "llm_ended")
        self.assertEqual(events[-1].data["status"], "canceled")
        self.assertEqual(events[-1].data["retries"], 1)

    def test_other_errors_are_not_retried(self) -> None:
        class _Broken(_StreamModel):
            def stream(self, _request):
                self.attempts += 1
                raise RuntimeError("protocol error")
                yield  # pragma: no cover

        events = []
        model = _Broken()
        state = _drain(ModelModule()._stream(
            _ports(events), model, LogicalRequest(messages=[], tools=[])))
        self.assertEqual(model.attempts, 1)
        self.assertEqual(state["retries"], 0)
        self.assertIn("RuntimeError", state["failure"])


if __name__ == "__main__":
    unittest.main()
