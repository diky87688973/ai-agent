# -*- coding: utf-8 -*-
"""覆盖率补齐：边界分支与公开行为，不依赖外部服务。"""
from __future__ import annotations

import base64
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from agent.app import App
from agent.core.context import AppContext
from agent.core.events import Event
from agent.core.image_embed import (
    build_embed_parts,
    describe_image,
    placeholder_text,
    shrink_image,
    strip_attachment_meta,
    strip_old_images,
)
from agent.core.session_context import SessionContext, SessionContexts
from agent.core.session_log import SessionLog, _tool_envelope, _user_content, ensure_tool_pairs
from agent.core.slot_tree import SlotNode, SlotTree, SlotTreeError
from agent.mechanisms.command_safety import (
    _strip_shell_wrapper,
    check_command_blacklist,
    check_script_content,
    check_text_content,
    decode_output,
    resolve_shell,
    sanitize_output_for_display,
    validate_safe_command,
)
from agent.mechanisms.error_log import ErrorLog
from agent.mechanisms.executors import ExecutorRegistry
from agent.mechanisms.live_state import (
    GoalError,
    LiveState,
    register_command_input_target,
    submit_command_input,
    unregister_command_input_target,
)
from agent.mechanisms.session_title import (
    TitleStore,
    clean_title,
    is_placeholder_title,
    make_provider_title_generator,
)
from agent.session_paths import (
    ensure_layout,
    raw_dir,
    session_root,
    state_dir,
    titles_dir,
)
from agent.subagent.lifecycle import SubagentLifecycle
from agent.subagent.models import SubagentError
from agent.subagent.seed import completed_turn_prefix, seed_child

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class ImageEmbedEdgeTest(unittest.TestCase):
    def test_unknown_bytes_are_not_images(self) -> None:
        self.assertEqual(describe_image(b"not an image"), ("", 0, 0))

    def test_png_dimensions(self) -> None:
        mime, width, height = describe_image(PNG)
        self.assertEqual(mime, "image/png")
        self.assertEqual((width, height), (1, 1))

    def test_invalid_attachments_are_ignored(self) -> None:
        parts, skipped = build_embed_parts(
            [None, {}, {"mime": "", "data_base64": ""},
             {"mime": "", "data_base64": "!!!not-base64"}])
        self.assertEqual(parts, [])
        self.assertEqual(skipped, [])

    def test_budget_skip_is_reported(self) -> None:
        parts, skipped = build_embed_parts(
            [{"mime": "image/png", "data_base64": base64.b64encode(PNG).decode()}],
            max_bytes=1)
        self.assertEqual(parts, [])
        self.assertEqual(skipped, ["0"])
        text = placeholder_text(skipped)
        self.assertIn("1 张图片", text)

    def test_placeholder_with_attachment_id(self) -> None:
        text = placeholder_text(
            ["0"], [{"attachment_id": "att-1"}])
        self.assertIn("att-1", text)

    def test_shrink_zero_side_is_identity(self) -> None:
        self.assertEqual(shrink_image(PNG, max_side=0)[0], PNG)

    def test_strip_old_images_and_attachment_meta(self) -> None:
        messages = [
            {"role": "user", "content": [
                {"type": "text", "text": "old"},
                {"type": "image_url", "attachment_id": "old"},
            ]},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": [
                {"type": "text", "text": "new"},
                {"type": "image_url", "attachment_id": "new"},
            ]},
        ]
        kept, count = strip_old_images(messages, keep_turns=1, max_images=1)
        self.assertEqual(count, 1)
        self.assertIn("read_image", str(kept[0]["content"]))
        cleaned = strip_attachment_meta(kept)
        for message in cleaned:
            if isinstance(message.get("content"), list):
                for part in message["content"]:
                    if isinstance(part, dict):
                        self.assertNotIn("attachment_id", part)


class SlotTreeValidationEdgeTest(unittest.TestCase):
    def test_rejects_duplicate_missing_factory_and_dependency(self) -> None:
        node = SlotNode(path="app/a", factory="x:y")
        with self.assertRaises(SlotTreeError):
            SlotTree([node, SlotNode(path="app/a", factory="x:y")])
        with self.assertRaises(SlotTreeError):
            SlotTree([SlotNode(path="app/a", factory="")])
        with self.assertRaises(SlotTreeError):
            SlotTree([SlotNode(path="bad/a", factory="x:y")])
        with self.assertRaises(SlotTreeError):
            SlotTree([SlotNode(path="app/a", factory="x:y", requires={"x": "app/missing"})])


