# -*- coding: utf-8 -*-
"""HTTP/SSE 协议契约测试。

契约的可回归化：把"前端消费契约 → 内核事件模型"的映射钉死，避免换前端时
契约悄悄漂移。本文件不测网络层，只测**事件词汇表与映射落点**。
"""
from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.app import build_app  # noqa: E402
from agent.core import event_name as ev  # noqa: E402

# 经典界面曾消费 / 仍需映射表覆盖的事件类型
FRONTEND_CONSUMED = (
    "assistant",
    "assistant_delta",
    "assistant_markdown",
    "conversation",
    "context_layout",
    "dispatch_title",
    "done",
    "error",
    "llm_done",
    "llm_request",
    "llm_response",
    "llm_round",
    "mode_changed",
    "paused_for_user_confirm",
    "peer_message",
    "reasoning_delta",
    "run_started",
    "todo_list",
    "tool_end",
    "tool_start",
    "usage",
)

# 前端事件类型 → 内核事件映射（值为内核事件名；None = 前端已忽略 / 归状态查询）
SOURCE_TO_NEW = {
    "run_started": ev.TURN_STARTED,
    "reasoning_delta": ev.REASONING_DELTA,
    "assistant_delta": ev.ASSISTANT_DELTA,
    "assistant": ev.MODEL_MESSAGE,
    "assistant_markdown": ev.MODEL_MESSAGE,
    "tool_start": ev.TOOL_STARTED,
    "tool_end": ev.TOOL_DONE,
    "todo_list": ev.TOOL_DONE,
    "paused_for_user_confirm": ev.TOOL_DONE,
    "usage": ev.USAGE,
    "error": ev.ERROR,
    "done": ev.TURN_ENDED,
    "context_layout": ev.CONTEXT_COMPACTED,
    # 步骤卡 / LLM 卡片：前端显式忽略，不实现
    "llm_round": None,
    "llm_request": None,
    "llm_response": None,
    "llm_done": None,
    "dispatch_title": None,
    # 模式 / 会话快照：归状态查询（ui-state / run_type），不走事件流
    "mode_changed": None,
    "conversation": None,
    # 协作类：前端未消费，按需实现
    "peer_message": None,
}

class EventVocabularyTest(unittest.TestCase):
    """词汇表与映射完整性。"""

    def test_frontend_consumed_set_is_fully_mapped(self) -> None:
        """映射表覆盖 FRONTEND_CONSUMED，无悬空类型。"""

        missing = [t for t in FRONTEND_CONSUMED if t not in SOURCE_TO_NEW]
        self.assertEqual(missing, [], msg=f"前端消费但映射表未覆盖：{missing}")

    def test_no_source_type_mapped_to_unknown_new_event(self) -> None:

        known = {
            value
            for name, value in vars(ev).items()
            if not name.startswith("_") and isinstance(value, str)
        }
        for source, target in SOURCE_TO_NEW.items():
            if target is None:
                continue
            with self.subTest(source=source):
                self.assertIn(target, known, msg=f"{source} → {target} 不在 core/events.py")

    def test_ignored_source_types_are_explicitly_dropped(self) -> None:

        for t in ("llm_request", "llm_response", "llm_done", "dispatch_title", "llm_round"):
            self.assertIsNone(SOURCE_TO_NEW[t], msg=f"{t} 应显式不实现")

class KernelEventEmissionTest(unittest.TestCase):
    """内核真实产出的事件序列满足前端契约。"""

    @classmethod
    def setUpClass(cls) -> None:
        app = build_app()
        engine = app.session("probe-events-contract", system_prompt="SYS")
        cls.seen = [e.type for e in engine.start_turn("跑一次工具")]
        cls.app = app

    def test_core_structural_events_emitted(self) -> None:

        # 内核原生词汇：
        # LLM 轮的起止是 `llm_started` / `llm_ended`。
        for name in (
            ev.TURN_STARTED,
            ev.INPUT_CLAIMED,
            ev.LLM_STARTED,
            ev.LLM_ENDED,
            ev.TURN_ENDED,
        ):
            self.assertIn(name, self.seen, msg=name)

    def test_tool_and_message_events_emitted(self) -> None:

        # 工具用 TOOL_STARTED / TOOL_DONE。
        for name in (ev.TOOL_STARTED, ev.TOOL_DONE, ev.MODEL_MESSAGE, ev.ASSISTANT_DELTA):
            self.assertIn(name, self.seen, msg=name)

    def test_every_event_carries_conversation_id(self) -> None:
        """单流多路复用依赖每个事件绑定 conversation_id。"""

        app = build_app()
        engine = app.session("probe-cid-binding", system_prompt="SYS")
        events = list(engine.start_turn("你好"))
        self.assertTrue(events)
        missing = [e.type for e in events if "conversation_id" not in e.data]
        self.assertEqual(missing, [], msg=f"缺 conversation_id 的事件：{missing}")
        cids = {e.data.get("conversation_id") for e in events}
        self.assertEqual(cids, {"probe-cid-binding"})

    def test_event_envelope_is_type_plus_data(self) -> None:
        """载荷为统一信封（type + data），前端 JSON.parse 后按 type 分派。"""

        app = build_app()
        engine = app.session("probe-envelope", system_prompt="SYS")
        for event in engine.start_turn("你好"):
            self.assertIsInstance(event.type, str)
            self.assertIsInstance(event.data, dict)

