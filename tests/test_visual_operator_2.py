# -*- coding: utf-8 -*-
"""视觉操作 2.0 全局授权与上下文钩子。"""
from __future__ import annotations

import ctypes
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from agent.core.context import ToolTurnContext
from agent.core.session_scope import reset_tool_turn_context, set_tool_turn_context
from plugins.visual_operator_2 import plugin as _PLUGIN
from plugins.visual_operator_2.config import VisionConfig
from plugins.visual_operator_2.plugin import _observation_hook, _step_log_path
from plugins.visual_operator_2.routes import build_routes
from plugins.visual_operator_2.state import VisionRuntime
from plugins.visual_operator_2.tools import VisionRequestOpenTool, VisionStartTool, VisionStopTool


class InjectedInputTagTest(unittest.TestCase):
    def test_injected_inputs_carry_foreign_tag(self) -> None:
        from plugins.visual_operator_2 import backend

        if not getattr(backend, "_WINDOWS", False):
            self.skipTest("Windows-only SendInput")
        captured = []

        def fake_send(count, events, size):
            for index in range(count):
                event = events[index]
                if event.type == backend._INPUT_MOUSE:
                    captured.append(int(event.union.mi.dwExtraInfo))
                else:
                    captured.append(int(event.union.ki.dwExtraInfo))
            return count

        with patch.object(backend, "_u", SimpleNamespace(SendInput=fake_send)):
            backend.click("left", 1)
            backend.press_keys(["a"])
        self.assertEqual(captured, [backend.FOREIGN_INJECT_TAG] * 4)

    def test_registered_tag_filters_keyboard_even_with_injected_bit(self) -> None:
        from plugins.visual_operator_2 import backend

        if not getattr(backend, "_WINDOWS", False):
            self.skipTest("Windows-only keyboard hook")
        fired = []
        monitor = backend.HumanInputMonitor()
        monitor.bind(lambda: fired.append("fired"))
        monitor.register_inject_tag(backend.FOREIGN_INJECT_TAG)
        event = backend._KeyboardHookStruct()
        event.vkCode = 0x77
        event.flags = backend._LLKHF_INJECTED
        event.dwExtraInfo = backend.FOREIGN_INJECT_TAG
        with patch.object(
                backend, "_u",
                SimpleNamespace(CallNextHookEx=lambda *args: 0)):
            monitor._on_keyboard(0, 0, ctypes.addressof(event))
        self.assertEqual(fired, [])