class SessionContextEdgeTest(unittest.TestCase):
    def test_approval_and_registry(self) -> None:
        ctx = SessionContext(conversation_id="cid-12345678")
        approval = ctx.grant_approval("yes")
        self.assertIn(approval, ctx.approvals)
        with self.assertRaises(ValueError):
            ctx.grant_approval("")
        contexts = SessionContexts(lambda cid: {"cid": cid})
        first = contexts.resolve_sync("cid-12345678")
        self.assertIs(first, contexts.resolve_sync("cid-12345678"))
        self.assertIs(contexts.get("cid-12345678"), first)
        self.assertEqual(contexts.active_count(), 1)
        contexts.release("cid-12345678")
        self.assertEqual(contexts.active_count(), 0)


class SessionLogEdgeTest(unittest.TestCase):
    def test_user_content_invalid_and_budget(self) -> None:
        self.assertEqual(_user_content("hi", None), "hi")
        self.assertEqual(_user_content("hi", [{"mime": "", "data_base64": "x"}]), "hi")

    def test_tool_envelope_errors_and_elapsed(self) -> None:
        self.assertIn('"ok": false', _tool_envelope(ok=False, error="x"))
        self.assertIn('"data": 1', _tool_envelope(ok=True, data=1, elapsed_s="bad"))

    def test_session_log_append_and_derive(self) -> None:
        log = SessionLog()
        log.append([
            Event("input_claimed", {"content": "hello"}),
            Event("model_message", {"content": "thinking"}),
            Event("tool_started", {"call_id": "c1", "name": "x"}),
            Event("tool_done", {"call_id": "c1", "data": {"ok": True}}),
            Event("turn_ended", {}),
        ])
        self.assertEqual(len(log.readonly()), 5)
        self.assertIn("hello", str(log.derive_messages()))
        self.assertEqual(ensure_tool_pairs([]), [])


class TitleEdgeTest(unittest.TestCase):
    def test_clean_title_strips_wrapping_and_clips(self) -> None:
        self.assertEqual(clean_title("“标题：修复登录”"), "修复登录")
        self.assertEqual(len(clean_title("x" * 80)), 32)
        self.assertEqual(clean_title(""), "")

    def test_placeholder_title(self) -> None:
        self.assertTrue(is_placeholder_title(""))
        self.assertTrue(is_placeholder_title("新会话"))
        self.assertFalse(is_placeholder_title("修复登录"))

    def test_provider_generator_and_failure(self) -> None:
        class Delta:
            kind = "text"
            text = "标题"
        class Provider:
            def stream(self, request):
                return iter([Delta()])
        gen = make_provider_title_generator(Provider())
        self.assertEqual(gen([{"role": "user", "content": "hi"}]), "标题")
        self.assertEqual(make_provider_title_generator(None)([]), "")

    def test_title_store_round_trip_and_invalid_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = TitleStore(Path(tmp))
            self.assertTrue(store.save("cid-12345678", "标题"))
            self.assertEqual(store.load("cid-12345678"), "标题")
            self.assertFalse(store.save("bad/id", "x"))
            self.assertEqual(store.load("missing"), "")


