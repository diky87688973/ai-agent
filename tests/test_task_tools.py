# -*- coding: utf-8 -*-
"""任务与自主工具测试。

覆盖：run_type 查询 / 切换、todo_list 全动作与校验、user_confirm 两段式、
task_sleep / goal 信封与钳制、模式门控（Plan / Execute）、会话作用域。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.app import build_app  # noqa: E402
from agent.capabilities.tasks.confirm import ApprovalConfirmTool  # noqa: E402
from agent.core import session_scope  # noqa: E402
from agent.core.tool_call import ToolCallRequest  # noqa: E402
from agent.mechanisms.live_state import LiveState  # noqa: E402

CID = "convtest0001"

class _TaskToolsBase(unittest.TestCase):
    """公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.state = LiveState(storage_dir=self.root / "todo")
        self.app = build_app(live_state=self.state)
        self._seq = 0

    def _call(self, name, arguments=None, cid=CID):
        from agent.core.ports import ToolPort

        self._seq += 1
        call = ToolCallRequest(call_id=f"c{self._seq}", name=name, arguments=arguments or {})
        port = ToolPort(
            registry=self.app.registry,
            pipeline=self.app.pipeline,
            app=self.app.context,
            sessions=self.app.session_contexts,
        )
        return port.execute(call, conversation_id=cid or "")

class RunTypeTest(_TaskToolsBase):
    def test_query_default_auto(self):

        r = self._call("run_type", {})
        self.assertTrue(r.ok)
        self.assertEqual(r.data, {"run_type": "auto", "action": "query"})

    def test_switch_and_query(self):

        r = self._call("run_type", {"run_type": "execute"})
        self.assertEqual(r.data, {"run_type": "execute", "action": "switch"})
        self.assertEqual(self._call("run_type", {}).data["run_type"], "execute")
        r2 = self._call("run_type", {"run_type": "plan"})
        self.assertEqual(r2.data["action"], "switch")
        self.assertEqual(self._call("run_type", {}).data["run_type"], "plan")

    def test_auto_clears_override(self):

        self._call("run_type", {"run_type": "plan"})
        r = self._call("run_type", {"run_type": "auto"})
        self.assertEqual(r.data, {"run_type": "auto", "action": "switch"})
        self.assertEqual(self.state.get_mode(CID), "auto")
        self.assertEqual(self._call("run_type", {}).data["run_type"], "auto")

    def test_invalid_value_falls_back_to_query(self):

        r = self._call("run_type", {"run_type": "weird"})
        self.assertTrue(r.ok)
        self.assertEqual(r.data["action"], "query")

    def test_requires_session_scope(self):

        r = self._call("run_type", {}, cid=None)
        self.assertFalse(r.ok)
        self.assertIn("conversation_id", r.error)