class VisionRuntimeTest(unittest.TestCase):
    def _runtime(self) -> VisionRuntime:
        config = VisionConfig(fps=30, focus_width=80, focus_height=60)
        return VisionRuntime(
            config,
            capture=lambda: Image.new("RGB", (320, 240), (40, 80, 120)),
            cursor=lambda: (160, 120),
        )

    def test_consent_owner_and_observation(self) -> None:
        runtime = self._runtime()
        try:
            request = runtime.request_open("cid-a", "call-a")
            self.assertTrue(request["ok"])
            self.assertFalse(runtime.request_open("cid-b", "call-b")["ok"])
            grant = runtime.confirm("cid-a", request["request_id"], "agree")
            self.assertTrue(grant["ok"])
            self.assertTrue(runtime.start("cid-a", grant["consent_id"])["ok"])
            time.sleep(0.15)
            observation = runtime.observe("cid-a")
            self.assertIsNotNone(observation)
            assert observation is not None
            self.assertIn("cursor_model", observation["text"])
            self.assertNotIn("screen_size", observation["text"])
            self.assertTrue(observation["frames"])
            self.assertTrue(any("LATEST" in str(item.get("label") or "")
                                for item in observation["images"]))
            self.assertTrue(any(str(item.get("url") or "").split(",")[0] == "data:image/webp;base64"
                                for item in observation["images"]))
            self.assertEqual(observation["focus_image"], "")
            self.assertEqual(observation["focus"], {})
            self.assertIsNone(runtime.observe("cid-b"))
            self.assertFalse(runtime.start("cid-a", grant["consent_id"])["ok"])
            self.assertTrue(runtime.stop("cid-a")["ok"])
            self.assertIsNone(runtime.observe("cid-a"))
        finally:
            runtime.close()

    def test_observation_includes_multiple_frames(self) -> None:
        runtime = VisionRuntime(
            VisionConfig(fps=30, queue_size=4, settle_ms=0),
            capture=lambda: Image.new("RGB", (320, 240), (40, 80, 120)),
            cursor=lambda: (160, 120),
        )
        try:
            request = runtime.request_open("cid-a", "call-a")
            grant = runtime.confirm("cid-a", request["request_id"], "agree")
            runtime.start("cid-a", grant["consent_id"])
            time.sleep(0.18)
            observation = runtime.observe("cid-a")
            assert observation is not None
            self.assertGreaterEqual(len(observation["frames"]), 2)
            self.assertGreaterEqual(len(observation["images"]), 2)
            self.assertIn("frames=", observation["text"])
            latest = observation["images"][-1]
            self.assertIn("LATEST", str(latest.get("label") or ""))
            self.assertEqual(observation["full_image"], latest.get("url"))
        finally:
            runtime.close()

    def test_on_demand_capture_replaces_background_sampling(self) -> None:
        calls = []

        def capture():
            calls.append(1)
            return Image.new("RGB", (320, 240), (40, 80, 120))

        runtime = VisionRuntime(
            VisionConfig(fps=0, queue_size=3, settle_ms=0),
            capture=capture,
            cursor=lambda: (160, 120),
        )
        try:
            request = runtime.request_open("cid-a", "call-a")
            grant = runtime.confirm("cid-a", request["request_id"], "agree")
            runtime.start("cid-a", grant["consent_id"])
            time.sleep(0.05)
            observation = runtime.observe("cid-a")
            assert observation is not None
            self.assertGreaterEqual(len(calls), 2)
            self.assertGreaterEqual(len(observation["frames"]), 2)
        finally:
            runtime.close()

    def test_new_consent_call_supersedes_pending_request(self) -> None:
        runtime = self._runtime()
        try:
            first = runtime.request_open("cid-a", "call-a")
            second = runtime.request_open("cid-a", "call-b")
            self.assertNotEqual(first["request_id"], second["request_id"])
            self.assertFalse(second["reused"])
            self.assertFalse(runtime.confirm(
                "cid-a", first["request_id"], "agree")["ok"])
            self.assertTrue(runtime.confirm(
                "cid-a", second["request_id"], "agree")["ok"])
        finally:
            runtime.close()

    def test_reject_does_not_open(self) -> None:
        runtime = self._runtime()
        try:
            request = runtime.request_open("cid-a", "call-a")
            result = runtime.confirm("cid-a", request["request_id"], "reject")
            self.assertEqual(result["decision"], "reject")
            self.assertEqual(result["consent_id"], "")
            self.assertFalse(runtime.start("cid-a", "missing")["ok"])
        finally:
            runtime.close()

    def test_context_hook_appends_full_frame(self) -> None:
        runtime = self._runtime()
        try:
            request = runtime.request_open("cid-a", "call-a")
            grant = runtime.confirm("cid-a", request["request_id"], "agree")
            runtime.start("cid-a", grant["consent_id"])
            time.sleep(0.15)
            messages = _observation_hook(runtime)(
                [{"role": "user", "content": "hi"}], "cid-a")
            self.assertEqual(messages[-1]["role"], "user")
            parts = messages[-1]["content"]
            self.assertGreaterEqual(sum(1 for p in parts if p["type"] == "image_url"), 1)
            self.assertEqual(parts[0]["type"], "text")
            self.assertTrue(any(p.get("type") == "text" and "FRAME" in str(p.get("text"))
                                for p in parts))
            self.assertTrue(any(p.get("type") == "image_url" for p in parts))
        finally:
            runtime.close()

    def test_context_hook_publishes_exact_model_frame(self) -> None:
        events = []
        config = VisionConfig(fps=30, focus_width=80, focus_height=60)
        runtime = VisionRuntime(
            config,
            publish=lambda event, payload: events.append((event, payload)) or 0,
            capture=lambda: Image.new("RGB", (320, 240), (40, 80, 120)),
            cursor=lambda: (160, 120),
        )
        try:
            request = runtime.request_open("cid-a", "call-a")
            grant = runtime.confirm("cid-a", request["request_id"], "agree")
            runtime.start("cid-a", grant["consent_id"])
            time.sleep(0.15)
            _observation_hook(runtime)([{"role": "user", "content": "hi"}], "cid-a")
            frames = [payload for event, payload in events if event == "vision_frame"]
            self.assertEqual(len(frames), 1)
            payload = frames[0]
            self.assertEqual(payload["conversation_id"], "cid-a")
            self.assertEqual(payload["source"], "model_input")
            self.assertEqual(payload["screen_size"], [320, 240])
            self.assertEqual(payload["full_size"], [320, 240])
            self.assertEqual(payload["coordinate_space"], "model_image")
            self.assertGreater(payload["full_scale"], 0)
            self.assertTrue(payload["full_image"].startswith("data:image/"))
            self.assertEqual(payload["focus_image"], "")
        finally:
            runtime.close()

    def test_confirm_route_resumes_pending_call(self) -> None:
        runtime = self._runtime()
        routes = {}
        resumed = []

        class Ctx:
            def add_route(self, method, path, handler, **_kwargs):
                routes[(method, path)] = handler
                return lambda: None

            def resume_suspended(self, cid, call_id, **kwargs):
                resolved = kwargs["resolve"](None, {"call_id": call_id})
                resumed.append((cid, call_id, resolved["data"], kwargs))
                return {"ok": True, **resolved["response"]}

        try:
            build_routes(Ctx(), runtime)
            request = runtime.request_open("cid-a", "call-a")
            handler = routes[("POST", "eye-consent/confirm")]
            status, payload = handler({"body": {
                "conversation_id": "cid-a",
                "request_id": request["request_id"],
                "call_id": "call-a",
                "choice": "agree",
            }})
            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(resumed[0][0], "cid-a")
            self.assertEqual(resumed[0][1], "call-a")
            self.assertEqual(resumed[0][2]["consent_id"], payload["consent_id"])
        finally:
            runtime.close()

    def test_confirm_after_runtime_restart_uses_durable_request_identity(self) -> None:
        import tempfile
        from pathlib import Path

        from agent.app import App
        from agent.core.events import Event
        from agent.core.session_context import SessionContext
        from agent.mechanisms.session_store import SessionStore
        from plugins.visual_operator_2.routes import make_confirm

        cid, call_id = "vision-restart", "vision-call"
        original = self._runtime()
        request_id = original.request_open(cid, call_id)["request_id"]
        original.close()
        runtime = self._runtime()
        self.addCleanup(runtime.close)
        with tempfile.TemporaryDirectory() as folder:
            store = SessionStore(Path(folder))
            store.append(cid, [Event("tool_suspended", {
                "call_id": call_id, "name": "vision_request_open",
                "envelope": {"kind": "vision_consent", "request_id": request_id,
                             "conversation_id": cid},
            })])
            session = SessionContext()
            app = SimpleNamespace(
                store=store,
                session_contexts=SimpleNamespace(resolve_sync=lambda _cid: session),
                mesh=SimpleNamespace(is_stopped=lambda _cid: False,
                                     submit=lambda *_args, **_kwargs: {"run_id": "continued"}),
            )
            ctx = SimpleNamespace(resume_suspended=lambda *args, **kw: App.resume_suspended(app, *args, **kw))
            confirm = make_confirm(ctx, runtime)
            body = {"conversation_id": cid, "call_id": call_id, "choice": "agree"}
            self.assertIsNone(runtime.pending(cid))
            self.assertEqual(confirm({"body": {**body, "request_id": "old-request"}})[0], 409)
            self.assertEqual([event.type for event in store.load(cid)], ["tool_suspended"])
            status, response = confirm({"body": {**body, "request_id": request_id}})
            self.assertEqual(status, 200, response)
            self.assertTrue(response["consent_id"])
            result = next(event for event in store.load(cid) if event.type == "tool_done")
            self.assertEqual(result.data["data"]["consent_id"], response["consent_id"])
            self.assertEqual(confirm({"body": {**body, "request_id": request_id}})[0], 409)

    def test_tools_require_consent_and_close_cleanly(self) -> None:
        runtime = self._runtime()
        request_tool = VisionRequestOpenTool(runtime)
        start_tool = VisionStartTool(runtime)
        stop_tool = VisionStopTool(runtime)
        token = set_tool_turn_context(ToolTurnContext(
            session=SimpleNamespace(conversation_id="cid-a"),
            call=SimpleNamespace(call_id="call-a"),
        ))
        try:
            with self.assertRaises(Exception) as raised:
                request_tool.execute({})
            self.assertTrue(raised.exception.data["request_id"].startswith(
                "consent_req_"))
            self.assertFalse(start_tool.execute({"consent_id": "forged"}).get("ok"))
            request = runtime.request_open("cid-a", "call-a")
            grant = runtime.confirm("cid-a", request["request_id"], "agree")
            self.assertTrue(start_tool.execute(
                {"consent_id": grant["consent_id"]}).get("ok"))
            self.assertTrue(stop_tool.execute({}).get("ok"))
        finally:
            reset_tool_turn_context(token)
            runtime.close()

    def test_model_point_uses_both_image_sizes(self) -> None:
        calls = []
        config = VisionConfig(fps=30, focus_width=80, focus_height=60,
                              square_size=160, settle_ms=0)
        runtime = VisionRuntime(
            config,
            capture=lambda: Image.new("RGB", (320, 240), (40, 80, 120)),
            cursor=lambda: (10, 10),
        )
        try:
            request = runtime.request_open("cid-a", "call-a")
            grant = runtime.confirm("cid-a", request["request_id"], "agree")
            runtime.start("cid-a", grant["consent_id"])
            with patch("plugins.visual_operator_2.state.backend.set_cursor",
                       side_effect=lambda x, y: calls.append((x, y))), \
                 patch("plugins.visual_operator_2.state.backend.click"):
                move = runtime.move_point("cid-a", 80, 80, 160, 120, 320, 240)
                self.assertTrue(move["ok"])
                self.assertEqual(move["coordinate_space"], "model_image")
                self.assertEqual(move["model_point"], {"x": 80, "y": 80})
                self.assertNotIn("target_screen", move)
                self.assertNotIn("cursor_after", move)
                click = runtime.click("cid-a")
                self.assertTrue(click["ok"])
                self.assertTrue(click["observation_frame_id"])
            self.assertEqual(calls, [(80, 80)])
        finally:
            runtime.close()

    def test_user_takeover_closes_eyes_and_blocks_actions(self) -> None:
        runtime = self._runtime()
        try:
            request = runtime.request_open("cid-a", "call-a")
            grant = runtime.confirm("cid-a", request["request_id"], "agree")
            self.assertTrue(runtime.start("cid-a", grant["consent_id"])["ok"])
            runtime.user_takeover()
            status = runtime.status("cid-a")
            self.assertFalse(status["eyes_open"])
            self.assertTrue(status["user_takeover"])
            self.assertFalse(runtime.move_point("cid-a", 0, 0, 1, 1, 1, 1)["ok"])
            self.assertFalse(runtime.click("cid-a")["ok"])
            self.assertTrue(runtime.request_open("cid-a", "call-b")["ok"])
        finally:
            runtime.close()

    def test_model_point_matches_user_example(self) -> None:
        calls = []
        runtime = VisionRuntime(
            VisionConfig(fps=30, focus_width=80, focus_height=60,
                         square_size=100, settle_ms=0),
            capture=lambda: Image.new("RGB", (200, 100), (40, 80, 120)),
            cursor=lambda: (10, 10),
        )
        try:
            request = runtime.request_open("cid-a", "call-a")
            grant = runtime.confirm("cid-a", request["request_id"], "agree")
            runtime.start("cid-a", grant["consent_id"])
            with patch("plugins.visual_operator_2.state.backend.set_cursor",
                       side_effect=lambda x, y: calls.append((x, y))):
                result = runtime.move_point(
                    "cid-a", 50, 25, 100, 50, 200, 100)
            self.assertTrue(result["ok"])
            self.assertNotIn("target_screen", result)
            self.assertEqual(calls, [(50, 25)])
        finally:
            runtime.close()

    def test_native_full_image_is_screen_identity(self) -> None:
        calls = []
        config = VisionConfig(fps=30, focus_width=80, focus_height=60,
                              square_size=0, settle_ms=0)
        runtime = VisionRuntime(
            config,
            capture=lambda: Image.new("RGB", (1920, 1080), (40, 80, 120)),
            cursor=lambda: (10, 10),
        )
        try:
            request = runtime.request_open("cid-a", "call-a")
            grant = runtime.confirm("cid-a", request["request_id"], "agree")
            runtime.start("cid-a", grant["consent_id"])
            observation = runtime.observe("cid-a")
            assert observation is not None
            self.assertEqual(observation["full_size"], [1600, 900])
            self.assertGreater(observation["full_scale"], 0)
            with patch("plugins.visual_operator_2.state.backend.set_cursor",
                       side_effect=lambda x, y: calls.append((x, y))):
                result = runtime.move_point("cid-a", 800, 450, 800, 450, 1920, 1080)
            self.assertTrue(result["ok"])
            self.assertEqual(result["model_point"], {"x": 800, "y": 450})
            self.assertNotIn("target_screen", result)
            self.assertEqual(calls, [(960, 540)])
        finally:
            runtime.close()

    def test_model_stretched_image_uses_independent_axes(self) -> None:
        runtime = VisionRuntime(
            VisionConfig(fps=30, square_size=0, settle_ms=0),
            capture=lambda: Image.new("RGB", (1920, 1080), (40, 80, 120)),
            cursor=lambda: (10, 10),
        )
        try:
            request = runtime.request_open("cid-a", "call-a")
            grant = runtime.confirm("cid-a", request["request_id"], "agree")
            runtime.start("cid-a", grant["consent_id"])
            with patch("plugins.visual_operator_2.state.backend.move_cursor",
                       return_value=True):
                result = runtime.move_point(
                    "cid-a", 200, 100, 800, 450, 1920, 1080)
            self.assertTrue(result["ok"])
            self.assertNotIn("target_screen", result)
            self.assertNotIn("scale", result)
        finally:
            runtime.close()

    def test_single_click_count_and_interval(self) -> None:
        clicks = []
        runtime = self._runtime()
        try:
            request = runtime.request_open("cid-a", "call-a")
            grant = runtime.confirm("cid-a", request["request_id"], "agree")
            runtime.start("cid-a", grant["consent_id"])
            with patch("plugins.visual_operator_2.state.backend.click",
                       side_effect=lambda button, count: clicks.append((button, count))):
                result = runtime.click("cid-a", count=2, interval_ms=72)
            self.assertTrue(result["ok"])
            self.assertEqual(result["clicks"], 2)
            self.assertEqual(result["interval_ms"], 72)
            self.assertEqual(clicks, [("left", 1), ("left", 1)])
            bad = runtime.click("cid-a", count=1, interval_ms=71)
            self.assertFalse(bad["ok"])
        finally:
            runtime.close()

    def test_click_sequence_uses_same_point_conversion(self) -> None:
        calls = []
        runtime = self._runtime()
        try:
            request = runtime.request_open("cid-a", "call-a")
            grant = runtime.confirm("cid-a", request["request_id"], "agree")
            runtime.start("cid-a", grant["consent_id"])
            with patch("plugins.visual_operator_2.state.backend.set_cursor",
                       side_effect=lambda x, y: calls.append((x, y))), \
                 patch("plugins.visual_operator_2.state.backend.click"):
                result = runtime.click_sequence(
                    "cid-a",
                    [{"x": 40, "y": 40}, {"x": 120, "y": 100}],
                    160, 120, 320, 240, interval_ms=72, count=1)
            self.assertTrue(result["ok"])
            self.assertNotIn("target_screen", result["clicks"][0])
            self.assertNotIn("target_screen", result["clicks"][1])
            self.assertEqual(calls, [(40, 40), (120, 100)])
            self.assertTrue(result["observation_frame_id"])
            bad = runtime.click_sequence(
                "cid-a", [{"x": 40, "y": 40}], 160, 120, 320, 240,
                interval_ms=71, count=1)
            self.assertFalse(bad["ok"])
            self.assertIn("72", bad["error"])
        finally:
            runtime.close()

    def test_zero_move_is_not_reported_as_moved(self) -> None:
        runtime = self._runtime()
        try:
            request = runtime.request_open("cid-a", "call-a")
            grant = runtime.confirm("cid-a", request["request_id"], "agree")
            runtime.start("cid-a", grant["consent_id"])
            with patch("plugins.visual_operator_2.state.backend.move_cursor") as move:
                relative = runtime.move("cid-a", 0, 0)
                point = runtime.move_point(
                    "cid-a", 160, 120, 160, 120, 320, 240)
            self.assertTrue(relative["ok"])
            self.assertFalse(relative["moved"])
            self.assertTrue(relative["no_op"])
            self.assertFalse(point["moved"])
            self.assertTrue(point["no_op"])
            move.assert_not_called()
        finally:
            runtime.close()

    def test_trajectory_duration_and_same_point_skip(self) -> None:
        runtime = VisionRuntime(
            VisionConfig(fps=30, focus_width=80, focus_height=60,
                         move_duration_ms=200, settle_ms=0, move_settle_ms=0),
            capture=lambda: Image.new("RGB", (320, 240), (40, 80, 120)),
            cursor=lambda: (160, 120),
        )
        try:
            request = runtime.request_open("cid-a", "call-a")
            grant = runtime.confirm("cid-a", request["request_id"], "agree")
            runtime.start("cid-a", grant["consent_id"])
            with patch("plugins.visual_operator_2.state.backend.move_cursor",
                       return_value=True) as move, \
                 patch("plugins.visual_operator_2.state.backend.click"):
                self.assertTrue(runtime.move_point(
                    "cid-a", 512, 640, 160, 120, 320, 240)["ok"])
                self.assertEqual(move.call_args[0][2], 200)
                result = runtime.click_sequence(
                    "cid-a", [{"x": 40, "y": 40}, {"x": 40, "y": 40}],
                    160, 120, 320, 240, interval_ms=72, count=1)
            self.assertTrue(result["ok"])
            self.assertEqual(move.call_count, 2)
            self.assertFalse(result["clicks"][1]["moved"])
        finally:
            runtime.close()

    def test_focus_region_maps_compressed_image_center(self) -> None:
        runtime = VisionRuntime(
            VisionConfig(fps=30, settle_ms=0, image_max_side=1600),
            capture=lambda: Image.new("RGB", (1920, 1080), (40, 80, 120)),
            cursor=lambda: (960, 540),
        )
        try:
            request = runtime.request_open("cid-a", "call-a")
            grant = runtime.confirm("cid-a", request["request_id"], "agree")
            runtime.start("cid-a", grant["consent_id"])
            result = runtime.focus(
                "cid-a", 400, 300, 400, 300, 800, 450, 1920, 1080)
            self.assertTrue(result["ok"])
            self.assertEqual(result["focus_size"], [480, 360])
        finally:
            runtime.close()

    def test_focus_region_and_move_focus(self) -> None:
        runtime = VisionRuntime(
            VisionConfig(fps=30, settle_ms=0, square_size=0),
            capture=lambda: Image.new("RGB", (320, 240), (40, 80, 120)),
            cursor=lambda: (160, 120),
        )
        try:
            request = runtime.request_open("cid-a", "call-a")
            grant = runtime.confirm("cid-a", request["request_id"], "agree")
            runtime.start("cid-a", grant["consent_id"])
            result = runtime.focus(
                "cid-a", 100, 80, 100, 80, 160, 120, 320, 240)
            self.assertTrue(result["ok"])
            self.assertEqual(result["focus_size"], [100, 80])
            observation = runtime.observe("cid-a")
            assert observation is not None
            self.assertTrue(observation["cursor_in_focus"])
            self.assertEqual(observation["focus"]["image_size"], [100, 80])
            self.assertGreaterEqual(len(observation["images"]), 2)
            self.assertTrue(any("FOCUS" in str(item.get("label") or "")
                                for item in observation["images"]))
            with patch("plugins.visual_operator_2.state.backend.move_cursor",
                       return_value=True) as move:
                moved = runtime.move_focus("cid-a", 50, 40, 100, 80)
            self.assertTrue(moved["ok"])
            self.assertNotIn("target_screen", moved)
            move.assert_called_once()
        finally:
            runtime.close()

    def test_focus_accepts_10px_region(self) -> None:
        runtime = self._runtime()
        try:
            request = runtime.request_open("cid-a", "call-a")
            grant = runtime.confirm("cid-a", request["request_id"], "agree")
            runtime.start("cid-a", grant["consent_id"])
            result = runtime.focus(
                "cid-a", 100, 80, 10, 10, 160, 120, 320, 240)
            self.assertTrue(result["ok"])
            self.assertEqual(result["focus_size"], [10, 10])
        finally:
            runtime.close()

    def test_move_focus_tool_executes_without_check_points(self) -> None:
        from plugins.visual_operator_2.tools import VisionMoveFocusTool

        runtime = self._runtime()
        try:
            request = runtime.request_open("cid-a", "call-a")
            grant = runtime.confirm("cid-a", request["request_id"], "agree")
            runtime.start("cid-a", grant["consent_id"])
            self.assertTrue(runtime.focus(
                "cid-a", 100, 80, 100, 80, 160, 120, 320, 240)["ok"])
            token = set_tool_turn_context(ToolTurnContext(
                session=SimpleNamespace(conversation_id="cid-a"),
                call=SimpleNamespace(call_id="call-a"),
            ))
            try:
                with patch("plugins.visual_operator_2.state.backend.move_cursor",
                           return_value=True):
                    result = VisionMoveFocusTool(runtime).execute(
                        {"x": 50, "y": 40, "width": 100, "height": 80})
            finally:
                reset_tool_turn_context(token)
            self.assertTrue(result["ok"])
        finally:
            runtime.close()

    def test_click_tools_and_sequence_contract(self) -> None:
        from plugins.visual_operator_2.tools import VisionClickTool, build_tools

        self.assertEqual(VisionClickTool.parameters["interval_ms"]["default"], 72)
        self.assertEqual(VisionClickTool.parameters["interval_ms"]["minimum"], 72)
        tools = build_tools(self._runtime())
        names = [tool.name for tool in tools]
        for tool in tools:
            self.assertIn("visual-operator-2", tool.description)
            self.assertIn("windows-desktop-operations", tool.description)
        self.assertIn("vision_click", names)
        self.assertIn("vision_click_sequence", names)
        self.assertIn("vision_move_point", names)
        self.assertIn("vision_focus", names)
        self.assertIn("vision_move_focus", names)
        self.assertNotIn("vision_move_to", names)
        self.assertNotIn("vision_move_box", names)
        self.assertNotIn("vision_click_at", names)
        self.assertNotIn("vision_click_offset", names)

    def test_calibration_can_be_disabled(self) -> None:
        runtime = VisionRuntime(
            VisionConfig(fps=30, settle_ms=0, calibration_enabled=False),
            capture=lambda: Image.new("RGB", (320, 240), (40, 80, 120)),
            cursor=lambda: (160, 120),
        )
        try:
            request = runtime.request_open("cid-a", "call-a")
            grant = runtime.confirm("cid-a", request["request_id"], "agree")
            runtime.start("cid-a", grant["consent_id"])
            observation = runtime.observe("cid-a")
            assert observation is not None
            self.assertEqual(observation["calibration"], [])
            self.assertNotIn("calibration=", observation["text"])
            with patch("plugins.visual_operator_2.state.backend.move_cursor",
                       return_value=True):
                result = runtime.move_point(
                    "cid-a", 10, 10, 160, 120, 320, 240)
            self.assertTrue(result["ok"])
        finally:
            runtime.close()

    def test_random_calibration_points(self) -> None:
        runtime = self._runtime()
        try:
            request = runtime.request_open("cid-a", "call-a")
            grant = runtime.confirm("cid-a", request["request_id"], "agree")
            runtime.start("cid-a", grant["consent_id"])
            observation = runtime.observe("cid-a")
            assert observation is not None
            challenge = runtime._challenges[observation["frame_id"]]
            self.assertEqual(len(observation["calibration"]), 1)
            self.assertEqual(
                [(item["x"], item["y"]) for item in observation["calibration"]],
                challenge["screen"])
            points = [{"x": x, "y": y} for x, y in challenge["model"]]
            with patch("plugins.visual_operator_2.state.backend.move_cursor",
                       return_value=True):
                good = runtime.move_point(
                    "cid-a", 10, 10, 160, 120, 320, 240, points)
            self.assertTrue(good["ok"])
            self.assertNotIn(observation["frame_id"], runtime._challenges)
            observation = runtime.observe("cid-a")
            assert observation is not None
            challenge = runtime._challenges[observation["frame_id"]]
            bad = runtime.move_point(
                "cid-a", 10, 10, 160, 120, 320, 240,
                [{"x": 20, "y": 20}])
            self.assertFalse(bad["ok"])
            self.assertIn("校准", bad["error"])
            self.assertIn("读图", bad["error"])
            report = runtime._last_calibration
            self.assertFalse(report["accepted"])
            self.assertEqual(report["points"][0]["real"],
                             {"x": challenge["screen"][0][0],
                              "y": challenge["screen"][0][1]})
            self.assertIn("screen", report["points"][0])
            self.assertIn("delta", report["points"][0])
        finally:
            runtime.close()

    def test_check_error_comes_after_eye_state(self) -> None:
        runtime = self._runtime()
        try:
            closed = runtime.move_point(
                "cid-a", 10, 10, 100, 100, 200, 100, [])
            self.assertIn("眼睛", closed["error"])
            request = runtime.request_open("cid-a", "call-a")
            grant = runtime.confirm("cid-a", request["request_id"], "agree")
            runtime.start("cid-a", grant["consent_id"])
            missing = runtime.move_point(
                "cid-a", 10, 10, 100, 100, 200, 100, [])
            self.assertIn("校准", missing["error"])
        finally:
            runtime.close()

    def test_five_calibration_failures_close_eyes(self) -> None:
        runtime = self._runtime()
        try:
            request = runtime.request_open("cid-a", "call-a")
            grant = runtime.confirm("cid-a", request["request_id"], "agree")
            runtime.start("cid-a", grant["consent_id"])
            runtime.observe("cid-a")
            bad = [{"x": 1, "y": 1}]
            for _ in range(5):
                result = runtime.move_point(
                    "cid-a", 10, 10, 160, 120, 320, 240, bad)
                self.assertFalse(result["ok"])
            self.assertFalse(runtime.status("cid-a")["eyes_open"])
            self.assertIn("视觉已关闭", result["error"])
            self.assertIn("读图", result["error"])
        finally:
            runtime.close()

    def test_coordinate_tools_require_check_points(self) -> None:
        from plugins.visual_operator_2.tools import (
            VisionClickSequenceTool,
            VisionMovePointTool,
        )

        for tool in (VisionMovePointTool, VisionClickSequenceTool):
            self.assertEqual(tool.parameters["check_points"]["minItems"], 1)
            self.assertEqual(tool.parameters["check_points"]["maxItems"], 1)

    def test_step_log_writes_jsonl_and_reports_failure(self) -> None:
        from plugins.visual_operator_2 import step_log

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "steps.log"
            try:
                step_log.configure(path)
                step_log.write("probe", value=1)
                records = [json.loads(line) for line in path.read_text(
                    encoding="utf-8").splitlines()]
                self.assertEqual(records[0]["event"], "probe")
                self.assertEqual(records[0]["value"], "1")
                step_log.configure(Path(tmp))
                with patch("plugins.visual_operator_2.step_log.report_error") as report:
                    step_log.write("probe", value=2)
                report.assert_called_once()
            finally:
                step_log.configure(None)

    def test_calibration_report_rejects_wrong_point_count(self) -> None:
        from plugins.visual_operator_2.calibration import ChallengeStore

        store = ChallengeStore()
        store._items["f"] = {"screen": [(10, 10)], "model": [(10, 10)]}
        self.assertEqual(store.report(
            [{"x": 1, "y": 2}, {"x": 3, "y": 4}], "f", 800, 450, 1600, 900), {})
        self.assertEqual(store.report(
            [{"x": 1, "y": 2}], "f", 800, 450, 1600, 900)["points"][0]["real"],
            {"x": 10, "y": 10})

    def test_built_tools_keep_tool_plugin_type(self) -> None:
        from agent.capabilities.registry import ToolPlugin
        from plugins.visual_operator_2.tools import build_tools

        tools = build_tools(self._runtime())
        self.assertTrue(all(isinstance(tool, ToolPlugin) for tool in tools))

    def test_step_log_path_uses_error_log_root(self) -> None:
        context = SimpleNamespace(
            has=lambda name: name == "error_log",
            get=lambda name: SimpleNamespace(path=Path("D:/data/logs/errors.log")))
        app = SimpleNamespace(context=context)
        self.assertEqual(_step_log_path(app),
                         Path("D:/data/logs/visual_operator_2.steps.log"))
        self.assertIsNone(_step_log_path(None))

    @unittest.skipUnless(sys.platform == "win32", "Windows input backend")
    def test_key_shortcut_uses_sendinput_batch(self) -> None:
        from plugins.visual_operator_2 import backend

        with patch.object(backend._u, "SendInput", return_value=4) as send:
            backend.press_keys(["win", "s"])
        events = send.call_args.args[1]
        self.assertEqual(send.call_count, 1)
        self.assertEqual([(events[i].type, events[i].union.ki.wVk,
                           events[i].union.ki.dwFlags) for i in range(4)],
                         [(1, 0x5B, 1), (1, 0x53, 0),
                          (1, 0x53, 2), (1, 0x5B, 3)])

    def test_desktop_tools_are_registered_and_authorized(self) -> None:
        from agent.capabilities.registry import ToolPlugin
        from plugins.visual_operator_2.tools import build_tools

        runtime = self._runtime()
        try:
            tools = build_tools(runtime)
            names = {tool.name for tool in tools}
            for name in ("vision_app", "vision_window", "vision_eye",
                         "vision_type_into", "vision_keyboard", "vision_wait",
                         "vision_find", "vision_click_text", "vision_mouse",
                         "vision_open"):
                self.assertIn(name, names)
            self.assertTrue(all(isinstance(tool, ToolPlugin) for tool in tools))
            eye = next(tool for tool in tools if tool.name == "vision_eye")
            self.assertIn("不替代持续视觉帧", eye.description)
        finally:
            runtime.close()

    def test_desktop_tool_requires_authorization_and_blocks_core_overlap(self) -> None:
        from agent.capabilities.registry import ToolPlugin
        from plugins.visual_operator_2.desktop import _AuthorizedDesktopTool

        class _Inner(ToolPlugin):
            name = "inner"
            description = "inner"
            parameters = {"action": {"type": "string"}}
            parallel_safe = False

            def execute(self, arguments):
                return {"ok": True, "arguments": arguments}

        status = {"eyes_open": False}
        runtime = SimpleNamespace(status=lambda cid: status)
        tool = _AuthorizedDesktopTool(
            _Inner(), runtime, "vision_mouse", "滚动拖拽", "test")
        token = set_tool_turn_context(ToolTurnContext(
            session=SimpleNamespace(conversation_id="cid-a"),
            call=SimpleNamespace(call_id="call-a"),
        ))
        try:
            self.assertFalse(tool.execute({"action": "scroll"})["ok"])
            status["eyes_open"] = True
            self.assertFalse(tool.execute({"action": "click"})["ok"])
            self.assertTrue(tool.execute({"action": "scroll"})["ok"])
        finally:
            reset_tool_turn_context(token)

    @unittest.skipUnless(sys.platform == "win32", "Windows input backend")
    def test_key_fallback_reports_alt_tab_success_and_win_failure(self) -> None:
        from plugins.visual_operator_2 import backend

        with patch.object(backend._u, "SendInput", return_value=0), \
                patch.object(backend, "_key"):
            self.assertTrue(backend.press_keys(["alt", "tab"])["ok"])
            self.assertFalse(backend.press_keys(["win", "s"])["ok"])

    def test_visual_skill_is_registered(self) -> None:
        from pathlib import Path

        from plugins.skills.library import SkillManager

        root = Path(__file__).resolve().parent.parent
        skills = SkillManager(None, builtin_dir=root / "skills")
        self.assertIn("visual-operator-2", skills.list_skill_names())
        self.assertIn("windows-desktop-operations", skills.list_skill_names())
        text = skills.get_skill("visual-operator-2") or ""
        self.assertIn("vision_click", text)
        self.assertIn("vision_move_point", text)
        self.assertIn("vision_focus", text)
        self.assertIn("vision_move_focus", text)
        self.assertIn("coordinate_space=model_image", text)
        self.assertIn("用户接管", text)

    def test_human_mouse_takeover_after_100px(self) -> None:
        from plugins.visual_operator_2 import backend

        monitor = backend.HumanInputMonitor(100)
        done = threading.Event()
        monitor.bind(done.set)
        monitor.record_human_move(0, 0)
        monitor.record_human_move(60, 0)
        self.assertFalse(done.is_set())
        monitor.record_human_move(120, 0)
        self.assertTrue(done.wait(1.0))

    def test_input_monitor_fires_once_in_worker(self) -> None:
        from plugins.visual_operator_2 import backend

        monitor = backend.HumanInputMonitor()
        called = []
        done = threading.Event()
        gate = threading.Event()

        def callback() -> None:
            called.append(True)
            gate.wait(1.0)
            done.set()

        monitor.bind(callback)
        monitor._fire()
        monitor._fire()
        gate.set()
        self.assertTrue(done.wait(1.0))
        time.sleep(0.05)
        self.assertEqual(len(called), 1)

    def test_actions_use_fake_backend_and_wake_on_change(self) -> None:
        woke = []
        config = VisionConfig(fps=30, focus_width=80, focus_height=60,
                              settle_ms=0)
        runtime = VisionRuntime(
            config,
            capture=lambda: Image.new("RGB", (320, 240), (40, 80, 120)),
            cursor=lambda: (160, 120),
            wake=woke.append,
        )
        try:
            request = runtime.request_open("cid-a", "call-a")
            grant = runtime.confirm("cid-a", request["request_id"], "agree")
            runtime.start("cid-a", grant["consent_id"])
            time.sleep(0.15)
            with patch.object(runtime, "_cursor", return_value=(160, 120)), \
                 patch("plugins.visual_operator_2.state.backend.set_cursor") as setcur, \
                 patch("plugins.visual_operator_2.state.backend.move_cursor", return_value=True) as move, \
                 patch("plugins.visual_operator_2.state.backend.click") as click, \
                 patch("plugins.visual_operator_2.state.backend.press_keys") as keys:
                self.assertTrue(runtime.focus(
                    "cid-a", 20, 20, 100, 80, 160, 120, 320, 240)["ok"])
                self.assertTrue(runtime.move("cid-a", 10, 5)["ok"])
                move.assert_called_once()
                self.assertTrue(runtime.click("cid-a")["ok"])
                click.assert_called_once()
                self.assertTrue(runtime.key("cid-a", ["ctrl", "c"])["ok"])
                keys.assert_called_once()
            runtime._remember_frame(
                Image.new("RGB", (320, 240), (200, 20, 20)),
                (160, 120), runtime._generation)
            time.sleep(0.1)
            self.assertTrue(woke)
        finally:
            runtime.close()


