# -*- coding: utf-8 -*-
"""子 Agent：批次、fork、生命周期、存储隔离与工具入口。"""
from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from agent.app import build_app
from agent.capabilities.registry import ToolPlugin, ToolRegistry, ToolRegistryView
from agent.core.context import SERVICE_SUBAGENTS
from agent.core.events import make_event
from agent.core.model_call import StreamDelta
from agent.mechanisms.live_state import LiveState
from agent.mechanisms.session_store import SessionStore
from agent.subagent.batches import BatchError, BatchStore
from agent.subagent.manager import SubagentError, SubagentManager
from agent.subagent.repository import SubagentRepository
from agent.subagent.seed import completed_turn_prefix, seed_child
from tests.testkit import no_plugins


class _Provider:
    model = "subagent-test"
    allowed_models = ["subagent-test"]

    def stream(self, request):
        yield StreamDelta(kind="text", text="子回答")


class _BlockingProvider:
    model = "subagent-test"
    allowed_models = ["subagent-test"]

    def __init__(self) -> None:
        self.started = __import__("threading").Event()
        self.release = __import__("threading").Event()

    def stream(self, request):
        self.started.set()
        self.release.wait(3)
        yield StreamDelta(kind="text", text="完成")


class _ManagerCase(unittest.TestCase):
    def setUp(self) -> None:
        no_plugins(self)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.store = SessionStore(self.root / "data")
        self.app = build_app(
            provider=_Provider(),
            store=self.store,
            data_root=self.root / "data",
            live_state=LiveState(storage_dir=self.root / "state"),
            plugins_dir=self.root / "plugins",
            plugins_path=self.root / "plugins.ini",
        )
        self.addCleanup(self.app.dispose)
        self.manager = self.app.context.get(SERVICE_SUBAGENTS)

    def _wait(self, child_id: str) -> None:
        deadline = time.time() + 3
        while time.time() < deadline:
            if not self.app.mesh.is_running(child_id):
                return
            time.sleep(0.01)
        self.fail("子 Agent 回合未在时限内结束")


class SessionStorePathTest(unittest.TestCase):
    def test_child_store_shares_sequence_and_separate_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = SessionStore(root / "data")
            child = SessionStore(
                root / "data",
                sessions_dir=root / "data" / "subagent" / "sessions",
                sequence_source=parent,
            )
            parent.add_scan_dir(root / "data" / "subagent" / "sessions")
            first = parent.allocate_seq(1)
            second = child.allocate_seq(1)
            self.assertGreater(second, first)
            child.append("child-store-0001", [make_event("turn_started")])
            self.assertTrue((root / "data" / "subagent" / "sessions"
                             / "child-store-0001.raw").is_file())
            self.assertFalse((root / "data" / "sessions"
                              / "child-store-0001.raw").exists())
            self.assertEqual(child.load("child-store-0001")[0].type, "turn_started")


class BatchStoreTest(unittest.TestCase):
    def test_batch_file_is_capped_and_isolated_by_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = BatchStore(root)
            batch = store.create("parent-0001")
            self.assertTrue((root / "batches" / "parent-0001"
                             / f"{batch.batch}.json").is_file())
            for index in range(10):
                store.add_child(
                    "parent-0001", batch.batch,
                    child_id=f"child-{index:04d}-0000",
                    label=f"任务{index}",
                    context="fresh",
                )
            with self.assertRaises(BatchError):
                store.add_child(
                    "parent-0001", batch.batch,
                    child_id="child-overflow-0000",
                    label="溢出",
                    context="fresh",
                )
            self.assertEqual(store.list_for_parent("parent-0001")[0].children[0].label, "任务0")
            self.assertEqual(store.list_for_parent("parent-0002"), [])


class RegistryVisibilityTest(unittest.TestCase):
    def test_plugin_can_hide_tool_from_subagent(self) -> None:
        class _Tool(ToolPlugin):
            name = "plugin_tool"
            parameters = {}
            def execute(self, arguments):
                return {}

        registry = ToolRegistry()
        dispose = registry.register(_Tool(), owner="demo")
        restore = registry.set_subagent_tools("demo", [])
        child = ToolRegistryView(registry, honor_subagent_hidden=True)
        parent = ToolRegistryView(registry)
        self.assertIsNone(child.get("plugin_tool"))
        self.assertIsNotNone(parent.get("plugin_tool"))
        self.assertIn("plugin_tool", registry.names())
        restore()
        dispose()
        self.assertNotIn("plugin_tool", registry.names())