class LiveStateEdgeTest(unittest.TestCase):
    def test_mode_todo_and_autonomy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = LiveState(storage_dir=Path(tmp))
            cid = "cid-12345678"
            self.assertEqual(state.get_mode(cid), "auto")
            self.assertEqual(state.set_mode(cid, "plan"), "plan")
            self.assertEqual(state.get_mode(cid), "plan")
            state.set_mode(cid, "auto")
            self.assertEqual(state.get_mode(cid), "auto")
            state.set_todo(cid, {"list_id": "l1", "items": [{"text": "a"}]})
            self.assertTrue(state.has_active_todo(cid))
            self.assertEqual(state.get_todo(cid)["items"][0]["text"], "a")
            state.set_todo(cid, None)
            self.assertFalse(state.has_active_todo(cid))
            state.set_autonomy(cid, True, "run")
            self.assertTrue(state.get_autonomy(cid)["enabled"])

    def test_goal_mutation_and_trigger(self) -> None:
        cid = "cid-12345678"
        state = LiveState()
        self.assertIsNone(state.get_goal(cid))
        self.assertEqual(state.note_goal_round(cid), 0)
        with self.assertRaises(GoalError):
            state.set_goal("", "x")
        with self.assertRaises(GoalError):
            state.set_goal(cid, "")
        state.set_goal(cid, "g")
        self.assertEqual(state.update_goal(cid, text="g2", note="n")["text"], "g2")
        with self.assertRaises(GoalError):
            state.update_goal(cid, status="bad")
        state.update_goal(cid, status="paused")
        self.assertEqual(state.goal_trigger_text(cid), "")
        state.update_goal(cid, status="active")
        self.assertEqual(state.goal_trigger_text(cid), "g2")
        self.assertTrue(state.delete_goal(cid))
        self.assertFalse(state.delete_goal(cid))
        self.assertFalse(state.set_reasoning_effort(cid, "bad"))
        self.assertEqual(state.set_model("", "m"), "")

    def test_command_input_targets(self) -> None:
        progress = {}
        register_command_input_target("cid:call", progress)
        self.assertTrue(submit_command_input("cid:call", "yes"))
        self.assertEqual(progress["_user_input"], "yes")
        unregister_command_input_target("cid:call")
        self.assertFalse(submit_command_input("cid:call", "x"))
        self.assertFalse(submit_command_input("", "x"))
        register_command_input_target("", progress)

    def test_invalid_mode_rejected(self) -> None:
        state = LiveState()
        with self.assertRaises(ValueError):
            state.set_mode("cid-12345678", "bad")

    def test_goal_effort_model_persist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cid = "cid-12345678"
            state = LiveState(storage_dir=Path(tmp))
            goal = state.set_goal(cid, "完成覆盖", note="n")
            self.assertEqual(goal["text"], "完成覆盖")
            self.assertEqual(state.get_goal(cid)["status"], "active")
            self.assertGreaterEqual(state.note_goal_round(cid), 1)
            self.assertIn("完成覆盖", state.goal_trigger_text(cid))
            self.assertEqual(state.set_reasoning_effort(cid, "max"), True)
            self.assertEqual(state.get_reasoning_effort(cid), "max")
            self.assertEqual(state.set_model(cid, "m"), "m")
            self.assertEqual(state.get_model(cid), "m")
            again = LiveState(storage_dir=Path(tmp))
            self.assertEqual(again.get_model(cid), "m")
            self.assertTrue(state.delete_goal(cid))


class CommandSafetyEdgeTest(unittest.TestCase):
    def test_blacklist_and_safe_validation(self) -> None:
        self.assertIsNotNone(check_command_blacklist("format C:"))
        self.assertIsNone(check_script_content("echo ok"))
        with self.assertRaises(ValueError):
            validate_safe_command("echo a & echo b")

    def test_shell_and_output(self) -> None:
        shell, args = resolve_shell("cmd", "echo ok")
        self.assertTrue(shell.lower().endswith("cmd.exe") or "cmd" in shell.lower())
        self.assertEqual(args, ["cmd", "/c"])
        self.assertIn("ok", decode_output(b"ok").lower())
        self.assertIn("输出已截断", sanitize_output_for_display("a\n" * 10, max_chars=5))


class SessionPathsEdgeTest(unittest.TestCase):
    def test_layout_creates_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_layout(root)
            self.assertEqual(session_root(root), root / "session")
            self.assertEqual(state_dir(root), root / "session" / "state")
            self.assertEqual(raw_dir(root), root / "session" / "raw")
            self.assertEqual(titles_dir(root), root / "session" / "titles")
            self.assertTrue(state_dir(root).is_dir())
            self.assertTrue(raw_dir(root).is_dir())
            self.assertTrue(titles_dir(root).is_dir())
            ensure_layout(root)

    def test_layout_preserves_existing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "session" / "raw").mkdir(parents=True)
            (root / "session" / "raw" / "same.raw").write_text("old", encoding="utf-8")
            ensure_layout(root)
            self.assertEqual(
                (root / "session" / "raw" / "same.raw").read_text(encoding="utf-8"),
                "old")


class AppFacadeEdgeTest(unittest.TestCase):
    def test_app_init_and_loop_config(self) -> None:
        app = App(AppContext())
        calls = {}
        app._kernel_group = type("K", (), {"configure_loop": lambda self, **kw: calls.update(kw)})()
        app.apply_agent_loop(image_turns=1, image_max=2, max_passes=3)
        self.assertEqual(calls, {"image_turns": 1, "image_max": 2, "max_passes": 3})
        self.assertEqual(app.context_defaults, {})
        with self.assertRaises(RuntimeError):
            _ = app.gate
        app.dispose()