class AssetReusePolicyTest(unittest.TestCase):
    """媒体路由的可读范围与越界拒绝。"""

    def test_media_and_markdown_rendering_is_frontend_side(self) -> None:
        """后端载荷不含 HTML——工具结果与事件均为结构化数据。"""

        app = build_app()
        engine = app.session("h006-render", system_prompt="SYS")
        for event in engine.start_turn("你好"):
            data = event.data
            # 载荷字段是值而非 HTML 串（不出现标签）
            for value in data.values():
                if isinstance(value, str):
                    self.assertNotIn("<div", value, msg=event.type)
                    self.assertNotIn("<span", value, msg=event.type)

    def test_media_embedding_uses_markdown_syntax(self) -> None:
        """媒体以 Markdown 图片语法嵌入，非 base64 / HTML。"""

        # 消费侧用 markdown 解析器把图片 token 渲染成 `<img>`，且渲染链路不内联 base64。
        ui = (_ROOT / "agent/shell/web_assets/classic/js/agent-ui.js").read_text(encoding="utf-8")
        self.assertIn("marked.Renderer", ui, "经典 UI 应把图片 token 交给解析器的 Renderer")
        self.assertIn("r.image=", ui)
        self.assertIn("function mdParser(", ui, "散文块应由 markdown 解析器实例渲染")
        self.assertIn(".use({renderer:", ui, "渲染定制应经 marked.use 安装")
        self.assertNotIn("base64,", ui, "渲染链路不得内联 base64")
        vendor = (_ROOT / "agent/shell/web_assets/classic/js/vendor/marked.min.js")
        self.assertTrue(vendor.is_file(), "markdown 解析器应随素材分发")

class UiStateContractTest(unittest.TestCase):
    """状态面向（ui-state / usage / 推理档位）的落点。"""

    def test_transient_ui_state_is_per_session(self) -> None:
        """模式 / 折叠态归 live_state（按 cid），不落全局单例。"""

        app = build_app()
        app.live_state.set_mode("h010-a", "execute")
        app.live_state.set_todo("h010-a", {"list_id": "L1", "items": [{"text": "x", "done": False}]})
        self.assertEqual(app.live_state.get_mode("h010-a"), "execute")
        self.assertEqual(app.live_state.get_mode("h010-b"), "auto")
        self.assertTrue(app.live_state.has_active_todo("h010-a"))
        self.assertFalse(app.live_state.has_active_todo("h010-b"))
        app.live_state.set_todo("h010-a", None)

    def test_usage_and_reasoning_are_provider_side(self) -> None:
        """用量经 usage 事件；推理档位属 provider 请求参数。

        **真断言**：直接读 provider 的源码，确认 `payload["reasoning_effort"]`
        取自**请求**而不是写死的常量。

        写死常量会让前端「思考 · High / Max」两档失效——用户选 Max，发出去的还是 high。
        """

        src = (_ROOT / "agent/mechanisms/model_provider.py").read_text(encoding="utf-8")
        self.assertIn('payload["reasoning_effort"] = effort', src,
                      "推理档位必须来自 LogicalRequest.effort；写死常量会让 High/Max 失效")
        self.assertIn('getattr(request, "effort"', src,
                      "effort 应从请求对象读取")
        from agent.core.ports import LogicalRequest
        self.assertIn("effort", inspect.signature(LogicalRequest).parameters)

class SessionIsolationContractTest(unittest.TestCase):
    """多会话隔离与门控确认按 cid 解析（前端分派契约的后端前提）。"""
    def setUp(self) -> None:
        self.app = build_app()
        self.addCleanup(self.app.session_contexts.close_all)

    def test_events_of_two_sessions_carry_distinct_cids(self) -> None:

        a = [e.data.get("conversation_id") for e in self.app.session("sse-a").start_turn("hi")]
        b = [e.data.get("conversation_id") for e in self.app.session("sse-b").start_turn("hi")]
        self.assertEqual(set(a), {"sse-a"})
        self.assertEqual(set(b), {"sse-b"})

    def test_confirm_id_is_session_scoped(self) -> None:
        """确认端点须按 cid 解析门控，不得落默认桶。"""

        import tempfile
        from types import SimpleNamespace

        from agent.core.tool_call import ToolCallRequest

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "_h007_probe.txt"
            call = ToolCallRequest(
                call_id="h007",
                name="write_file",
                arguments={"path": str(target), "content": "x"},
            )
            result = self.app.pipeline.execute(
                self.app.registry, call, SimpleNamespace(conversation_id="h007-session")
            )
            confirm_id = str((result.data or {}).get("confirm_id") or "")
            self.assertTrue(confirm_id)
            # 会话门控能看到，默认桶看不到
            self.assertIsNotNone(self.app.gate_for("h007-session").peek(confirm_id))
            self.assertIsNone(self.app.gate.peek(confirm_id))
            self.assertFalse(self.app.gate.confirm(confirm_id))

if __name__ == "__main__":
    unittest.main()
