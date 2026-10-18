# -*- coding: utf-8 -*-
"""会话上下文（SessionContext / SessionContexts）测试。

覆盖：隔离键 / 懒创建与复用 / 线程安全 / 默认桶 / 独立门控 /
共享容器 / 单解析路径 / 三级不混放 / 装配接线 / 跨会话不串扰。
"""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.app import build_app  # noqa: E402
from agent.core.session_context import (  # noqa: E402
    DEFAULT_BUCKET,
    SessionContext,
    SessionContexts,
)
from agent.core.session_scope import current_session_id  # noqa: E402
from agent.core.tool_call import ToolCallRequest  # noqa: E402
from agent.mechanisms.live_state import LiveState  # noqa: E402
from agent.mechanisms.quality import QualityGate  # noqa: E402
from tests.gate_fixtures import make_gate  # noqa: E402


def _contexts(**kwargs) -> SessionContexts:
    """会话注册表（门控工厂默认造真门控，并接内置 write_path_keys）。"""
    return SessionContexts(kwargs.pop("gate_factory", lambda cid: make_gate()), **kwargs)

class IsolationKeyTest(unittest.TestCase):
    """会话隔离键。"""

    def test_bucket_key_rules(self):

        ctxs = _contexts()
        self.assertIs(ctxs.resolve_sync("conv-a"), ctxs.resolve_sync("conv-a"))
        self.assertIsNot(ctxs.resolve_sync("conv-a"), ctxs.resolve_sync("conv-b"))

    def test_empty_and_blank_share_default_bucket(self):

        ctxs = _contexts()
        default = ctxs.resolve_sync("")
        self.assertEqual(default.conversation_id, DEFAULT_BUCKET)
        self.assertIs(ctxs.resolve_sync("   "), default)
        self.assertIs(ctxs.resolve_sync(None), default)

    def test_whitespace_normalised_but_case_preserved(self):

        ctxs = _contexts()
        self.assertIs(ctxs.resolve_sync(" conv-a "), ctxs.resolve_sync("conv-a"))
        self.assertIsNot(ctxs.resolve_sync("Conv-A"), ctxs.resolve_sync("conv-a"))

class LazyLifecycleTest(unittest.TestCase):
    """懒创建语义。"""

    def test_no_context_until_resolved(self):

        ctxs = _contexts()
        self.assertEqual(ctxs.buckets(), {})
        ctxs.resolve_sync("conv-a")
        self.assertEqual(list(ctxs.buckets()), ["conv-a"])

    def test_get_is_readonly_no_side_effect(self):

        ctxs = _contexts()
        self.assertIsNone(ctxs.get("never-created"))
        self.assertEqual(ctxs.buckets(), {})
        created = ctxs.resolve_sync("conv-a")
        self.assertIs(ctxs.get("conv-a"), created)

    def test_gate_factory_called_once_per_conversation(self):

        made = []

        def factory(cid):
            made.append(cid)
            return make_gate()

        ctxs = SessionContexts(factory)
        ctxs.resolve_sync("conv-a")
        ctxs.resolve_sync("conv-a")
        ctxs.resolve_sync("conv-b")
        self.assertEqual(made, ["conv-a", "conv-b"])

class ThreadSafetyTest(unittest.TestCase):
    """线程安全。"""

    def test_concurrent_first_use_yields_single_context(self):

        ctxs = _contexts()
        results = []
        barrier = threading.Barrier(8)

        def worker():
            barrier.wait(timeout=10)
            results.append(ctxs.resolve_sync("conv-race"))

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertEqual(len(results), 8)
        self.assertEqual(len({id(r) for r in results}), 1)
        self.assertEqual(len(ctxs.buckets()), 1)

class ExclusiveGateTest(unittest.TestCase):
    """门控每会话独占，跨会话不串扰。"""

    def test_gates_are_distinct_instances(self):

        ctxs = _contexts()
        a = ctxs.resolve_sync("conv-a").gate
        b = ctxs.resolve_sync("conv-b").gate
        self.assertIsInstance(a, QualityGate)
        self.assertIsNot(a, b)

    def test_preview_snapshot_not_visible_across_sessions(self):

        ctxs = _contexts()
        gate_a = ctxs.resolve_sync("conv-a").gate
        gate_b = ctxs.resolve_sync("conv-b").gate
        cid = gate_a.register_preview("write_file", {"path": "a.txt", "content": "x"})
        self.assertIsNotNone(gate_a.peek(cid))
        self.assertIsNone(gate_b.peek(cid))
        self.assertFalse(gate_b.confirm(cid))
        self.assertFalse(gate_b.discard(cid))
        self.assertTrue(gate_a.confirm(cid))

    def test_review_and_reread_state_not_shared(self):

        ctxs = _contexts()
        gate_a = ctxs.resolve_sync("conv-a").gate
        gate_b = ctxs.resolve_sync("conv-b").gate
        gate_a.note_committed("x.py", tool="write_file")
        self.assertEqual(len(gate_a.pending_review), 1)
        self.assertEqual(gate_b.pending_review, [])
        self.assertTrue(gate_b.reviewed_ok)
        self.assertFalse(gate_a.reviewed_ok)

    def test_intent_and_red_light_not_shared(self):

        ctxs = _contexts()
        gate_a = ctxs.resolve_sync("conv-a").gate
        gate_b = ctxs.resolve_sync("conv-b").gate
        gate_a.set_intent("debug")
        gate_a.pending_diagnose_red = True
        self.assertEqual(gate_b.intent, "")
        self.assertFalse(gate_b.pending_diagnose_red)

