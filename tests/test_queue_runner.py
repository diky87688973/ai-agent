# -*- coding: utf-8 -*-
"""挂起回合不得消费待发送队列。"""
from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.core.events import Event  # noqa: E402
from agent.core.session_context import SessionContext  # noqa: E402
from agent.mechanisms.conversation_queue import ConversationQueue  # noqa: E402
from agent.mechanisms.mesh import MeshState  # noqa: E402
from agent.mechanisms.session_store import SessionStore  # noqa: E402
from agent.shell.session.runner import SessionRunner  # noqa: E402


class _Session(SessionContext):
    def __init__(self):
        super().__init__(pending_confirm={"call_id": "confirm-1"})


class _Contexts:
    def __init__(self) -> None:
        self.session = _Session()

    def resolve_sync(self, cid: str):
        return self.session


class _IdleSession(SessionContext):
    pass


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
        runner._run_loop(cid, "")
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
            app.session_contexts = _Contexts()
            return True

        runner._execute = execute  # type: ignore[method-assign]
        queue.enqueue(cid, content="queued")
        self.assertTrue(mesh.try_begin_run(cid))
        runner._run_loop(cid, "start")
        self.assertEqual(rounds["n"], 1)
        self.assertEqual(queue.size(cid), 1)
        self.assertFalse(mesh.is_running(cid))


    def test_round_end_settles_confirmation_only_when_not_paused(self) -> None:
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as directory:
            scenarios = ((False, False, False), (True, False, False),
                         (True, True, False), (True, False, True))
            for paused, shutdown, stopped in scenarios:
                with self.subTest(paused=paused, shutdown=shutdown, stopped=stopped):
                    cid = f"confirmation-round-{paused}-{shutdown}-{stopped}"
                    queue = ConversationQueue()
                    app = _App(queue)
                    app.store = SessionStore(Path(directory))
                    app.store.append(cid, [Event("tool_suspended", {"call_id": "confirm-1"})])
                    runner = SessionRunner(app=app, mesh=MeshState(input_queue=queue))
                    engine = SimpleNamespace(start_turn=lambda *_args, paused=paused, **_kwargs: iter([
                        Event("turn_ended", {"paused": paused}),
                    ]))
                    if shutdown:
                        runner._cancels[cid] = threading.Event()
                        self.assertTrue(runner.shutdown())
                    if stopped:
                        runner._mesh.mark_stopped(cid)

                    self.assertEqual(runner._execute_round(cid, "", engine=engine), paused)
                    facts = [event.type for event in app.store.load(cid)]
                    if paused and not stopped:
                        self.assertIsNotNone(app.session_contexts.session.pending_confirm)
                        self.assertEqual(facts, ["tool_suspended"])
                    else:
                        self.assertIsNone(app.session_contexts.session.pending_confirm)
                        self.assertEqual(facts, ["tool_suspended", "tool_failed", "tool_ended"])

    def test_new_input_cancels_pending_confirm(self) -> None:
        """All input sources settle the suspension before recording the new input."""
        from pathlib import Path
        from types import SimpleNamespace

        from agent.boot.shell_components import _notice_handler, wake_scheduler
        from agent.shell.session import queue as input_queue
        from agent.subagent.messaging import SubagentMessenger

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        for source in ("user", "background", "peer", "wake"):
            with self.subTest(source=source):
                cid = f"pending-{source}-01"
                inbox = ConversationQueue()
                mesh = MeshState(input_queue=inbox)
                app = _App(inbox)
                app.mesh = mesh
                app.context = SimpleNamespace(has=lambda _key: False)
                app.store = SessionStore(root / source)
                app.store.append(cid, [Event("tool_suspended", {"call_id": "confirm-1"})])
                runner = SessionRunner(app=app, mesh=mesh, store_for=lambda _cid, store=app.store: store)
                self.addCleanup(runner.shutdown)

                def execute(_cid, *_args, inbox=inbox, app=app, **_kwargs):
                    for item in inbox.claim_insert_batch(_cid):
                        input_queue.persist_inputs(_cid, app, app.store, [item])

                runner._execute = execute
                mesh.set_activator(runner.start)
                if source == "user":
                    mesh.submit(cid, {"content": "new input"}, user_send=True)
                elif source == "background":
                    _notice_handler(app)(cid, "background", {"kind": "system_notice"})
                elif source == "peer":
                    repo = SimpleNamespace(record=lambda child, cid=cid: SimpleNamespace(
                        parent_cid=cid, child_id=child, label="peer"))
                    SubagentMessenger(repository=repo, mesh=mesh).send_to_parent("peer-child", msg="peer")
                else:
                    ctx = SimpleNamespace(boot_config=SimpleNamespace(data_root=root / source))
                    scheduler = wake_scheduler(ctx, app)
                    job = scheduler.schedule_seconds(1, target_cid=cid, owner_cid=cid, reminder="wake")
                    scheduler.run_due(job["due_at"])
                self.assertTrue(runner.wait_idle(cid, timeout=3))
                events = app.store.load(cid)
                self.assertEqual([e.type for e in events],
                                 ["tool_suspended", "tool_failed", "tool_ended", "input_claimed"])
                self.assertEqual(events[1].data["error"], "无结果：用户未作答")
                self.assertIsNone(app.session_contexts.resolve_sync(cid).pending_confirm)

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

    def test_failed_batch_claim_keeps_items_visible_and_retryable(self) -> None:
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            queue = ConversationQueue(Path(directory))
            cid = "batch-claim-fail"
            first = queue.enqueue(cid, content="first")
            second = queue.enqueue(cid, content="second")
            queue.set_insert(cid, first["id"])
            write = queue._write_item

            def fail_second(item, *args):
                if item["id"] == second["id"] and item["state"] == "claimed":
                    raise OSError("disk full")
                return write(item, *args)

            with patch.object(queue, "_write_item", side_effect=fail_second), self.assertRaises(OSError):
                queue.claim_insert_batch(cid, resume_all=True)
            self.assertEqual([item["state"] for item in queue.list(cid)["items"]], ["inserting", "queued"])
            reopened = ConversationQueue(Path(directory))
            self.assertEqual([item["content"] for item in reopened.claim_insert_batch(cid, resume_all=True)],
                             ["first", "second"])

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

    def test_stop_holds_queue_until_explicit_send(self) -> None:
        cid = "stop-handoff-01"
        queue = ConversationQueue()
        mesh = MeshState(input_queue=queue)
        app = _App(queue)
        app.session_contexts = _IdleContexts()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        app.store = SessionStore(Path(folder.name))
        runner = SessionRunner(app=app, mesh=mesh, store_for=lambda _cid: app.store)
        self.addCleanup(runner.shutdown)
        mesh.set_activator(runner.start)
        entered = threading.Event()
        finish = threading.Event()
        self.addCleanup(finish.set)
        delivered = threading.Event()
        inputs = []

        def execute(_cid, text, attachments=None, resume=None, sender=None,
                    from_queue=False, meta=None):
            inputs.append(text)
            if text == "first":
                entered.set()
                finish.wait(3)
            else:
                inputs.extend(e.data["content"] for e in app.store.load(cid))
                delivered.set()

        runner._execute = execute
        self.assertTrue(runner.start(cid, {"content": "first"}))
        self.assertTrue(entered.wait(2))
        self.assertTrue(runner.request_cancel(cid))
        insert = queue.enqueue(cid, content="context")
        queue.set_insert(cid, insert["id"])
        mesh.activate_inserts(cid)
        self.assertTrue(mesh.submit(cid, {"content": "ordinary"})["queued"])
        finish.set()
        self.assertTrue(runner.wait_idle(cid, timeout=3))
        self.assertFalse(delivered.is_set())
        self.assertEqual(app.store.load(cid), [])
        self.assertEqual(queue.size(cid), 2)
        self.assertTrue(mesh.is_stopped(cid))
        late = mesh.submit(cid, {"content": "convert while stopped"})["queue_item"]
        queue.set_insert(cid, late["id"])
        mesh.activate_inserts(cid)
        self.assertEqual(app.store.load(cid), [])
        self.assertFalse(mesh.is_running(cid))

        result = mesh.submit(cid, {"content": "new user input"}, user_send=True)
        self.assertTrue(result["run_id"])
        self.assertTrue(delivered.wait(3))
        self.assertTrue(runner.wait_idle(cid, timeout=3))
        self.assertEqual(inputs, ["first", "", "context", "convert while stopped",
                                  "ordinary", "new user input"])
        self.assertFalse(mesh.is_stopped(cid))
        self.assertEqual(queue.size(cid), 0)

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