class TodoListTest(_TaskToolsBase):
    def _create(self, items=None):
        return self._call("todo_list", {"action": "create", "items": items if items is not None else ["a", "b", "c"]})

    def test_create_and_shape(self):

        r = self._create(["alpha", {"text": "beta", "done": True}])
        self.assertTrue(r.ok)
        self.assertEqual(len(r.data["list_id"]), 12)
        self.assertEqual(r.data["items"], [{"text": "alpha", "done": False}, {"text": "beta", "done": True}])
        self.assertFalse(r.data["collapsed"])

    def test_create_replaces_and_validates(self):

        first = self._create(["a"])
        r = self._create(["x", "y"])
        self.assertNotEqual(r.data["list_id"], first.data["list_id"])
        for bad in ([], [""], [123], "notalist"):
            rr = self._call("todo_list", {"action": "create", "items": bad})
            self.assertFalse(rr.ok, msg=str(bad))

    def test_check_uncheck_and_bounds(self):

        self._create()
        r = self._call("todo_list", {"action": "check", "indices": [0, 2]})
        self.assertEqual([it["done"] for it in r.data["items"]], [True, False, True])
        self.assertEqual(r.data["checked"], [0, 2])
        r2 = self._call("todo_list", {"action": "uncheck", "indices": 2})
        self.assertFalse(r2.data["items"][2]["done"])
        bad = self._call("todo_list", {"action": "check", "indices": [1, 9]})
        self.assertFalse(bad.ok)
        self.assertIn("越界", bad.error)
        self.assertFalse(self.state.get_todo(CID)["items"][1]["done"])  # 整体拒绝：不改状态

    def test_add_remove_replace(self):

        self._create()
        r = self._call("todo_list", {"action": "add_item", "text": "new"})
        self.assertEqual([it["text"] for it in r.data["items"]], ["a", "b", "c", "new"])
        r2 = self._call("todo_list", {"action": "add_item", "text": "ins", "item_index": 0})
        self.assertEqual([it["text"] for it in r2.data["items"]], ["ins", "a", "b", "c", "new"])
        r3 = self._call("todo_list", {"action": "remove_item", "item_index": 0})
        self.assertEqual([it["text"] for it in r3.data["items"]], ["a", "b", "c", "new"])
        r4 = self._call("todo_list", {"action": "replace_item", "item_index": 3, "text": "done!"})
        self.assertEqual(r4.data["items"][3]["text"], "done!")
        for args in ({"action": "add_item"}, {"action": "replace_item", "item_index": 0}, {"action": "remove_item", "item_index": 99}):
            self.assertFalse(self._call("todo_list", args).ok, msg=str(args))

    def test_no_list_unknown_and_query_close(self):

        r = self._call("todo_list", {"action": "check", "indices": [0]})
        self.assertFalse(r.ok)
        self.assertIn("无活跃清单", r.error)
        self.assertIsNone(self._call("todo_list", {"action": "query"}).data)
        self._create()
        self.assertTrue(self._call("todo_list", {"action": "collapse"}).data["collapsed"])
        self.assertEqual([it["text"] for it in self._call("todo_list", {"action": "query"}).data], ["a", "b", "c"])
        self.assertEqual(self._call("todo_list", {"action": "close"}).data, {"close": True})
        self.assertIsNone(self._call("todo_list", {"action": "query"}).data)
        self.assertFalse(self._call("todo_list", {"action": "nope"}).ok)
        self.assertFalse(self._call("todo_list", {}).ok)

    def test_persistence_reload(self):

        r = self._create(["p1", "p2"])
        lid = r.data["list_id"]
        other = LiveState(storage_dir=self.root / "todo")
        loaded = other.get_todo(CID)
        self.assertEqual(loaded["list_id"], lid)
        self.assertEqual([it["text"] for it in loaded["items"]], ["p1", "p2"])

    def test_persistence_tolerance_and_cid_defense(self):

        fp = self.root / "todo" / f"{CID}.json"
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text("{ bad json", encoding="utf-8")
        other = LiveState(storage_dir=self.root / "todo")
        self.assertIsNone(other.get_todo(CID))
        r = self._call("todo_list", {"action": "create", "items": ["x"]}, cid="short")
        self.assertTrue(r.ok)
        self.assertFalse((self.root / "todo" / "short.json").exists())

class UserConfirmTest(_TaskToolsBase):
    def test_pending_envelope(self):

        r = self._call("user_confirm", {"title": "选哪个？", "confirms": ["A", "B"], "multi": True})
        self.assertFalse(r.ok)
        self.assertIn("UserConfirmRequired", r.error)
        self.assertEqual(r.data["title"], "选哪个？")
        self.assertEqual(r.data["confirms"], ["A", "B"])
        self.assertTrue(r.data["multi"])

    def test_confirm_roundtrip(self):

        r = self._call("user_confirm", {"confirm": "A"})
        self.assertTrue(r.ok)
        self.assertEqual(r.data, {"confirm": "A"})
        r2 = self._call("user_confirm", {"confirm": "B", "confirm_id": "cid-1"})
        self.assertEqual(r2.data, {"confirm": "B", "confirm_id": "cid-1"})

    def test_validations(self):

        cases = (
            {"title": "t"},
            {"title": "t", "confirms": []},
            {"title": "t", "confirms": ["", "x"]},
            {"confirms": ["A"]},
            {"title": "t", "confirms": ["A"], "custom_option_index": 3},
        )
        for args in cases:
            self.assertFalse(self._call("user_confirm", args).ok, msg=str(args))

    def test_interactive_flag_is_ignored_without_host_support(self):
        """宿主未注入 TTY 能力时，旧 interactive 入参不能阻断两段式确认。"""

        params = self.app.registry.get("user_confirm").parameters
        for hidden in ("interactive", "confirm", "confirm_id"):
            self.assertNotIn(hidden, params)
        r = self._call("user_confirm", {"title": "t", "confirms": ["A", "B"], "interactive": True})
        self.assertFalse(r.ok)
        self.assertIn("UserConfirmRequired", r.error)
        self.assertEqual(r.data["confirms"], ["A", "B"])

    def test_envelope_still_works_without_tty(self):
        """无 TTY 时不给 interactive，必须照常返回待确认信封（宿主 UI 负责交互）。"""

        r = self._call("user_confirm", {"title": "选哪个？", "confirms": ["A", "B"]})
        self.assertFalse(r.ok)
        self.assertIn("UserConfirmRequired", r.error)
        self.assertEqual(r.data["confirms"], ["A", "B"])

