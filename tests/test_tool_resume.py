"""Durable confirmation identity and settlement."""
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent.app import App
from agent.core.events import Event
from agent.core.session_context import SessionContext
from agent.mechanisms.session_store import SessionStore
from agent.shell.session.resume import interrupt_confirmation


class ToolResumeTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = SessionStore(Path(folder.name))
        self.cid = "confirm-session"
        self.session = SessionContext()
        self.starts = []
        self.frames = []
        self.app = SimpleNamespace(
            session_contexts=SimpleNamespace(resolve_sync=lambda _cid: self.session),
            mesh=SimpleNamespace(is_stopped=lambda _cid: False, submit=self._submit),
            store=self.store, event_bus=SimpleNamespace(publish=self.frames.append),
        )

    def _submit(self, cid, payload, **kwargs):
        self.starts.append(cid)
        return {"run_id": "run-1"}

    def _suspend(self, call_id):
        pending = {"call_id": call_id, "request_id": "req-" + call_id, "kind": "confirm"}
        self.store.append(self.cid, [Event("tool_suspended", {
            "call_id": call_id, "envelope": pending,
        })])
        self.session.pending_confirm = pending

    def _respond(self, call_id, **kwargs):
        return App.resume_suspended(self.app, self.cid, call_id, {"confirm": "yes"},
                                    request_id="req-" + call_id, **kwargs)

    def test_rejects_missing_or_mismatched_pending(self):
        self._suspend("A")
        interrupt_confirmation(self.app, self.cid, self.store)
        self.store.append(self.cid, [Event("input_claimed", {"content": "new input"})])
        before = self.store.load(self.cid)
        self.assertTrue(self._respond("A")["expired"])
        self.assertEqual(self.store.load(self.cid), before)
        self.assertEqual(before[1].data["error"], "无结果：用户未作答")
        self.assertEqual(before[-1].type, "input_claimed")

        self._suspend("B")
        before = self.store.load(self.cid)
        callback_calls = []
        self.assertTrue(self._respond("A", resolve=lambda *_: callback_calls.append(1))["expired"])
        self.assertEqual(callback_calls, [])
        self.assertEqual(self.session.pending_confirm["call_id"], "B")
        self.assertEqual(self.store.load(self.cid), before)
        self.assertEqual(self.starts, [])
        self.assertEqual(len(self.frames), 1)
        self.assertTrue(self._respond("B")["ok"])

    def test_submits_resume_and_clears_pending(self):
        self._suspend("A")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self._respond("A"), range(2)))
        self.assertEqual(sum(bool(item["ok"]) for item in results), 1)
        self.assertIsNone(self.session.pending_confirm)
        self.assertEqual(len(self.starts), 1)
        self.assertEqual(sum(e.type == "tool_done" for e in self.store.load(self.cid)), 1)

    def test_submit_failure_restores_pending(self):
        self._suspend("A")
        rolled_back = []
        with patch.object(self.store, "append_if_absent", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                interrupt_confirmation(self.app, self.cid, self.store)
            result = self._respond("A", resolve=lambda *_: {
                "ok": True, "rollback": lambda: rolled_back.append(True),
            })
        self.assertFalse(result["ok"])
        self.assertEqual(rolled_back, [True])
        self.assertEqual(self.session.pending_confirm["call_id"], "A")
        self.assertEqual(self.starts, [])
        self.assertTrue(self._respond("A")["ok"])


if __name__ == "__main__":
    unittest.main()
