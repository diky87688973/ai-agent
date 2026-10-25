# -*- coding: utf-8 -*-
"""上下文贯通冒烟测试：工具轮次内工具拿得到三级上下文。

上下文是模块间传输数据的约定（数据结构）：各模块直接引用 `current_context()`
取到的 ToolTurnContext，不经过回调或解析器。本测试覆盖这条通路。
"""
from __future__ import annotations

import unittest
from typing import Any, Dict, List

from agent.core.context import AppContext, ToolTurnContext
from agent.core.session_context import SessionContexts
from agent.core.session_scope import current_context
from agent.core.tool_call import ToolCallRequest, ToolPipeline


class _ProbeTool:
    """在工具轮次内把上下文抓出来，供断言检查。"""

    name = "probe"
    description = "探针"

    def __init__(self) -> None:
        self.seen: List[Any] = []

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        self.seen.append(current_context())
        return {"ok": True}

class _Registry:
    def __init__(self, tool: Any) -> None:
        self._tool = tool

    def get(self, name: str) -> Any:
        return self._tool if name == self.tool_name else None

    def names(self) -> List[str]:
        return [self.tool_name]

    tool_name = "probe"

class _FakeTurn:
    """最小的回合级上下文（管道只从它取 app / session / conversation_id / progress_sink）。"""

    def __init__(self, app: Any = None, session: Any = None, cid: str = "ctx-smoke-01") -> None:
        self.app = app
        self.session = session
        self.conversation_id = cid
        self.progress_sink = None

class ContextPlumbingTest(unittest.TestCase):
    """三级上下文在工具轮次内可用。"""

    def setUp(self) -> None:
        from agent.mechanisms.quality import QualityGate

        self.tool = _ProbeTool()
        self.registry = _Registry(self.tool)
        self.pipeline = ToolPipeline()
        self.app = AppContext()
        self.app.register("demo_service", {"hello": "world"})
        # 门控住在会话上下文里（真实装配同形：`SessionContexts(lambda cid: QualityGate())`）
        self.gate = QualityGate()
        self.contexts = SessionContexts(lambda cid: self.gate, live="LIVE")
        self.session = self.contexts.resolve_sync("ctx-smoke-01")
        self.call = ToolCallRequest(call_id="call-1", name="probe", arguments={"a": 1})

    def test_tool_sees_all_three_contexts(self) -> None:
        self.pipeline.execute(self.registry, self.call, _FakeTurn(self.app, self.session))
        ctx = self.tool.seen[0]
        self.assertIsInstance(ctx, ToolTurnContext)
        # 进程级
        self.assertIs(ctx.app, self.app)
        # 会话级
        self.assertIs(ctx.session, self.session)
        # 回合级（原对象，供确实要看回合内部状态的场合）
        self.assertIsNotNone(ctx.turn)
        # 本次调用
        self.assertEqual(ctx.call_id, "call-1")
        self.assertEqual(ctx.tool_name, "probe")
        self.assertEqual(ctx.arguments, {"a": 1})

    def test_service_lookup_from_tool_round(self) -> None:
        """全局能力经上下文解析（不必在构造期注入）。"""
        self.pipeline.execute(self.registry, self.call, _FakeTurn(self.app, self.session))
        ctx = self.tool.seen[0]
        self.assertEqual(ctx.service("demo_service"), {"hello": "world"})
        self.assertIsNone(ctx.service("不存在"), msg="未注册服务返回 None，不抛错")

    def test_session_state_reachable_from_tool_round(self) -> None:
        """会话态（门控 / 实时状态 / 待确认）直接从会话上下文取。"""
        self.session.pending_confirm = {"call_id": "call-9", "title": "t", "confirms": ["a"]}
        self.pipeline.execute(self.registry, self.call, _FakeTurn(self.app, self.session))
        ctx = self.tool.seen[0]
        self.assertIs(ctx.session.gate, self.gate)
        self.assertEqual(ctx.session.live, "LIVE")
        self.assertEqual(ctx.session.pending_confirm["call_id"], "call-9")
        self.assertEqual(ctx.conversation_id, "ctx-smoke-01")

    def test_context_does_not_leak_outside_the_call(self) -> None:
        """调用结束即还原：工具轮次上下文不跨调用泄漏。"""
        self.pipeline.execute(self.registry, self.call, _FakeTurn(self.app, self.session))
        self.assertIsNone(current_context())

    def test_missing_contexts_degrade_instead_of_failing(self) -> None:
        """没有 app/session（脚本直建引擎）时仍能跑，只是相关字段为空。"""
        self.pipeline.execute(self.registry, self.call, _FakeTurn())
        ctx = self.tool.seen[0]
        self.assertIsNone(ctx.app)
        self.assertIsNone(ctx.session)
        self.assertEqual(ctx.conversation_id, "")
        self.assertIsNone(ctx.service("demo_service"))
        ctx.report({"text": "无人接收也不报错"})

if __name__ == "__main__":
    unittest.main()