class ApprovalConfirmTest(_TaskToolsBase):
    def setUp(self) -> None:
        super().setUp()
        self.assertIsNone(self.app.registry.get("approval_confirm"))
        self.app.registry.register(ApprovalConfirmTool())

    def test_suspends_with_approval_envelope(self):

        r = self._call("approval_confirm", {
            "option_id": "video-1",
            "option_desc": "提示词已修正完毕，是否准许生成视频？",
        })
        self.assertFalse(r.ok)
        self.assertTrue(r.await_user)
        self.assertIn("ApprovalRequired", r.error)
        self.assertEqual(r.data["kind"], "approval")
        self.assertEqual(r.data["title"], "审批")
        self.assertEqual(r.data["option_id"], "video-1")
        self.assertEqual(r.data["option_desc"], "提示词已修正完毕，是否准许生成视频？")

    def test_rejects_blank_or_forged_id(self):

        self.assertFalse(self._call("approval_confirm", {"option_desc": "是否准许？"}).ok)
        self.assertFalse(self._call("approval_confirm", {"option_id": "  ", "option_desc": "是否准许？"}).ok)
        self.assertFalse(self._call("approval_confirm", {"option_id": "video-1"}).ok)
        forged = self._call("approval_confirm", {
            "option_id": "video-1",
            "option_desc": "是否准许？",
            "approval_id": "apv_forged",
        })
        self.assertFalse(forged.ok)
        self.assertIn("不接收 approval_id", forged.error)

    def test_suspend_is_remembered_on_the_session(self):
        """挂起信封进会话上下文，回合结束只清待审批，不清已签发的通行证。"""

        from agent.core.engine import Engine
        from agent.core.events import Event
        from agent.core.session_context import SessionContext

        ctx = SessionContext(conversation_id=CID)
        engine = Engine(conversation_id=CID, modules=[], session_context=ctx)
        engine._remember_suspend(Event("tool_suspended", {
            "call_id": "c1",
            "envelope": {
                "kind": "approval",
                "title": "审批",
                "option_id": "video-1",
                "option_desc": "是否准许生成视频？",
            },
        }))
        self.assertEqual(ctx.pending_confirm["kind"], "approval")
        self.assertEqual(ctx.pending_confirm["option_id"], "video-1")
        aid = ctx.grant_approval("video-1")
        engine._remember_suspend(Event("turn_ended", {"paused": False}))
        self.assertIsNone(ctx.pending_confirm)
        self.assertEqual(ctx.approvals[aid], "video-1")

