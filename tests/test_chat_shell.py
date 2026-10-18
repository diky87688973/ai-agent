# -*- coding: utf-8 -*-
"""交互壳（shell/chat.py）装配测试 —— 会话门控解析。

门控必须按会话取：拿默认桶门控（`app.gate`）去确认一个具名会话的预览，
确认不会落到该会话上，提交必被拒（"预览尚未确认"），交互壳将完全无法写盘。
本文件把"壳层取哪个门控"钉死为断言，并端到端跑通壳层的确认回调。
"""
from __future__ import annotations

import builtins
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.app import build_app  # noqa: E402
from agent.core.session_context import SessionContexts  # noqa: E402
from agent.core.tool_call import ToolCallRequest  # noqa: E402
from agent.shell.chat import _PREVIEW_TOOL_NAMES, _ask_confirm, build_session  # noqa: E402

CID = "chat-shell-regression-01"

class ChatGateWiringTest(unittest.TestCase):
    """壳层门控解析：必须是会话自己的门控，不是默认桶。"""

    def setUp(self) -> None:
        self.app = build_app()
        self.addCleanup(self.app.dispose)
        built = build_session(["--session", CID], app=self.app)
        self.app, self.cid, self.engine, self.gate, self.single = built  # type: ignore[misc]
        self.addCleanup(self.app.session_contexts.release, self.cid)

    def test_build_session_returns_named_conversation(self) -> None:

        self.assertEqual(self.cid, CID)
        self.assertTrue(self.single == "" or isinstance(self.single, str))

    def test_gate_is_the_conversation_gate_not_default_bucket(self) -> None:

        self.assertIs(self.gate, self.app.gate_for(CID))
        self.assertIsNot(self.gate, self.app.gate)
        self.assertIsNot(self.gate, self.app.gate_for(""))

    def test_engine_runs_on_same_conversation_id(self) -> None:

        self.assertEqual(self.engine.conversation_id, CID)

