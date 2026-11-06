# -*- coding: utf-8 -*-
"""挂起回合不得消费待发送队列。"""
from __future__ import annotations

import sys
import time
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
                    from_queue=False, meta=None):
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
                    from_queue=False, meta=None):
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

    def test_insertion_keeps_busy_start_but_next_queued_round_resets_it(self) -> None:
        cid = "paused-queue-04"
        queue = ConversationQueue()
        mesh = MeshState(input_queue=queue)
        app = _App(queue)
        app.session_contexts = _IdleContexts()
        runner = SessionRunner(app=app, mesh=mesh)

        self.assertTrue(mesh.try_begin_run(cid))
        first_started = mesh.run_started_at(cid)
        item = queue.enqueue(cid, content="插入补充")
        queue.set_insert(cid, item["id"])
        self.assertEqual(runner._insert_turn_state(cid), "ready")
        self.assertEqual(mesh.run_started_at(cid), first_started,
                         "插话续跑不得重置当前忙碌段的开始时间")
        self.assertIsNotNone(queue.claim_insert(cid))

        starts = []

        def execute(_cid, _text, attachments=None, resume=None, sender=None,
                    from_queue=False, meta=None):
            starts.append(mesh.run_started_at(cid))
            if len(starts) == 1:
                time.sleep(0.05)
                queue.enqueue(cid, content="下一项任务")

        runner._execute = execute  # type: ignore[method-assign]
        runner._run_loop(cid, "首轮")
        self.assertEqual(len(starts), 2)
        self.assertGreater(starts[1], first_started,
                           "新的任务轮次必须从新的开始时间计算")


class InsertDeliveryTest(unittest.TestCase):
    def test_nested_meta_cannot_override_message_fields(self) -> None:
        cid = "insert-meta-0001"
        queue = ConversationQueue()
        mesh = MeshState(input_queue=queue)
        self.assertTrue(mesh.try_begin_run(cid))
        mesh.submit_insert(
            cid,
            {
                "content": "外层通知正文",
                "attachments": [],
                "meta": {
                    "content": "不应覆盖正文",
                    "attachments": "不应覆盖附件",
                    "kind": "system_notice",
                },
            },
            origin="system",
        )
        claimed = queue.claim_insert_batch(cid)
        self.assertEqual(claimed[0]["content"], "外层通知正文")
        self.assertEqual(claimed[0]["attachments"], [])
        self.assertEqual(claimed[0]["payload"]["content"], "外层通知正文")
        self.assertEqual(claimed[0]["payload"]["kind"], "system_notice")
        self.assertEqual(
            claimed[0]["payload"]["meta"]["kind"], "system_notice")
        mesh.end_run(cid)

    def test_busy_insert_is_deduplicated_and_keeps_queue_order(self) -> None:
        cid = "insert-atomic-01"
        queue = ConversationQueue()
        mesh = MeshState(input_queue=queue)
        self.assertTrue(mesh.try_begin_run(cid))
        message = {
            "content": "任务批次已完成",
            "meta": {
                "kind": "system_notice",
                "source": "background_tasks",
                "notice_id": "notice-1",
                "batch": "batch-1",
            },
        }
        first = mesh.submit_insert(
            cid, message, origin="system",
            dedupe_key="system_notice:background_tasks:notice-1",
        )
        second = mesh.submit_insert(
            cid, message, origin="system",
            dedupe_key="system_notice:background_tasks:notice-1",
        )
        self.assertTrue(first["inserted"])
        self.assertTrue(second["inserted"])
        self.assertTrue(queue.has_inserting(cid))
        claimed = queue.claim_insert_batch(cid)
        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0]["payload"]["notice_id"], "notice-1")
        mesh.end_run(cid)

    def test_idle_insert_starts_one_queue_driven_run(self) -> None:
        cid = "insert-idle-0001"
        queue = ConversationQueue()
        mesh = MeshState(input_queue=queue)
        starts = []
        mesh.set_activator(
            lambda key, message: (
                starts.append((key, message)) or mesh.try_begin_run(key)
            )
        )
        result = mesh.submit_insert(
            cid, {"content": "notice", "meta": {"kind": "system_notice"}},
            origin="system",
        )
        self.assertTrue(result["queued"])
        self.assertTrue(result["inserted"])
        self.assertTrue(result["run_id"])
        self.assertEqual(starts, [(cid, {})])
        claimed = queue.claim_insert_batch(cid)
        self.assertEqual(claimed[0]["content"], "notice")
        self.assertEqual(claimed[0]["payload"]["kind"], "system_notice")
        mesh.end_run(cid)

    def test_late_insert_is_consumed_by_finishing_runner(self) -> None:
        cid = "insert-finish-01"
        queue = ConversationQueue()
        mesh = MeshState(input_queue=queue)
        app = _App(queue)
        app.session_contexts = _IdleContexts()
        runner = SessionRunner(app=app, mesh=mesh)
        rounds = []

        def execute(_cid, _text, attachments=None, resume=None, sender=None,
                    from_queue=False, meta=None):
            rounds.append(len(rounds) + 1)
            if len(rounds) == 2:
                claimed = queue.claim_insert_batch(_cid)
                self.assertEqual([row["content"] for row in claimed], ["迟到通知"])

        def next_text(_cid):
            if len(rounds) == 1:
                mesh.submit_insert(
                    _cid,
                    {"content": "迟到通知", "meta": {
                        "kind": "system_notice",
                        "source": "background_tasks",
                    }},
                    origin="system",
                )
            return ""

        runner._execute = execute  # type: ignore[method-assign]
        runner._next_continuation_text = next_text  # type: ignore[method-assign]
        self.assertTrue(mesh.try_begin_run(cid))
        runner._run_loop(cid, "首轮")
        self.assertEqual(rounds, [1, 2])
        self.assertFalse(mesh.is_running(cid))
        self.assertFalse(queue.has_inserting(cid))

if __name__ == "__main__":
    unittest.main()
