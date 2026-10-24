# -*- coding: utf-8 -*-
"""后台任务管理器：队列、执行、输出、取消与 cid 隔离。"""
from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

from agent.app import build_app
from agent.capabilities.builtin.background_task import build as build_task_tool
from agent.core.events import Event
from agent.mechanisms.background_tasks import (
    CANCELLED,
    COMPLETED,
    MAX_PENDING_PER_CID,
    MAX_RUNNING_PER_CID,
    QUEUED,
    BackgroundTaskManager,
)


def _py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


class BackgroundTaskManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.notices: list[tuple[str, str]] = []
        self.manager = BackgroundTaskManager(
            [self.root], notice=lambda cid, text: self.notices.append((cid, text))
        )

    def tearDown(self) -> None:
        self.manager.shutdown()
        self._tmp.cleanup()

    def test_completed_output_and_history(self) -> None:
        result = self.manager.create("cid-a", _py("print('hello')"), str(self.root), 10, "hello")
        self.assertTrue(result["ok"])
        task_id = result["task"]["task_id"]
        output = self.manager.output("cid-a", task_id, wait=True, timeout_ms=5000)
        self.assertTrue(output["ok"])
        self.assertIn("hello", output["output"])
        jobs = self.manager.list_tasks(
            "cid-a", result["task"]["batch"], status=COMPLETED
        )["tasks"]
        self.assertEqual([item["task_id"] for item in jobs], [task_id])
        for _ in range(50):
            if self.notices:
                break
            time.sleep(0.02)
        self.assertEqual(len(self.notices), 1)
        self.assertTrue(self.notices[0][1].startswith("<<系统通知>>"))
        self.assertIn(result["task"]["batch"], self.notices[0][1])

    def test_cancel_queued_task(self) -> None:
        # 先塞满运行位，再让下一个任务只能排队。
        for index in range(MAX_RUNNING_PER_CID):
            result = self.manager.create(
                "cid-a", _py("import time; time.sleep(5)"), str(self.root), 30,
                label=f"hold-{index}",
            )
            self.assertTrue(result["ok"])
        queued = self.manager.create(
            "cid-a", _py("print('never')"), str(self.root), 30, label="queued"
        )
        self.assertEqual(queued["task"]["status"], QUEUED)
        task_id = queued["task"]["task_id"]
        cancelled = self.manager.cancel("cid-a", task_id, "test cancel")
        self.assertTrue(cancelled["ok"])
        self.assertEqual(cancelled["task"]["status"], CANCELLED)
        self.assertIsNone(cancelled["task"]["pid"])

    def test_queue_capacity_and_cid_isolation(self) -> None:
        for index in range(MAX_RUNNING_PER_CID):
            self.assertTrue(self.manager.create(
                "cid-a", _py("import time; time.sleep(5)"), str(self.root), 30,
                label=f"hold-{index}",
            )["ok"])
        for index in range(MAX_PENDING_PER_CID):
            self.assertTrue(self.manager.create(
                "cid-a", _py("print(1)"), str(self.root), 30, label=f"wait-{index}",
            )["ok"])
        overflow = self.manager.create("cid-a", _py("print(1)"), str(self.root), 30, "overflow")
        self.assertFalse(overflow["ok"])
        self.assertEqual(overflow["error"], "task_queue_full")
        self.assertEqual(self.manager.snapshot("cid-b")["tasks"], [])

    def test_app_wires_manager_and_tool(self) -> None:
        with tempfile.TemporaryDirectory() as data_dir:
            app = build_app(data_root=Path(data_dir))
            try:
                self.assertIn("background_task", app.registry.names())
                self.assertTrue(app.context.has("background_tasks"))
            finally:
                app.dispose()

    def test_label_required_but_not_unique(self) -> None:
        with self.assertRaises(ValueError):
            self.manager.create("cid-a", _py("print(1)"), str(self.root), 10)
        first = self.manager.create("cid-a", _py("print(1)"), str(self.root), 10, "same")
        second = self.manager.create("cid-a", _py("print(1)"), str(self.root), 10, "same")
        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertNotEqual(first["task"]["batch"], second["task"]["batch"])

    def test_batch_groups_tasks_and_filters_exact_id(self) -> None:
        first = self.manager.create("cid-a", _py("print(1)"), str(self.root), 10, "first")
        batch = first["task"]["batch"]
        second = self.manager.create(
            "cid-a", _py("print(2)"), str(self.root), 10, "second", batch=batch
        )
        other = self.manager.create("cid-a", _py("print(3)"), str(self.root), 10, "other")
        self.assertTrue(second["ok"])
        grouped = self.manager.list_tasks("cid-a", batch)
        self.assertEqual(grouped["total"], 2)
        self.assertEqual(set(item["label"] for item in grouped["tasks"]), {"first", "second"})
        self.assertEqual(grouped["counts"].get("completed", 0) + grouped["counts"].get("running", 0), 2)
        exact = self.manager.list_tasks("cid-a", batch, task_id=second["task"]["task_id"])
        self.assertEqual(exact["total"], 1)
        self.assertEqual(exact["tasks"][0]["label"], "second")
        self.assertNotEqual(other["task"]["batch"], batch)
        with self.assertRaises(ValueError):
            self.manager.list_tasks("cid-a", "")

    def test_batch_returns_all_tasks_without_pagination(self) -> None:
        first = self.manager.create(
            "cid-a", _py("import time; time.sleep(2)"), str(self.root), 30, "task-00"
        )
        batch = first["task"]["batch"]
        for index in range(1, 12):
            result = self.manager.create(
                "cid-a", _py("import time; time.sleep(2)"), str(self.root), 30,
                f"task-{index:02d}", batch=batch,
            )
            self.assertTrue(result["ok"])
        grouped = self.manager.list_tasks("cid-a", batch)
        self.assertEqual(grouped["total"], 12)
        self.assertEqual(len(grouped["tasks"]), 12)

    def test_execution_timeout_and_running_cancel(self) -> None:
        timed = self.manager.create(
            "cid-a", _py("import time; time.sleep(5)"), str(self.root), 1, "timeout"
        )
        self.assertTrue(timed["ok"])
        out = self.manager.output("cid-a", timed["task"]["task_id"], wait=True, timeout_ms=4000)
        self.assertEqual(out["status"], "timed_out")

        running = self.manager.create(
            "cid-a", _py("import time; time.sleep(10)"), str(self.root), 30, "cancel-running"
        )
        self.assertTrue(running["ok"])
        cancelled = self.manager.cancel("cid-a", running["task"]["task_id"], "stop")
        self.assertTrue(cancelled["ok"])
        for _ in range(100):
            out = self.manager.output("cid-a", running["task"]["task_id"])
            if out.get("status") == CANCELLED:
                break
            time.sleep(0.05)
        self.assertEqual(out["status"], CANCELLED)

    def test_argv_is_not_shell_interpreted(self) -> None:
        result = self.manager.create(
            "cid-a", _py("print('a;b')"), str(self.root), 10, "argv"
        )
        self.assertTrue(result["ok"])
        out = self.manager.output("cid-a", result["task"]["task_id"], wait=True, timeout_ms=5000)
        self.assertIn("a;b", out["output"])

    def test_plan_mode_rejects_create(self) -> None:
        from unittest.mock import patch

        from agent.mechanisms.live_state import ModeConflict
        live = type("Live", (), {"get_mode": lambda self, cid: "plan"})()
        tool = build_task_tool(self.manager, live)
        with patch("agent.capabilities.builtin.background_task.current_session_id",
                   return_value="cid-a"), patch(
                       "agent.capabilities.builtin.command_tools.current_session_id",
                       return_value="cid-a"):
            with self.assertRaises(ModeConflict):
                tool.execute({"action": "create", "argv": _py("print(1)"), "label": "plan"})

    def test_tool_dispatch_create_list_output_cancel(self) -> None:
        from unittest.mock import patch
        tool = build_task_tool(self.manager)
        with patch("agent.capabilities.builtin.background_task.current_session_id",
                   return_value="cid-a"):
            created = tool.execute({
                "action": "create", "argv": _py("print(42)"),
                "cwd": str(self.root), "timeout_sec": 10, "label": "tool",
            })
            self.assertTrue(created["ok"])
            task_id = created["task"]["task_id"]
            listed = tool.execute({
                "action": "list", "batch": created["task"]["batch"],
                "task_id": task_id,
            })
            self.assertEqual(listed["total"], 1)
            output = tool.execute({
                "action": "output", "task_id": task_id,
                "wait": True, "timeout_ms": 5000,
            })
            self.assertIn("42", output["output"])
            sleep = tool.execute({
                "action": "create", "argv": _py("import time; time.sleep(10)"),
                "cwd": str(self.root), "timeout_sec": 30, "label": "tool-cancel",
            })
            cancelled = tool.execute({
                "action": "cancel", "task_id": sleep["task"]["task_id"], "reason": "tool",
            })
            self.assertTrue(cancelled["ok"])

    def test_system_notice_metadata_survives_queue_and_history(self) -> None:
        from agent.mechanisms.conversation_queue import ConversationQueue
        from agent.shell.classic_adapter.history import history_items
        from agent.shell.session.queue import input_of

        queue = ConversationQueue()
        item = queue.enqueue(
            "cid-notice-1",
            content="<<系统通知>>\n本消息为 任务管理器 触发的系统通知\n任务批次：b-1 已完结，请查看结果。",
            origin="system",
            delivery="next_pass",
            payload={
                "kind": "system_notice",
                "source": "background_tasks",
                "notice_id": "ntf-1",
                "batch": "b-1",
            },
        )
        queue.set_insert("cid-notice-1", item["id"])
        claimed = queue.claim_insert("cid-notice-1")
        self.assertIsNotNone(claimed)
        _content, _atts, _resume, _sender, meta = input_of(claimed)
        self.assertEqual(meta["kind"], "system_notice")
        self.assertEqual(meta["source"], "background_tasks")
        items, _ = history_items([Event("input_claimed", {
            "content": claimed["content"],
            **meta,
        })])
        self.assertEqual(items[0]["kind"], "system_notice")
        self.assertEqual(items[0]["source"], "background_tasks")
        self.assertEqual(items[0]["notice_id"], "ntf-1")
        self.assertEqual(items[0]["batch"], "b-1")

        from agent.core.modules.input_mod import InputModule
        class _Ports:
            conversation_id = "cid-a"
            def emit(self, type_, **data):
                return Event(type_, dict(data))
        module = InputModule()
        module.feed("notice", meta=meta)
        claimed_events = [ev for ev in module.execute(_Ports())
                          if ev.type == "input_claimed"]
        self.assertEqual(claimed_events[0].data["kind"], "system_notice")

    def test_cwd_outside_root_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.manager.create("cid-a", _py("print(1)"), str(self.root.parent), 10, "outside")


if __name__ == "__main__":
    unittest.main()