class _FakeContext:
    """register 用到的最小上下文；只记录贡献，不做真装配。"""

    app = None

    def __init__(self) -> None:
        self.tools = []
        self.sections = []
        self.routes = []
        self.hooks = []
        self.items = []
        self.runtime = None

    def publish_event(self, event, payload):
        return 1

    def register_tool(self, tool):
        self.tools.append(tool)
        return lambda: None

    def add_context_assembly_hook(self, hook, **_kwargs):
        self.hooks.append(hook)
        return lambda: None

    def add_prompt_section(self, name, section, **_kwargs):
        self.sections.append((name, section))
        return lambda: None

    def add_route(self, method, path, handler, **_kwargs):
        self.routes.append((method, path, handler))
        return lambda: None

    def add_ui_item(self, path, **kwargs):
        self.items.append((path, kwargs))
        return lambda: None

    def set_runtime(self, runtime):
        self.runtime = runtime

    def resume_suspended(self, cid, call_id, data, **kwargs):
        return {"ok": True}


def _slot_runtime():
    """不经 register 构造一份插口运行时，用于单工厂调用。"""
    from plugins.visual_operator_2.desktop import make_desktop_parts
    from plugins.visual_operator_2.plugin import SlotRuntime

    config = VisionConfig(fps=30, focus_width=80, focus_height=60)
    vision = VisionRuntime(
        config,
        capture=lambda: Image.new("RGB", (320, 240), (40, 80, 120)),
        cursor=lambda: (160, 120),
    )
    return SlotRuntime(vision=vision, desktop=make_desktop_parts())