class RepositoryBoundaryTest(unittest.TestCase):
    def test_explicit_batch_history_and_invalid_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = SessionStore(root / "data")
            repo = SubagentRepository(data_root=root / "data", parent_store=parent)
            batch = repo.batches.create("parent-0001")
            child = repo.prepare(
                parent_cid="parent-0001", batch=batch.batch,
                label="边界", context="fresh",
            )
            self.assertTrue(repo.is_child(child.child_id))
            self.assertIs(repo.store_for("missing-child"), parent)
            self.assertEqual(repo.list_batches("parent-0001")[0].batch, batch.batch)
            with self.assertRaises(SubagentError):
                repo.list_batches("parent-0001", "sb-missing")
            with self.assertRaises(SubagentError):
                repo.history("parent-0002", child.child_id)
            self.assertEqual(repo.history("parent-0001", child.child_id)["label"], "边界")
            repo.discard("missing-child")
            with self.assertRaises(SubagentError):
                repo.record("missing-child")
            with self.assertRaises(SubagentError):
                repo.prepare(
                    parent_cid="parent-0001", batch="sb-missing",
                    label="坏批次", context="fresh",
                )

    def test_batch_files_reject_invalid_ids_and_corrupt_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = BatchStore(root)
            with self.assertRaises(BatchError):
                store.create("bad")
            with self.assertRaises(BatchError):
                store.get("parent-0001", "bad")
            with self.assertRaises(BatchError):
                store.get("parent-0001", "sb-missing")
            corrupt = root / "batches" / "parent-0001" / "sb-corrupt.json"
            corrupt.parent.mkdir(parents=True)
            corrupt.write_text("{not json", encoding="utf-8")
            self.assertEqual(store.list_for_parent("parent-0001"), [])


class SeedTest(unittest.TestCase):
    def test_fork_keeps_only_completed_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent_store = SessionStore(root / "data")
            child_store = SessionStore(
                root / "data",
                sessions_dir=root / "data" / "subagent" / "sessions",
                sequence_source=parent_store,
            )
            parent_cid = "parent-seed-0001"
            child_id = "child-seed-0001"
            parent_store.append(parent_cid, [
                make_event("turn_started", conversation_id=parent_cid),
                make_event("model_message", content="完成"),
                make_event("turn_ended", conversation_id=parent_cid),
                make_event("turn_started", conversation_id=parent_cid),
            ])
            seed_child(
                parent_store, child_store,
                child_id=child_id,
                parent_cid=parent_cid,
                batch="sb-seed0001",
                label="fork",
                context="fork",
            )
            events = child_store.load(child_id)
            types = [event.type for event in events]
            self.assertEqual(types[0], "subagent/created")
            self.assertIn("turn_ended", types)
            self.assertNotIn(types[-1], ("turn_started",))
            self.assertEqual(completed_turn_prefix([
                make_event("turn_started"),
                make_event("turn_ended"),
                make_event("turn_started"),
            ])[-1].type, "turn_ended")
            self.assertEqual(completed_turn_prefix([make_event("turn_started")]), [])

    def test_fresh_seed_has_only_created_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent_store = SessionStore(root / "data")
            child_store = SessionStore(
                root / "data",
                sessions_dir=root / "data" / "subagent" / "sessions",
                sequence_source=parent_store,
            )
            child_id = "child-fresh-0001"
            seed_child(
                parent_store, child_store,
                child_id=child_id,
                parent_cid="parent-fresh-0001",
                batch="sb-fresh0001",
                label="fresh",
                context="fresh",
            )
            self.assertEqual([event.type for event in child_store.load(child_id)],
                             ["subagent/created"])


