# -*- coding: utf-8 -*-
"""挂起回合不得消费待发送队列。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.mechanisms.conversation_queue import ConversationQueue  # noqa: E402
from agent.mechanisms.mesh import MeshState  # noqa: E402
from agent.shell.session.runner import SessionRunner  # noqa: E402


class _Session:
    pending_confirm = {"call_id": "confirm-1"}


class _Contexts:
    def __init__(self) -> None:
        self.session = _Session()

    def resolve_sync(self, cid: str):
        return self.session


class _IdleSession:
    pending_confirm = None


class _IdleContexts:
    def resolve_sync(self, cid: str):
        return _IdleSession()


class _App:
    live_state = None
    store = None

    def __init__(self, queue: ConversationQueue) -> None:
        self.conversation_queue = queue
        self.session_contexts = _Contexts()


class PausedQueueTest(unittest.TestCase):
    def test_paused_turn_keeps_queue(self) -> None:
        cid = "paused-queue-01"
        queue = ConversationQueue()
        mesh = MeshState(input_queue=queue)
        app = _App(queue)
        runner = SessionRunner(app=app, mesh=mesh)
        rounds = {"n": 0}

        def execute(c, text, attachments=None, resume=None, sender=None,
                    from_queue=False):
            rounds["n"] += 1

        runner._execute = execute  # type: ignore[method-assign]
        queue.enqueue(cid, content="queued")
        self.assertTrue(mesh.try_begin_run(cid))
        runner._run_loop(cid, "start")
        self.assertEqual(rounds["n"], 1)
        self.assertEqual(queue.size(cid), 1)
        self.assertFalse(mesh.is_running(cid))

    def test_host_paused_flag_keeps_queue(self) -> None:
        cid = "paused-queue-02"
        queue = ConversationQueue()
        mesh = MeshState(input_queue=queue)
        app = _App(queue)
        app.session_contexts = _IdleContexts()
        runner = SessionRunner(app=app, mesh=mesh)
        rounds = {"n": 0}

        def execute(c, text, attachments=None, resume=None, sender=None,
                    from_queue=False):
            rounds["n"] += 1
            return True

        runner._execute = execute  # type: ignore[method-assign]
        queue.enqueue(cid, content="queued")
        self.assertTrue(mesh.try_begin_run(cid))
        runner._run_loop(cid, "start")
        self.assertEqual(rounds["n"], 1)
        self.assertEqual(queue.size(cid), 1)
        self.assertFalse(mesh.is_running(cid))


    def test_new_input_cancels_pending_confirm(self) -> None:
        cid = "paused-queue-03"
        queue = ConversationQueue()
        mesh = MeshState(input_queue=queue)
        app = _App(queue)
        runner = SessionRunner(app=app, mesh=mesh)
        self.assertEqual(runner._cancel_pending_for_new_input(cid), "confirm-1")
        session = app.session_contexts.resolve_sync(cid)
        self.assertIsNone(session.pending_confirm)


if __name__ == "__main__":
    unittest.main()
