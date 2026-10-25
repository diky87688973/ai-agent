# -*- coding: utf-8 -*-
"""拆分后 helper 的回归：终止事件、模型流、工具取消、图片配额。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.core.host import Host  # noqa: E402
from agent.core.image_embed import (  # noqa: E402
    _image_positions,
    _select_images,
    _strip_unselected,
    strip_old_images,
)
from agent.core.model_call import StreamDelta  # noqa: E402
from agent.core.modules.model_mod import ModelModule  # noqa: E402
from agent.core.modules.tool_mod import ToolModule  # noqa: E402
from agent.core.ports import Ports  # noqa: E402
from agent.core.session_log import SessionLog  # noqa: E402
from agent.core.tool_call import ToolCallRequest, ToolResult  # noqa: E402


class HostEventHelperTest(unittest.TestCase):
    def setUp(self) -> None:
        self.host = Host([], sink=lambda _event: None)
        self.log = SessionLog()

    def test_cancel_and_max_pass_events(self) -> None:
        event = self.host._cancel_event(self.log, "cid", 2)
        self.assertEqual(event.type, "turn_ended")
        self.assertTrue(event.data["stopped"])
        self.assertEqual(self.host.last_result.reason, "stopped")
        event = self.host._max_passes_event(self.log, "cid", 3)
        self.assertEqual(event.type, "turn_ended")
        self.assertTrue(event.data["halted"])
        self.assertEqual(self.host.last_result.reason, "max_passes")

    def test_terminal_event_covers_all_three_states(self) -> None:
        result = SimpleNamespace(
            terminal=SimpleNamespace(status="suspend", reason="需要输入"))
        event = self.host._terminal_event(result, self.log, "cid", 1)
        self.assertTrue(event.data["paused"])
        self.assertEqual(self.host.last_result.reason, "suspended")
        result.terminal.status = "stopped"
        event = self.host._terminal_event(result, self.log, "cid", 1)
        self.assertTrue(event.data["stopped"])
        result.terminal.status = "halted"
        event = self.host._terminal_event(result, self.log, "cid", 1)
        self.assertTrue(event.data["halted"])


class _Model:
    def __init__(self, deltas=None, error: Exception | None = None) -> None:
        self._deltas = list(deltas or [])
        self._error = error

    def name_for(self, _request) -> str:
        return "fake"

    def stream(self, _request):
        if self._error is not None:
            raise self._error
        yield from self._deltas


class _Tool:
    def schemas(self):
        return []


def _ports(events: list, cancel=None) -> Ports:
    return Ports(
        emit=events.append, log=SessionLog(), conversation_id="cid",
        tools=_Tool(), cancel=cancel,
    )


def _drain(generator):
    try:
        while True:
            next(generator)
    except StopIteration as exc:
        return exc.value
    raise AssertionError("generator did not finish")


class ModelHelperTest(unittest.TestCase):
    def _module(self) -> ModelModule:
        return ModelModule()

    def test_build_request_without_context(self) -> None:
        events: list = []
        module = self._module()
        request, messages, segments = module._build_request(_ports(events))
        self.assertEqual(messages, [])
        self.assertIsNone(segments)
        self.assertEqual(request.conversation_id, "cid")

    def test_stream_parts_usage_and_tool_calls(self) -> None:
        events: list = []
        call = ToolCallRequest(call_id="c1", name="echo", arguments={"x": 1})
        model = _Model([
            StreamDelta(kind="reasoning", text="想"),
            StreamDelta(kind="text", text="答"),
            StreamDelta(kind="tool_call", tool_call=call),
            StreamDelta(kind="meta", meta={"provider": {"k": 1}}),
            StreamDelta(kind="usage", usage={"input_tokens": 3}),
        ])
        module = self._module()
        ports = _ports(events)
        request, _messages, _segments = module._build_request(ports)
        state = _drain(module._stream(ports, model, request))
        self.assertEqual(state["text_parts"], ["答"])
        self.assertEqual(state["reasoning_parts"], ["想"])
        self.assertEqual(len(state["tool_calls"]), 1)
        self.assertTrue(any(e.type == "usage" for e in events))

    def test_stream_failure_returns_state(self) -> None:
        events: list = []
        module = self._module()
        ports = _ports(events)
        request, _messages, _segments = module._build_request(ports)
        state = _drain(module._stream(ports, _Model(error=RuntimeError("boom")), request))
        self.assertIn("RuntimeError", state["failure"])
        self.assertTrue(any(e.type == "llm_failed" for e in events))

    def test_stream_cancel_returns_stopped(self) -> None:
        events: list = []
        module = self._module()
        ports = _ports(events, cancel=lambda: True)
        request, _messages, _segments = module._build_request(ports)
        state = _drain(module._stream(
            ports, _Model([StreamDelta(kind="text", text="答")]), request))
        self.assertTrue(state["stopped"])
        self.assertTrue(any(e.type == "llm_failed" for e in events))


class ToolHelperTest(unittest.TestCase):
    def test_cancel_rest_emits_pair_for_every_call(self) -> None:
        events: list = []
        module = ToolModule()
        pending = [SimpleNamespace(call_id="a", name="x"),
                   SimpleNamespace(call_id="b", name="y")]
        list(module._cancel_rest(_ports(events), pending, 1, "user_stop"))
        self.assertEqual([e.type for e in events], ["tool_canceled", "tool_ended"])

    def test_result_events_cover_success_and_failure(self) -> None:
        events: list = []
        module = ToolModule()
        call = ToolCallRequest(call_id="c", name="echo", arguments={})
        list(module._result_events(
            _ports(events), call,
            ToolResult(call_id="c", ok=True, data={"x": 1}), 3, True))
        self.assertEqual(events[-1].data["status"], "done")
        list(module._result_events(
            _ports(events), call,
            ToolResult(call_id="c", ok=False, error="bad"), 4, False))
        self.assertEqual(events[-1].data["status"], "failed")


class ImageHelperTest(unittest.TestCase):
    def _image(self, data: str = "A") -> dict:
        return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}}

    def test_positions_select_and_strip(self) -> None:
        messages = [
            {"role": "user", "content": [self._image("A"), self._image("B")]},
            {"role": "assistant", "content": "ok"},
            {"role": "tool", "content": [self._image("C")]},
        ]
        positions = _image_positions(messages, "user")
        tools = _image_positions(messages, "tool")
        self.assertEqual(positions, [0])
        self.assertEqual(tools, [2])
        keep = _select_images(messages, positions, tools, 1, 1)
        out, stripped = _strip_unselected(messages, keep)
        self.assertEqual(stripped, 2)
        self.assertEqual(len(_image_positions([out[0]], "user")), 1)
        self.assertEqual(_image_positions([out[2]], "tool"), [])

    def test_strip_old_images_negative_limits(self) -> None:
        messages = [{"role": "user", "content": [self._image()]}]
        out, stripped = strip_old_images(messages, keep_turns=-1, max_images=-1)
        self.assertEqual(out, messages)
        self.assertEqual(stripped, 0)


if __name__ == "__main__":
    unittest.main()