class TaskSleepAutonomousTest(_TaskToolsBase):
    def test_sleep_ok_and_clamp(self):

        r = self._call("task_sleep", {"seconds": 60, "reminder": "r" * 600})
        self.assertTrue(r.ok)
        self.assertEqual(r.data["action"], "sleep")
        self.assertEqual(r.data["seconds"], 60)
        self.assertEqual(len(r.data["reminder"]), 500)
        self.assertEqual(self.state.get_sleep(CID)["seconds"], 60)

    def test_sleep_bounds(self):

        for bad in (0, 86401, -3, "abc"):
            self.assertFalse(self._call("task_sleep", {"seconds": bad}).ok, msg=str(bad))
        for good in (1, 86400):
            self.assertTrue(self._call("task_sleep", {"seconds": good}).ok, msg=str(good))

    def test_goal_shapes(self):
        """目标工具：建 / 查 / 改 / 暂停 / 恢复 / 达成 / 删，以及触发文案的语义。"""

        r = self._call("goal", {"action": "get"})
        self.assertTrue(r.ok)
        self.assertIsNone(r.data["goal"])

        r = self._call("goal", {"action": "create", "text": "把 README 补全"})
        self.assertTrue(r.ok)
        self.assertEqual(r.data["goal"]["status"], "active")
        self.assertEqual(self.state.goal_trigger_text(CID), "把 README 补全")

        r = self._call("goal", {"action": "update", "text": "补全 README 并加示例"})
        self.assertEqual(r.data["goal"]["text"], "补全 README 并加示例")

        self._call("goal", {"action": "pause"})
        self.assertEqual(self.state.goal_trigger_text(CID), "")
        self._call("goal", {"action": "resume"})
        self.assertEqual(self.state.goal_trigger_text(CID), "补全 README 并加示例")

        self._call("goal", {"action": "done"})
        self.assertEqual(self.state.goal_trigger_text(CID), "")

        self.assertTrue(self._call("goal", {"action": "delete"}).data["deleted"])
        self.assertFalse(self._call("goal", {"action": "delete"}).data["deleted"])

        # 参数错误经管线翻成 ok=False（工具内 raise，不终止回合）
        self.assertFalse(self._call("goal", {"action": "create"}).ok)
        self.assertFalse(self._call("goal", {"action": "bogus"}).ok)

    def test_resume_creates_missing_goal_from_text(self):
        r = self._call("goal", {"action": "resume", "text": "继续往下讲"})
        self.assertTrue(r.ok)
        self.assertEqual(r.data["goal"]["status"], "active")
        self.assertEqual(r.data["goal"]["text"], "继续往下讲")
        self.assertEqual(self.state.goal_trigger_text(CID), "继续往下讲")

    def test_resume_replaces_existing_goal_text(self):
        self._call("goal", {"action": "create", "text": "旧目标"})
        self._call("goal", {"action": "pause"})
        r = self._call("goal", {"action": "resume", "text": "新目标"})
        self.assertTrue(r.ok)
        self.assertEqual(r.data["goal"]["status"], "active")
        self.assertEqual(r.data["goal"]["text"], "新目标")
        self.assertEqual(self.state.goal_trigger_text(CID), "新目标")

class ModeGateTest(_TaskToolsBase):
    def _preview_ready(self, name):
        prev = self._call("write_file", {"path": str(self.root / name), "content": "hi"})
        self.assertTrue(prev.ok)
        cid = prev.data["confirm_id"]
        # 会话级门控：预览登记在 CID 会话桶，确认须取同一会话的门控
        self.app.gate_for(CID).confirm(cid)
        return cid

    def test_plan_blocks_commit(self):

        self._call("run_type", {"run_type": "plan"})
        cid = self._preview_ready("gateplan.txt")
        r = self._call("commit_write", {"confirm_id": cid})
        self.assertFalse(r.ok)
        self.assertIn("ModeConflict", r.error)
        self._call("run_type", {"run_type": "auto"})
        r2 = self._call("commit_write", {"confirm_id": cid})
        self.assertTrue(r2.ok, msg=r2.error)

    def test_execute_requires_todo(self):

        self._call("run_type", {"run_type": "execute"})
        cid = self._preview_ready("gateexec.txt")
        r = self._call("commit_write", {"confirm_id": cid})
        self.assertFalse(r.ok)
        self.assertIn("ModeConflict", r.error)
        self._call("todo_list", {"action": "create", "items": ["step"]})
        r2 = self._call("commit_write", {"confirm_id": cid})
        self.assertTrue(r2.ok, msg=r2.error)

    def test_plan_blocks_commands(self):

        self._call("run_type", {"run_type": "plan"})
        r = self._call("run_command", {"command": "echo hi"})
        self.assertFalse(r.ok)
        self.assertIn("ModeConflict", r.error)
        r2 = self._call("python_inline", {"code": "print(1)"})
        self.assertFalse(r2.ok)
        self.assertIn("ModeConflict", r2.error)

class SessionScopeTest(_TaskToolsBase):
    def test_scope_set_and_restored(self):

        self.assertEqual(session_scope.current_session_id(), "")
        r = self._call("run_type", {})
        self.assertTrue(r.ok)
        self.assertEqual(session_scope.current_session_id(), "")
        r2 = self._call("todo_list", {"action": "query"}, cid=None)
        self.assertFalse(r2.ok)

if __name__ == "__main__":
    unittest.main()