class ChatConfirmRoundTripTest(unittest.TestCase):
    """端到端：壳层确认回调 → 模型凭同一 ID 提交（真实文件落盘）。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.app = build_app()
        self.addCleanup(self.app.session_contexts.close_all)
        self._seq = 0

    def _call(self, name: str, arguments: dict, cid: str):
        from agent.core.ports import ToolPort

        self._seq += 1
        call = ToolCallRequest(call_id=f"c{self._seq}", name=name, arguments=arguments)
        port = ToolPort(
            registry=self.app.registry,
            pipeline=self.app.pipeline,
            app=self.app.context,
            sessions=self.app.session_contexts,
        )
        return port.execute(call, conversation_id=cid)

    def _confirm_yes(self, gate, name: str, confirm_id: str, args: dict) -> None:
        """以真实壳层回调驱动确认（stdin 替身为 y）。"""
        original = builtins.input
        builtins.input = lambda *a, **k: "y"
        try:
            _ask_confirm(gate, name, confirm_id, args)
        finally:
            builtins.input = original

    def test_shell_confirm_releases_preview_and_commit_lands(self) -> None:

        target = self.root / "shell_out.txt"
        gate = self.app.gate_for(CID)

        preview = self._call(
            "write_file", {"path": str(target), "content": "shell-ok"}, CID
        )
        self.assertTrue(preview.ok, msg=str(preview.error))
        confirm_id = str((preview.data or {}).get("confirm_id") or "")
        self.assertTrue(confirm_id)

        # 壳层回调：确认落在会话门控上
        self._confirm_yes(gate, "write_file", confirm_id, preview.data or {})
        self.assertTrue(bool((gate.peek(confirm_id) or {}).get("confirmed")))

        commit = self._call("commit_write", {"confirm_id": confirm_id}, CID)
        self.assertTrue(commit.ok, msg=str(commit.error))
        self.assertEqual(target.read_text(encoding="utf-8"), "shell-ok")

    def test_default_bucket_gate_cannot_confirm_named_session(self) -> None:
        """反面：默认桶门控确认不了具名会话的预览。"""

        target = self.root / "shell_wrong_gate.txt"
        preview = self._call(
            "write_file", {"path": str(target), "content": "nope"}, CID
        )
        confirm_id = str((preview.data or {}).get("confirm_id") or "")

        self.assertFalse(self.app.gate.confirm(confirm_id))
        blocked = self._call("commit_write", {"confirm_id": confirm_id}, CID)
        self.assertFalse(blocked.ok)
        # 钉**实质**而非"确认"二字：文案必须说明预览未解锁、
        # 并点明解锁入口 `review_conclusion`。
        self.assertIn("未解锁", blocked.error)
        self.assertIn("review_conclusion", blocked.error)
        self.assertFalse(target.exists())

    def test_preview_tool_names_include_write_path_tools(self) -> None:

        for name in ("write_file", "replace_in_file", "apply_patch", "read_write", "delete_file"):
            self.assertIn(name, _PREVIEW_TOOL_NAMES, msg=name)

class ChatExitReleaseTest(unittest.TestCase):
    """交互壳退出时释放会话运行态。"""
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        app = build_app(
            backup_root=self.root / "bk",
            recycle_root=self.root / "rc",
        )
        cid = "chat-exit-release-01"
        engine = app.session(cid, system_prompt="")
        gate = app.gate_for(cid)
        self.app, self.cid, self.engine, self.gate = app, cid, engine, gate
        self.contexts = app.session_contexts

    def _run_main_with_stubbed_build(self) -> int:
        """以替身 build_session 驱动 main()，观测退出路径。"""
        import agent.shell.chat as chat

        original_build = chat.build_session
        original_run = chat.run_one
        chat.build_session = lambda argv=None, app=None, parsed=None: (  # type: ignore[assignment]
            self.app, self.cid, self.engine, self.gate, "single text"
        )
        chat.run_one = lambda engine, gate, text: None  # type: ignore[assignment]
        try:
            return chat.main([], app_factory=lambda: self.app)
        finally:
            chat.build_session = original_build  # type: ignore[assignment]
            chat.run_one = original_run  # type: ignore[assignment]

    def test_main_releases_session_on_exit(self) -> None:

        self.assertGreaterEqual(self.contexts.active_count(), 1)
        self.assertEqual(self._run_main_with_stubbed_build(), 0)
        self.assertEqual(self.contexts.active_count(), 0)
        self.assertEqual(self.app.context.names(), [])

    def test_released_session_reparses_clean(self) -> None:
        """释放后同 cid 重新解析得到干净上下文（红灯 / 待 review 不残留）。

        测的是 SessionContexts.release，不是 app.dispose（dispose 会拆掉注册表，
        gate_for 按契约直接报错）。
        """

        self.gate.set_intent("debug")
        self.gate.note_committed("stale.py", tool="write_file")
        self.assertTrue(self.gate.pending_review)

        self.assertTrue(self.contexts.release(self.cid))

        fresh = self.app.gate_for(self.cid)
        self.assertIsNot(fresh, self.gate)
        self.assertEqual(fresh.intent, "")
        self.assertEqual(fresh.pending_review, [])
        self.assertTrue(fresh.reviewed_ok)

class ExplicitReleaseTest(unittest.TestCase):
    """会话上下文显式释放（不引入自动淘汰）。"""

    def test_release_drops_only_that_conversation(self) -> None:

        ctxs = SessionContexts(lambda cid: object())
        a = ctxs.resolve_sync("conv-a")
        ctxs.resolve_sync("conv-b")
        self.assertEqual(ctxs.active_count(), 2)
        self.assertTrue(ctxs.release("conv-a"))
        self.assertEqual(ctxs.active_count(), 1)
        self.assertIsNone(ctxs.get("conv-a"))
        self.assertIsNotNone(ctxs.get("conv-b"))
        # 释放后重新解析得到新上下文（旧引用失效）
        self.assertIsNot(ctxs.resolve_sync("conv-a"), a)

    def test_web_release_conversation_reduces_active_count(self) -> None:
        """关闭会话 API 调用 release 后 active_count 下降。"""
        from agent.shell.web import WebShell

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        app = build_app(
            backup_root=Path(tmp.name) / "bk",
            recycle_root=Path(tmp.name) / "rc",
        )
        self.addCleanup(app.dispose)
        cid = "web-release-active-count-01"
        app.session_contexts.resolve_sync(cid)
        before = app.session_contexts.active_count()
        self.assertGreaterEqual(before, 1)
        shell = WebShell(app)
        status, payload = shell.release_conversation(cid)
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("ok"))
        self.assertEqual(app.session_contexts.active_count(), before - 1)
        self.assertIsNone(app.session_contexts.get(cid))

    def test_release_unknown_and_blank_are_safe(self) -> None:

        ctxs = SessionContexts(lambda cid: object())
        self.assertFalse(ctxs.release("never-created"))
        default = ctxs.resolve_sync("")
        self.assertTrue(ctxs.release("   "))  # 空白 → 默认桶
        self.assertIsNone(ctxs.get(""))
        self.assertIsNot(default, None)

    def test_close_all_clears_registry(self) -> None:

        ctxs = SessionContexts(lambda cid: object())
        for i in range(5):
            ctxs.resolve_sync(f"conv-{i}")
        self.assertEqual(ctxs.close_all(), 5)
        self.assertEqual(ctxs.active_count(), 0)
        self.assertEqual(ctxs.close_all(), 0)

    def test_release_does_not_touch_persisted_records(self) -> None:
        """释放只丢进程内运行态：会话记录（事实源）不受影响。"""

        import tempfile as _tf

        from agent.core.events import make_event
        from agent.mechanisms.session_store import SessionStore

        with _tf.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp))
            store.append(CID, [make_event("turn_started", conversation_id=CID)])
            ctxs = SessionContexts(lambda cid: object())
            ctxs.resolve_sync(CID)
            ctxs.release(CID)
            self.assertEqual(len(store.load(CID)), 1)
            self.assertIsNotNone(ctxs.resolve_sync(CID))

class ChatArgParsingTest(unittest.TestCase):
    """入口参数在装配之前解析：缺配置时 `--help` 仍可用。"""

    def test_help_exits_before_building_app(self) -> None:
        import agent.shell.chat as chat

        built: list[int] = []

        def factory():
            built.append(1)
            raise AssertionError("--help 不应触发 app 装配")

        with self.assertRaises(SystemExit) as caught:
            chat.main(["--help"], app_factory=factory)
        self.assertEqual(caught.exception.code, 0)
        self.assertEqual(built, [])

    def test_session_and_text_are_parsed(self) -> None:
        import agent.shell.chat as chat

        parsed = chat.parse_args(["--session", CID, "你好"])
        self.assertEqual(parsed.session, CID)
        self.assertEqual(parsed.text, "你好")

    def test_build_session_accepts_parsed_args(self) -> None:
        import agent.shell.chat as chat

        app = build_app()
        self.addCleanup(app.dispose)
        parsed = chat.parse_args(["--session", CID, "单回合"])
        built = chat.build_session(None, app=app, parsed=parsed)
        self.addCleanup(app.session_contexts.release, CID)
        self.assertEqual(built[1], CID)
        self.assertEqual(built[4], "单回合")


if __name__ == "__main__":
    unittest.main()
