# -*- coding: utf-8 -*-
"""开发者上下文导出：复用真实装配，不调用模型。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.app import build_app  # noqa: E402
from agent.core.model_call import StreamDelta  # noqa: E402
from agent.mechanisms.session_store import SessionStore  # noqa: E402
from agent.shell.context_dump import build_snapshot, render_text  # noqa: E402
from agent.shell.service_keys import SERVICE_RUNNER  # noqa: E402


class _Provider:
    name = "dump-test"

    def __init__(self) -> None:
        self.requests = []

    def stream(self, request):
        self.requests.append(request)
        yield StreamDelta(kind="text", text="收到。")
        yield StreamDelta(kind="done")


class ContextDumpTest(unittest.TestCase):
    def test_snapshot_uses_real_assembly_and_does_not_call_model(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest = root / "plugins.ini"
            manifest.write_text("", encoding="utf-8")
            provider = _Provider()
            app = build_app(
                provider=provider,
                store=SessionStore(root / "data"),
                plugins_path=manifest,
                plugins_dir=root / "plugins",
            )
            try:
                runner = app.context.get(SERVICE_RUNNER)
                runner.start("0123456789abcdef0123456789abcdef", {"content": "导出测试"})
                self.assertTrue(runner.wait_idle("0123456789abcdef0123456789abcdef", 10))
                before = len(provider.requests)
                snapshot = build_snapshot(app, "0123456789abcdef0123456789abcdef")
                self.assertEqual(len(provider.requests), before)
                self.assertTrue(snapshot["messages"])
                self.assertNotIn("## Todo-List：", snapshot["mode_note"])
                self.assertNotIn("## Todo-List：", render_text(snapshot))
                users = [str(m.get("content") or "") for m in snapshot["messages"]
                         if str(m.get("role") or "") == "user"]
                self.assertIn("导出测试", "\n".join(users))
            finally:
                app.dispose()

    def test_snapshot_reports_todo_progress_when_list_exists(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest = root / "plugins.ini"
            manifest.write_text("", encoding="utf-8")
            app = build_app(
                provider=_Provider(),
                store=SessionStore(root / "data"),
                plugins_path=manifest,
                plugins_dir=root / "plugins",
            )
            cid = "fedcba9876543210fedcba9876543210"
            try:
                app.live_state.set_todo(cid, {
                    "list_id": "dump-list",
                    "collapsed": False,
                    "items": [
                        {"text": "已完成项", "done": True},
                        {"text": "进行中项", "done": False},
                    ],
                })
                runner = app.context.get(SERVICE_RUNNER)
                runner.start(cid, {"content": "导出测试"})
                self.assertTrue(runner.wait_idle(cid, 10))
                snapshot = build_snapshot(app, cid)
                text = render_text(snapshot)
                self.assertIn("## Todo-List：", snapshot["mode_note"])
                self.assertIn("当前进度：1 已完成，1 进行中，0 待处理", snapshot["mode_note"])
                self.assertIn("当前进度：1 已完成，1 进行中，0 待处理", text)
            finally:
                app.dispose()

    def test_missing_conversation_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest = root / "plugins.ini"
            manifest.write_text("", encoding="utf-8")
            app = build_app(
                provider=_Provider(), store=SessionStore(root / "data"),
                plugins_path=manifest, plugins_dir=root / "plugins",
            )
            try:
                with self.assertRaises(ValueError):
                    build_snapshot(app, "missing")
            finally:
                app.dispose()


if __name__ == "__main__":
    unittest.main()