class SlotFactoryTest(unittest.TestCase):
    """插口工厂：20 个工具各一实例、共享件唯一、与片段声明一致。"""

    #: 恒注册的 20 个工具名，顺序即装配顺序。
    EXPECTED = [
        "vision_request_open", "vision_start", "vision_focus", "vision_move",
        "vision_move_point", "vision_move_focus", "vision_click",
        "vision_click_sequence", "vision_key", "vision_stop",
        "vision_app", "vision_window", "vision_eye", "vision_type_into",
        "vision_keyboard", "vision_wait", "vision_find", "vision_click_text",
        "vision_mouse", "vision_open",
    ]

    def test_factories_construct_every_tool_once(self) -> None:
        """20 个工厂各造一个工具，名字集合与片段声明一致。"""
        runtime = _slot_runtime()
        try:
            names = [factory(None, runtime).name for factory in _PLUGIN.TOOL_FACTORIES]
            self.assertEqual(sorted(names), sorted(self.EXPECTED))
        finally:
            runtime.vision.close()

    def test_declared_tools_match_module_factories(self) -> None:
        """片段里的 20 个 tool 节点 ↔ 模块 `make_tool_*` 后缀集合相等。"""
        data = json.loads(
            Path(_PLUGIN.__file__).with_name("plugin-slots.json")
            .read_text(encoding="utf-8"))
        declared = {row["path"].rsplit("/", 1)[-1]
                    for row in data["slots"] if row["kind"] == "tool"}
        self.assertEqual(sorted(declared), sorted(self.EXPECTED))
        exported = {name[len("make_tool_"):] for name in dir(_PLUGIN)
                    if name.startswith("make_tool_")}
        self.assertEqual(declared, exported)

    def test_all_tools_share_one_vision_runtime(self) -> None:
        """视觉运行时带锁与线程，必须全局唯一。"""
        runtime = _slot_runtime()
        try:
            holders = set()
            for factory in _PLUGIN.TOOL_FACTORIES:
                tool = factory(None, runtime)
                inner = getattr(tool, "_tool", None)
                vision = getattr(inner, "_runtime", None)
                if vision is not None:
                    holders.add(id(vision))
            self.assertEqual(len(holders), 1)
        finally:
            runtime.vision.close()

    def test_desktop_tools_share_one_capture_store(self) -> None:
        """截图与鼠标靠同一张映射对齐，桌面工具不能各建一份。"""
        runtime = _slot_runtime()
        try:
            holders = {}
            for factory in _PLUGIN.TOOL_FACTORIES:
                tool = factory(None, runtime)
                inner = getattr(tool, "_tool", None)
                captures = getattr(inner, "_captures", None)
                if captures is not None:
                    holders[tool.name] = id(captures)
            self.assertEqual(len(holders), 4)
            self.assertEqual(sorted(holders),
                             ["vision_eye", "vision_keyboard", "vision_mouse",
                              "vision_type_into"])
            self.assertEqual(len(set(holders.values())), 1)
        finally:
            runtime.vision.close()

    def _runtime(self) -> VisionRuntime:
        config = VisionConfig(fps=30, focus_width=80, focus_height=60)
        return VisionRuntime(
            config,
            capture=lambda: Image.new("RGB", (320, 240), (40, 80, 120)),
            cursor=lambda: (160, 120),
        )


if __name__ == "__main__":
    unittest.main()