class ManagerTest(_ManagerCase):
    def test_create_starts_turn_and_uses_child_store(self) -> None:
        result = self.manager.create(
            "parent-0001", prompt="执行", label="任务标题", context="fresh",
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["batch"].startswith("sb-"))
        self._wait(result["child_id"])
        events = self.manager.store_for(result["child_id"]).load(result["child_id"])
        self.assertEqual(events[0].type, "subagent/created")
        self.assertIn("子回答", [str(event.data.get("content") or "") for event in events])
        latest = self.manager.result("parent-0001", result["child_id"])
        self.assertEqual(latest["result"], "子回答")
        self.assertFalse((self.root / "data" / "sessions" / f"{result['child_id']}.raw").exists())
        self.assertTrue((self.root / "data" / "subagent" / "sessions"
                         / f"{result['child_id']}.raw").is_file())

    def test_label_required_and_batch_scope(self) -> None:
        with self.assertRaises(SubagentError):
            self.manager.create("parent-0001", prompt="x", label="", context="fresh")
        with self.assertRaises(SubagentError):
            self.manager.list("parent-0001", "sb-invalid")

    def test_restart_restores_idle_children(self) -> None:
        result = self.manager.create("parent-0001", prompt="x", label="持久", context="fresh")
        self._wait(result["child_id"])
        restored = SubagentManager(
            data_root=self.root / "data",
            parent_store=self.store,
            mesh=self.app.mesh,
            queue=self.app.conversation_queue,
        )
        rows = restored.list("parent-0001")
        self.assertEqual(rows["batches"][0]["children"][0]["label"], "持久")
        self.assertEqual(rows["batches"][0]["children"][0]["status"], "idle")

    def test_parent_send_and_permissions(self) -> None:
        first = self.manager.create("parent-0001", prompt="x", label="A", context="fresh")
        self._wait(first["child_id"])
        sent = self.manager.send("parent-0001", first["child_id"], msg="继续")
        self.assertTrue(sent["ok"])
        self._wait(first["child_id"])
        with self.assertRaises(SubagentError):
            self.manager.send("parent-0002", first["child_id"], msg="越权")
        with self.assertRaises(SubagentError):
            self.manager.create(
                first["child_id"], prompt="递归", label="递归", context="fresh",
            )

    def test_child_turn_end_notifies_parent(self) -> None:
        result = self.manager.create("parent-notice-0001", prompt="x", label="完成通知", context="fresh")
        self._wait(result["child_id"])
        self._wait("parent-notice-0001")
        events = self.store.load("parent-notice-0001")
        claimed = [event for event in events if event.type == "input_claimed"]
        self.assertTrue(claimed)
        self.assertEqual(claimed[-1].data.get("_sender"), result["child_id"])
        self.assertEqual(claimed[-1].data.get("content"), "子回答")

    def test_child_can_send_to_parent_with_source(self) -> None:
        result = self.manager.create("parent-0001", prompt="x", label="来源", context="fresh")
        self._wait(result["child_id"])
        self.manager.send_to_parent(result["child_id"], msg="子消息")
        self._wait("parent-0001")
        events = self.store.load("parent-0001")
        claimed = [event for event in events if event.type == "input_claimed"]
        self.assertTrue(claimed)
        self.assertEqual(claimed[-1].data.get("_sender"), result["child_id"])
        self.assertEqual(claimed[-1].data.get("_sender_name"), "来源")

    def test_insert_send_marks_queue_item(self) -> None:
        provider = _BlockingProvider()
        app = build_app(
            provider=provider,
            store=SessionStore(self.root / "data2"),
            data_root=self.root / "data2",
            live_state=LiveState(storage_dir=self.root / "state2"),
            plugins_dir=self.root / "plugins2",
            plugins_path=self.root / "plugins2.ini",
        )
        self.addCleanup(app.dispose)
        manager = app.context.get(SERVICE_SUBAGENTS)
        result = manager.create("parent-0001", prompt="x", label="忙", context="fresh")
        self.assertTrue(provider.started.wait(2))
        sent = manager.send("parent-0001", result["child_id"], msg="插入")
        self.assertTrue(sent["queued"])
        self.assertTrue(sent["inserted"])
        items = app.conversation_queue.list(result["child_id"])["items"]
        self.assertTrue(any(item.get("state") == "inserting" for item in items))
        provider.release.set()
        self._wait(result["child_id"])

    def test_tool_schema_and_list(self) -> None:
        result = self.manager.create("parent-0001", prompt="x", label="工具", context="fresh")
        self._wait(result["child_id"])
        rows = self.manager.list("parent-0001")
        self.assertEqual(rows["counts"]["idle"], 1)
        tool = self.app.registry.get("subagent")
        self.assertIsNotNone(tool)
        self.assertIn("create", tool.parameters["action"]["enum"])
        self.assertIn("result", tool.parameters["action"]["enum"])
        self.assertIsNotNone(self.app.registry.get("subagent_send"))


if __name__ == "__main__":
    unittest.main()
