# -*- coding: utf-8 -*-
"""内核挂起调用恢复入口。"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from agent.app import App


class _Contexts:
    def __init__(self, session):
        self.session = session

    def resolve_sync(self, _cid):
        return self.session


class _Mesh:
    def __init__(self):
        self.calls = []

    def submit(self, cid, payload):
        self.calls.append((cid, payload))
        return {"queued": False, "run_id": "run-1"}


class ToolResumeTest(unittest.TestCase):
    def _app(self, pending):
        return SimpleNamespace(
            session_contexts=_Contexts(SimpleNamespace(pending_confirm=pending)),
            mesh=_Mesh(),
        )

    def test_rejects_missing_or_mismatched_pending(self) -> None:
        app = self._app(None)
        self.assertFalse(App.resume_suspended(app, "cid", "call-1", {})["ok"])
        app = self._app({"call_id": "other"})
        self.assertFalse(App.resume_suspended(app, "cid", "call-1", {})["ok"])
        self.assertEqual(app.mesh.calls, [])

    def test_submits_resume_and_clears_pending(self) -> None:
        app = self._app({"call_id": "call-1", "kind": "confirm"})
        result = App.resume_suspended(app, "cid", "call-1", {"consent_id": "c-1"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["run_id"], "run-1")
        self.assertIsNone(app.session_contexts.session.pending_confirm)
        cid, payload = app.mesh.calls[0]
        self.assertEqual(cid, "cid")
        self.assertEqual(payload["resume"]["call_id"], "call-1")
        self.assertEqual(payload["resume"]["data"], {"consent_id": "c-1"})

    def test_submit_failure_restores_pending(self) -> None:
        app = self._app({"call_id": "call-1", "kind": "confirm"})

        def _fail(*_args, **_kwargs):
            raise RuntimeError("mesh down")

        app.mesh.submit = _fail
        result = App.resume_suspended(app, "cid", "call-1", {})
        self.assertFalse(result["ok"])
        self.assertEqual(
            app.session_contexts.session.pending_confirm["call_id"], "call-1")


if __name__ == "__main__":
    unittest.main()
