# -*- coding: utf-8 -*-
"""压缩请求必须复用上一次正常请求的精确前缀。"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from agent.core.model_call import StreamDelta
from agent.core.modules.model_mod import ModelModule
from agent.mechanisms.compaction.compactor import ContextCompactor, make_provider_summarizer
from agent.mechanisms.context import ContextPipeline
from agent.mechanisms.context.hooks import ContextAssemblyHooks


class _Log:
    def derive_request_messages(self):
        return [{"role": "user", "content": "hi"}]


class _Tools:
    def schemas(self):
        return [{"name": "read_file"}]


class _Spy:
    def __init__(self, text="new summary"):
        self.reqs = []
        self._text = text

    def stream(self, request):
        self.reqs.append(request)
        yield StreamDelta(kind="text", text=self._text)
        yield StreamDelta(kind="done")


class _SnapshotSink:
    def __init__(self):
        self.messages = None
        self.prefix = None
        self.tools = None

    def remember_sent_request(self, messages, prefix, tools):
        self.messages = list(messages)
        self.prefix = list(prefix)
        self.tools = list(tools)

    @property
    def summary_token_threshold(self):
        return 1


class CompactionPrefixTest(unittest.TestCase):
    def test_model_module_records_prefix_before_hook_tail(self) -> None:
        sink = _SnapshotSink()
        hooks = ContextAssemblyHooks()
        hooks.add(lambda messages, cid: [*messages, {
            "role": "user", "content": "visual frame"}])
        module = ModelModule(context_hooks=hooks, compactor=sink)
        ports = SimpleNamespace(log=_Log(), tool_port=_Tools(), conversation_id="cid")
        request, messages, _segments = module._build_request(ports)
        self.assertEqual(sink.messages, messages)
        self.assertEqual(sink.prefix, [{"role": "user", "content": "hi"}])
        self.assertEqual(sink.tools, request.tools)
        self.assertEqual(messages[-1]["content"], "visual frame")
        self.assertNotIn("visual frame", str(sink.prefix))

    def test_compaction_request_is_prefix_plus_user_instruction(self) -> None:
        pipe = ContextPipeline("cid-prefix-0001")
        pipe.append_system("system")
        pipe.set_summary_messages([{"role": "user", "content": "old summary"}])
        pipe.set_dialogue([
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
        ], covered_end=0)
        tail = [{"role": "user", "content": "new input"},
                {"role": "system", "content": "## current mode"}]
        whole = pipe.assembles(tail)
        prefix = whole[:len(whole) - len(tail)]
        tools = [{"name": "read_file"}]
        spy = _Spy()
        comp = ContextCompactor(make_provider_summarizer(spy, max_chars=200),
                                summary_token_threshold=1)
        comp.remember_sent_request(whole, prefix, tools)
        report = comp.ensure_before_append(
            pipe, [{"role": "user", "content": "q1"},
                   {"role": "assistant", "content": "a1"}],
            tools=tools, mode_note="## current mode", assembled=whole)
        self.assertIsNotNone(report)
        req = spy.reqs[0]
        self.assertEqual(req.messages[:-1], prefix)
        self.assertEqual(req.messages[-1]["role"], "user")
        self.assertIn("压缩引擎", req.messages[-1]["content"])
        self.assertIn("Markdown", req.messages[-1]["content"])
        self.assertIn("## ", req.messages[-1]["content"])
        self.assertIn("- ", req.messages[-1]["content"])
        self.assertEqual(req.tools, tools)

    def test_no_snapshot_falls_back_without_claiming_hit(self) -> None:
        pipe = ContextPipeline("cid-prefix-0002")
        pipe.append_system("system")
        pipe.set_dialogue([
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
        ], covered_end=0)
        whole = pipe.assembles([])
        spy = _Spy()
        comp = ContextCompactor(make_provider_summarizer(spy, max_chars=200),
                                summary_token_threshold=1)
        report = comp.ensure_before_append(
            pipe, list(whole), tools=[], mode_note="", assembled=whole)
        self.assertIsNotNone(report)
        self.assertTrue(spy.reqs)
        self.assertEqual(spy.reqs[0].messages[-1]["role"], "user")


if __name__ == "__main__":
    unittest.main()