class SharedContainerTest(unittest.TestCase):
    """live / inbox 为装配级共享容器。"""

    def test_live_and_inbox_shared_by_reference(self):

        live = LiveState()
        ctxs = _contexts(live=live, inbox=object())
        a = ctxs.resolve_sync("conv-a")
        b = ctxs.resolve_sync("conv-b")
        self.assertIs(a.live, b.live)
        self.assertIs(a.live, live)
        self.assertIs(a.inbox, b.inbox)

    def test_shared_live_is_still_partitioned_by_cid(self):

        live = LiveState()
        ctxs = _contexts(live=live)
        ctxs.resolve_sync("conv-a").live.set_mode("conv-a", "plan")
        self.assertEqual(ctxs.resolve_sync("conv-a").live.get_mode("conv-a"), "plan")
        self.assertEqual(ctxs.resolve_sync("conv-b").live.get_mode("conv-b"), "auto")

    def test_gate_factory_required(self):

        with self.assertRaises(ValueError):
            SessionContexts(None)

class ResolutionPathTest(unittest.TestCase):
    """单解析路径（core.session_scope）。"""

    def test_resolve_uses_current_session_scope(self):

        ctxs = _contexts()
        self.assertIs(ctxs.resolve(), ctxs.resolve_sync(current_session_id()))
        self.assertEqual(ctxs.resolve().conversation_id, DEFAULT_BUCKET)

class LevelSeparationTest(unittest.TestCase):
    """三级上下文不混放。"""

    def test_session_context_holds_only_session_level_state(self):

        ctxs = _contexts()
        ctx = ctxs.resolve_sync("conv-a")
        self.assertIsInstance(ctx, SessionContext)
        # 会话记录 / 上下文管线 / 压缩器不驻留会话上下文（由回合引擎按会话构建）
        self.assertFalse(hasattr(ctx, "log"))
        self.assertFalse(hasattr(ctx, "context"))
        self.assertFalse(hasattr(ctx, "compactor"))

class AppWiringTest(unittest.TestCase):
    """装配接线（app.py 经注册表按会话解析门控）。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.app = build_app()

    def _call(self, name: str, arguments: dict, cid: str = ""):
        from agent.core.ports import ToolPort

        call = ToolCallRequest(call_id=f"c-{name}-{cid}", name=name, arguments=arguments)
        port = ToolPort(
            registry=self.app.registry,
            pipeline=self.app.pipeline,
            app=self.app.context,
            sessions=self.app.session_contexts,
        )
        return port.execute(call, conversation_id=cid)

    def test_default_bucket_gate_is_canonical(self):

        self.assertIs(self.app.gate, self.app.gate_for(""))
        self.assertIs(self.app.gate, self.app.session_contexts.resolve_sync("").gate)

    def test_gate_for_is_per_conversation(self):

        self.assertIsNot(self.app.gate_for("conv-a"), self.app.gate_for("conv-b"))
        self.assertIs(self.app.gate_for("conv-a"), self.app.gate_for("conv-a"))

    def test_app_exposes_session_contexts(self):

        self.assertIsInstance(self.app.session_contexts, SessionContexts)
        self.assertIs(self.app.session_contexts.live, self.app.live_state)
        self.assertIs(self.app.session_contexts.inbox, self.app.mesh)

    def test_preview_and_confirm_land_in_same_session_gate(self):

        target = self.root / "session_wiring.txt"
        prev = self._call("write_file", {"path": str(target), "content": "hello"}, cid="conv-a")
        self.assertTrue(prev.ok, msg=str(prev.error))
        cid = prev.data["confirm_id"]
        gate_a = self.app.gate_for("conv-a")
        self.assertIsNotNone(gate_a.peek(cid))
        # 另一会话的门控看不到该预览
        self.assertIsNone(self.app.gate_for("conv-b").peek(cid))
        gate_a.confirm(cid)
        commit = self._call("commit_write", {"confirm_id": cid}, cid="conv-a")
        self.assertTrue(commit.ok, msg=str(commit.error))
        self.assertEqual(target.read_text(encoding="utf-8"), "hello")

    def test_commit_rejected_when_confirm_lands_in_other_session(self):

        target = self.root / "session_crosstalk.txt"
        prev = self._call("write_file", {"path": str(target), "content": "nope"}, cid="conv-a")
        cid = prev.data["confirm_id"]
        # 在另一会话门控上确认：提交仍须由 conv-a 的门控放行
        self.app.gate_for("conv-b").confirm(cid)
        blocked = self._call("commit_write", {"confirm_id": cid}, cid="conv-a")
        self.assertFalse(blocked.ok)
        # 断言钉实质：这条错误文案点明预览未解锁与解锁入口 `review_conclusion`。
        self.assertIn("未解锁", blocked.error)
        self.assertIn("review_conclusion", blocked.error)
        self.assertFalse(target.exists())

    def test_engine_session_runs_on_its_own_gate(self):

        events = list(self.app.session("conv-engine").start_turn("你好"))
        self.assertTrue(events)
        self.assertIsNotNone(self.app.session_contexts.get("conv-engine"))
        self.assertIsNot(self.app.gate_for("conv-engine"), self.app.gate)

if __name__ == "__main__":
    unittest.main()
