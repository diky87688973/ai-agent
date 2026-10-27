# -*- coding: utf-8 -*-
"""唤醒调度器：注册、到期、恢复、取消与重复投递。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

from agent.app import build_app
from agent.core.context import SERVICE_WAKE_SCHEDULER
from agent.core.events import Event
from agent.core.ports import ToolPort
from agent.core.tool_call import ToolCallRequest
from agent.mechanisms.conversation_queue import ConversationQueue
from agent.mechanisms.live_state import LiveState
from agent.mechanisms.mesh import MeshState
from agent.mechanisms.session_store import SessionStore
from agent.mechanisms.wake_scheduler import (
    STATUS_DELIVERED,
    WakeScheduler,
    parse_due_at,
)


class _Clock:
    def __init__(self, value: float = 1_700_000_000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class WakeSchedulerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="wake-scheduler-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.clock = _Clock()
        self.submitted: List[Dict[str, Any]] = []

    def _submit(self, cid: str, message: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        self.submitted.append({"cid": cid, "message": message, **kwargs})
        return {"queued": True, "run_id": ""}

    def _scheduler(self, *, delivered=None) -> WakeScheduler:
        return WakeScheduler(
            self.root / "wake",
            submit=self._submit,
            delivered=delivered,
            now_fn=self.clock,
        )

    def test_sleep_registers_and_delivers_once(self) -> None:
        scheduler = self._scheduler()
        job = scheduler.schedule_seconds(
            10, target_cid="cid-12345678", owner_cid="cid-12345678",
            reminder="回来继续")
        self.assertEqual(job["status"], "scheduled")
        self.assertEqual(self.submitted, [])
        self.clock.value = job["due_at"]
        scheduler.run_due()
        self.assertEqual(len(self.submitted), 1)
        self.assertEqual(self.submitted[0]["cid"], "cid-12345678")
        self.assertEqual(self.submitted[0]["message"]["meta"]["wake_job_id"], job["job_id"])
        self.assertEqual(scheduler.list_jobs(target_cid="cid-12345678")[0]["status"],
                         STATUS_DELIVERED)
        scheduler.run_due(self.clock.value + 100)
        self.assertEqual(len(self.submitted), 1)

    def test_cancel_prevents_delivery(self) -> None:
        scheduler = self._scheduler()
        job = scheduler.schedule_seconds(
            10, target_cid="cid-12345678", owner_cid="cid-12345678",
            reminder="取消")
        scheduler.cancel(job["job_id"], owner_cid="cid-12345678")
        self.clock.value += 20
        scheduler.run_due()
        self.assertEqual(self.submitted, [])
        self.assertEqual(scheduler.list_jobs()[0]["status"], "canceled")

    def test_restart_recovers_pending_job(self) -> None:
        first = self._scheduler()
        job = first.schedule_seconds(
            10, target_cid="cid-12345678", owner_cid="cid-12345678",
            reminder="重启后继续")
        second = self._scheduler()
        self.clock.value = job["due_at"]
        second.run_due()
        self.assertEqual(len(self.submitted), 1)
        self.assertEqual(self.submitted[0]["message"]["meta"]["wake_job_id"], job["job_id"])

    def test_restart_does_not_repeat_delivered_job(self) -> None:
        first = self._scheduler()
        job = first.schedule_seconds(
            10, target_cid="cid-12345678", owner_cid="cid-12345678",
            reminder="只一次")
        self.clock.value = job["due_at"]
        first.run_due()
        second = self._scheduler()
        second.run_due(self.clock.value)
        self.assertEqual(len(self.submitted), 1)

    def test_list_filters_by_target_and_owner(self) -> None:
        scheduler = self._scheduler()
        scheduler.schedule_seconds(
            10, target_cid="cid-owner-1", owner_cid="cid-owner-1", reminder="a")
        scheduler.schedule_seconds(
            20, target_cid="cid-target-2", owner_cid="cid-owner-1", reminder="b")
        rows = scheduler.list_jobs(owner_cid="cid-owner-1")
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(scheduler.list_jobs(target_cid="cid-target-2")), 1)
        self.assertEqual(rows[0]["reminder"], "a")

    def test_target_must_exist_for_other_session(self) -> None:
        scheduler = WakeScheduler(
            self.root / "wake", submit=self._submit,
            target_exists=lambda _cid: False, now_fn=self.clock)
        with self.assertRaises(ValueError):
            scheduler.schedule_seconds(
                5, target_cid="cid-other-1", owner_cid="cid-owner-1",
                reminder="x")
        job = scheduler.schedule_seconds(
            5, target_cid="cid-owner-1", owner_cid="cid-owner-1", reminder="y")
        self.assertEqual(job["target_cid"], "cid-owner-1")

    def test_invalid_schedules_are_rejected(self) -> None:
        scheduler = self._scheduler()
        with self.assertRaises(ValueError):
            scheduler.schedule_seconds(
                0, target_cid="cid-12345678", owner_cid="cid-12345678",
                reminder="x")
        with self.assertRaises(ValueError):
            scheduler.schedule_at(
                "2000-01-01T00:00:00+00:00",
                target_cid="cid-12345678", owner_cid="cid-12345678", reminder="x")
        with self.assertRaises(ValueError):
            scheduler.schedule_seconds(
                5, target_cid="cid-12345678", owner_cid="cid-12345678", reminder="")

    def test_parse_due_at_normalizes_z(self) -> None:
        due = parse_due_at("2030-01-01T00:00:00Z", now=0)
        self.assertGreater(due, 0)




class RealMeshDispatcherTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="wake-mesh-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.mesh = MeshState()
        self.started: List[Dict[str, Any]] = []
        self.mesh.set_activator(
            lambda cid, message: self.started.append({"cid": cid, "message": message})
            or "run-1")
        self.clock = _Clock()

    def _scheduler(self) -> WakeScheduler:
        return WakeScheduler(
            self.root / "wake", submit=self.mesh.submit, now_fn=self.clock)

    def test_idle_dispatch_goes_through_mesh_activator(self) -> None:
        scheduler = self._scheduler()
        job = scheduler.schedule_seconds(
            5, target_cid="cid-12345678", owner_cid="cid-12345678",
            reminder="到点")
        self.clock.value = job["due_at"]
        scheduler.run_due()
        self.assertEqual(len(self.started), 1)
        self.assertEqual(self.started[0]["cid"], "cid-12345678")
        meta = self.started[0]["message"]["meta"]
        self.assertEqual(meta["wake_job_id"], job["job_id"])

    def test_busy_target_is_queued_with_dedupe_key(self) -> None:
        scheduler = self._scheduler()
        cid = "cid-12345678"
        self.assertTrue(self.mesh.try_begin_run(cid))
        job = scheduler.schedule_seconds(
            5, target_cid=cid, owner_cid=cid, reminder="排队")
        self.clock.value = job["due_at"]
        scheduler.run_due()
        self.assertEqual(self.started, [])
        items = self.mesh.queue._items[cid]
        self.assertEqual(items[0]["dedupe_key"], job["job_id"])
        self.assertEqual(items[0]["payload"]["meta"]["wake_job_id"], job["job_id"])
        self.mesh.end_run(cid)

    def test_process_lock_allows_one_scheduler(self) -> None:
        first = self._scheduler()
        second = self._scheduler()
        self.assertTrue(first.start())
        self.assertFalse(second.start())
        first.stop()
        self.assertTrue(second.start())
        second.stop()

    def test_terminal_jobs_are_pruned(self) -> None:
        from unittest import mock
        scheduler = self._scheduler()
        with mock.patch("agent.mechanisms.wake_scheduler.MAX_TERMINAL_JOBS", 2):
            for index in range(3):
                job = scheduler.schedule_seconds(
                    10 + index, target_cid="cid-12345678",
                    owner_cid="cid-12345678", reminder=f"job-{index}")
                scheduler.cancel(job["job_id"], owner_cid="cid-12345678")
            self.assertEqual(len(scheduler.list_jobs()), 2)


class WakeToolTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="wake-tools-")
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.app = build_app(store=SessionStore(root / "data"), data_root=root,
                             live_state=LiveState(storage_dir=root / "state"))
        self.addCleanup(self.app.dispose)
        self._seq = 0

    def _call(self, name: str, arguments: Dict[str, Any] | None = None):
        self._seq += 1
        port = ToolPort(
            registry=self.app.registry,
            pipeline=self.app.pipeline,
            app=self.app.context,
            sessions=self.app.session_contexts,
        )
        return port.execute(
            ToolCallRequest(call_id=f"c{self._seq}", name=name,
                            arguments=arguments or {}),
            conversation_id="cid-12345678",
        )

    def test_sleep_list_cancel(self) -> None:
        result = self._call("task_sleep", {
            "seconds": 10,
            "reminder": "回来看结果",
            "target_cid": "cid-12345678",
        })
        self.assertTrue(result.ok, result.data)
        job_id = result.data["job_id"]
        listed = self._call("task_wake_list", {"target_cid": "cid-12345678"})
        self.assertTrue(listed.ok, listed.data)
        self.assertEqual(listed.data["jobs"][0]["job_id"], job_id)
        canceled = self._call("task_wake_cancel", {"job_id": job_id})
        self.assertTrue(canceled.ok, canceled.data)
        self.assertEqual(canceled.data["status"], "canceled")

    def test_app_wake_state_helpers(self) -> None:
        cid = "cid-12345678"
        scheduler = self.app.context.get(SERVICE_WAKE_SCHEDULER)
        self.assertFalse(scheduler._target_exists(cid))
        self.assertFalse(scheduler._delivered(cid, "wake-check"))
        self.app.store.append(cid, [Event(type="input_claimed", data={
            "content": "唤醒",
            "wake_job_id": "wake-check",
        })])
        self.assertTrue(scheduler._target_exists(cid))
        self.assertTrue(scheduler._delivered(cid, "wake-check"))
        self.assertFalse(scheduler._delivered(cid, "wake-other"))

    def test_schedule_rejects_past(self) -> None:
        result = self._call("task_schedule", {
            "at": "2000-01-01T00:00:00+00:00",
            "reminder": "旧时间",
        })
        self.assertFalse(result.ok)
        self.assertIn("at", result.error)


class QueueDedupeTest(unittest.TestCase):
    def test_dedupe_key_does_not_create_second_item(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wake-queue-") as tmp:
            queue = ConversationQueue(Path(tmp))
            first = queue.enqueue("cid-12345678", content="wake", origin="system",
                                  dedupe_key="wake-1")
            second = queue.enqueue("cid-12345678", content="wake", origin="system",
                                   dedupe_key="wake-1")
            self.assertEqual(first["id"], second["id"])
            self.assertEqual(queue.size("cid-12345678"), 0)
            self.assertEqual(len(queue._items["cid-12345678"]), 1)


if __name__ == "__main__":
    unittest.main()
