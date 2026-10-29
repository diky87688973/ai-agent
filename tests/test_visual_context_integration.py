# -*- coding: utf-8 -*-
"""内核上下文钩子在模型请求组装阶段的接入。"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from agent.core.engine import Engine
from agent.core.events import Event
from agent.core.modules.model_mod import ModelModule
from agent.mechanisms.context.hooks import ContextAssemblyHooks


class _Log:
    def derive_request_messages(self):
        return [{"role": "user", "content": "hi"}]


class _Tools:
    def schemas(self):
        return []


class ModelHookIntegrationTest(unittest.TestCase):
    def test_hook_output_enters_request_messages(self) -> None:
        hooks = ContextAssemblyHooks()
        hooks.add(lambda messages, cid: [*messages, {
            "role": "user", "content": "visual"}])
        module = ModelModule(context_hooks=hooks)
        ports = SimpleNamespace(
            log=_Log(), tool_port=_Tools(), conversation_id="cid")
        request, messages, _segments = module._build_request(ports)
        self.assertEqual(messages[-1]["content"], "visual")
        self.assertEqual(request.messages[-1]["content"], "visual")

    def test_engine_keeps_plugin_request_id_in_pending(self) -> None:
        engine = object.__new__(Engine)
        engine.session_context = SimpleNamespace(pending_confirm=None)
        engine._remember_suspend(Event("tool_suspended", {
            "call_id": "call-1",
            "envelope": {
                "kind": "vision_consent",
                "title": "title",
                "confirms": ["同意", "拒绝"],
                "request_id": "req-1",
                "conversation_id": "cid",
            },
        }))
        pending = engine.session_context.pending_confirm
        self.assertEqual(pending["call_id"], "call-1")
        self.assertEqual(pending["request_id"], "req-1")
        self.assertEqual(pending["conversation_id"], "cid")


if __name__ == "__main__":
    unittest.main()