class ExecutorErrorLogTest(unittest.TestCase):
    def test_executor_registry_without_slots(self) -> None:
        reg = ExecutorRegistry()
        reg.add("x", lambda args: {"ok": True}, "owner")
        self.assertEqual(reg.get("x")({}), {"ok": True})
        self.assertIn("x", reg.names())
        with self.assertRaises(ValueError):
            reg.add("", lambda args: {})
        with self.assertRaises(RuntimeError):
            reg.replace("x", lambda args: {})
        with self.assertRaises(ValueError):
            reg.add("x", None)
        with self.assertRaises(ValueError):
            reg.replace("x", None)
        first = reg.add("y", lambda args: {"y": 1}, "owner")
        first()
        self.assertIsNone(reg.get("y"))
        self.assertGreaterEqual(len(reg.names()), 1)

    def test_error_log_report_and_rotate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = ErrorLog(Path(tmp))
            log.report("tag", "boom", conversation_id="cid")
            self.assertTrue(log.path.is_file())
            self.assertIn("boom", log.path.read_text(encoding="utf-8"))
            with unittest.mock.patch("agent.mechanisms.error_log._MAX_FILE_BYTES", 1):
                log.report("tag", "again")
            self.assertTrue(log.path.with_name("errors.log.1").is_file())


class CommandSafetyMoreTest(unittest.TestCase):
    def test_wrapper_and_more_branches(self) -> None:
        self.assertEqual(_strip_shell_wrapper("cmd /c echo ok"), "echo ok")
        self.assertEqual(_strip_shell_wrapper("echo ok"), "echo ok")
        self.assertIsNotNone(check_text_content("import base64"))
        self.assertIsNotNone(check_text_content("echo x > app.py"))
        self.assertIsNone(check_command_blacklist("echo ok"))
        self.assertIsNone(validate_safe_command("echo ok"))
        with self.assertRaises(ValueError):
            resolve_shell("bad", "x")
        self.assertIn("cmd", resolve_shell("cmd", "x")[0])
        self.assertEqual(sanitize_output_for_display("a\n\n\n\n\nb"), "a\n\n\nb")


class SubagentLifecycleEdgeTest(unittest.TestCase):
    def test_validate_guards(self) -> None:
        mesh = type("M", (), {"get_agent": lambda self, cid: {"role": "subagent"}})()
        life = SubagentLifecycle.__new__(SubagentLifecycle)
        life.mesh = mesh
        with self.assertRaises(SubagentError):
            life._validate("parent", "x", "label", "fork", None)
        mesh.get_agent = lambda cid: {"role": "boss"}
        with self.assertRaises(SubagentError):
            life._validate("", "x", "label", "fork", None)
        with self.assertRaises(SubagentError):
            life._validate("parent", "x", "", "fork", None)
        with self.assertRaises(SubagentError):
            life._validate("parent", "x", "l" * 1000, "fork", None)
        with self.assertRaises(SubagentError):
            life._validate("parent", "x", "label", "bad", None)


class SubagentSeedEdgeTest(unittest.TestCase):
    def test_seed_child_fresh(self) -> None:
        class Store:
            def __init__(self):
                self.rows = []
            def load(self, cid):
                return []
            def append(self, cid, events):
                self.rows.extend(events)
        parent = Store()
        child = Store()
        count = seed_child(parent, child, child_id="c", parent_cid="p",
                           batch="b", label="l", context="fresh")
        self.assertEqual(count, 1)
        self.assertEqual(child.rows[0].type, "subagent/created")
        with self.assertRaises(ValueError):
            seed_child(parent, child, child_id="c", parent_cid="p",
                       batch="b", label="l", context="bad")
        class ForkStore(Store):
            def load(self, cid):
                return [Event("subagent/created", {}), Event("turn_ended", {})]
        fork = ForkStore()
        seed_child(fork, child, child_id="c", parent_cid="p",
                   batch="b", label="l", context="fork")

    def test_completed_turn_prefix(self) -> None:
        rows = [Event("input_claimed", {"content": "x"}),
                Event("turn_ended", {}),
                Event("input_claimed", {"content": "y"})]
        prefix = completed_turn_prefix(rows)
        self.assertEqual([e.type for e in prefix], ["input_claimed", "turn_ended"])
        self.assertEqual(completed_turn_prefix([]), [])


if __name__ == "__main__":
    unittest.main()
