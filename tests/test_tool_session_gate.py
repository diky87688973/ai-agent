# -*- coding: utf-8 -*-
"""ToolPort.execute 把会话桶填进管道：current_context().session.gate 即 resolve_sync 的门控。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.app import build_app  # noqa: E402
from agent.capabilities.registry import ToolPlugin  # noqa: E402
from agent.core.ports import ToolPort  # noqa: E402
from agent.core.session_scope import current_context  # noqa: E402
from agent.core.tool_call import ToolCallRequest  # noqa: E402


class _GateProbe(ToolPlugin):
    name = "_gate_probe"
    description = "capture session.gate"
    parameters: dict = {}
    seen_gate = None

    def execute(self, arguments: dict):
        ctx = current_context()
        type(self).seen_gate = ctx.session.gate if ctx is not None and ctx.session else None
        return {"ok": True}


class ToolSessionGateTest(unittest.TestCase):
    """经 ToolPort 执行时，工具所见 gate 与会话注册表一致。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.app = build_app()
        self.port = ToolPort(
            registry=self.app.registry,
            pipeline=self.app.pipeline,
            app=self.app.context,
            sessions=self.app.session_contexts,
        )
        _GateProbe.seen_gate = None
        self._dispose = self.app.registry.register(_GateProbe())

    def tearDown(self) -> None:
        self._dispose()

    def test_execute_fills_session_gate(self) -> None:
        cid = "gate-session-1"
        expected = self.app.session_contexts.resolve_sync(cid).gate
        call = ToolCallRequest(call_id="c1", name="_gate_probe", arguments={})
        result = self.port.execute(call, conversation_id=cid)
        self.assertTrue(result.ok, msg=str(getattr(result, "error", "")))
        self.assertIs(_GateProbe.seen_gate, expected)


if __name__ == "__main__":
    unittest.main()
