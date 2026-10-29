# -*- coding: utf-8 -*-
"""视觉操作 2.0 全局授权与上下文钩子。"""
from __future__ import annotations

import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from agent.core.context import ToolTurnContext
from agent.core.session_scope import reset_tool_turn_context, set_tool_turn_context
from plugins.visual_operator_2.config import VisionConfig
from plugins.visual_operator_2.plugin import _observation_hook
from plugins.visual_operator_2.routes import build_routes
from plugins.visual_operator_2.state import VisionRuntime
from plugins.visual_operator_2.tools import VisionRequestOpenTool, VisionStartTool, VisionStopTool


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
            self.assertEqual(observation["images"][0], "FULL FRAME")
            self.assertEqual(observation["images"][1].split(",")[0], "data:image/webp;base64")
            self.assertEqual(len(observation["images"]), 2)
            self.assertEqual(observation["focus_image"], "")
            self.assertIsNone(runtime.observe("cid-b"))
            self.assertFalse(runtime.start("cid-a", grant["consent_id"])["ok"])
            self.assertTrue(runtime.stop("cid-a")["ok"])
            self.assertIsNone(runtime.observe("cid-a"))
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

    def test_context_hook_appends_full_image_only(self) -> None:
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
            self.assertEqual(sum(1 for p in parts if p["type"] == "image_url"), 1)
            self.assertEqual(parts[0]["type"], "text")
            self.assertEqual(parts[1]["type"], "text")
            self.assertEqual(parts[2]["type"], "image_url")
            self.assertEqual(len(parts), 3)
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
            self.assertEqual(payload["full_size"], [1024, 1024])
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
            def add_route(self, method, path, handler):
                routes[(method, path)] = handler
                return lambda: None

            def resume_suspended(self, cid, call_id, data, **kwargs):
                resumed.append((cid, call_id, data, kwargs))
                return {"ok": True}

        try:
            build_routes(Ctx(), runtime)
            request = runtime.request_open("cid-a", "call-a")
            handler = routes[("POST", "eye-consent/confirm")]
            status, payload = handler({"body": {
                "conversation_id": "cid-a",
                "request_id": request["request_id"],
                "choice": "agree",
            }})
            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(resumed[0][0], "cid-a")
            self.assertEqual(resumed[0][1], "call-a")
            self.assertEqual(resumed[0][2]["consent_id"], payload["consent_id"])
        finally:
            runtime.close()

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
                move = runtime.move_point("cid-a", 80, 80, 160, 160, 320, 240)
                self.assertTrue(move["ok"])
                self.assertEqual(move["coordinate_space"], "model_image")
                self.assertEqual(move["model_point"], {"x": 80, "y": 80})
                self.assertEqual(move["target_screen"], {"x": 160, "y": 120})
                self.assertEqual(move["target_screen"], {"x": 160, "y": 120})
                click = runtime.click("cid-a")
                self.assertTrue(click["ok"])
                self.assertTrue(click["observation_frame_id"])
            self.assertEqual(calls, [(160, 120)])
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
                    "cid-a", 50, 50, 100, 100, 200, 100)
            self.assertTrue(result["ok"])
            self.assertEqual(result["target_screen"], {"x": 100, "y": 50})
            self.assertEqual(calls, [(100, 50)])
        finally:
            runtime.close()

    def test_native_full_image_is_screen_identity(self) -> None:
        calls = []
        config = VisionConfig(fps=30, focus_width=80, focus_height=60,
                              square_size=1024, settle_ms=0)
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
            self.assertEqual(observation["full_size"], [1024, 1024])
            self.assertGreater(observation["full_scale"], 0)
            with patch("plugins.visual_operator_2.state.backend.set_cursor",
                       side_effect=lambda x, y: calls.append((x, y))):
                result = runtime.move_point("cid-a", 512, 512, 1024, 1024, 1920, 1080)
            self.assertTrue(result["ok"])
            self.assertEqual(result["model_point"], {"x": 512, "y": 512})
            self.assertEqual(result["target_screen"], {"x": 960, "y": 540})
            self.assertEqual(calls, [(960, 540)])
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
                    [{"x": 40, "y": 40}, {"x": 120, "y": 120}],
                    160, 160, 320, 240, interval_ms=72, count=1)
            self.assertTrue(result["ok"])
            self.assertEqual(result["clicks"][0]["target_screen"], {"x": 80, "y": 40})
            self.assertEqual(result["clicks"][1]["target_screen"], {"x": 240, "y": 200})
            self.assertEqual(calls, [(80, 40), (240, 200)])
            self.assertTrue(result["observation_frame_id"])
            bad = runtime.click_sequence(
                "cid-a", [{"x": 40, "y": 40}], 160, 160, 320, 240,
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
                    "cid-a", 512, 512, 1024, 1024, 320, 240)
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
                    "cid-a", 512, 640, 1024, 1024, 320, 240)["ok"])
                self.assertEqual(move.call_args[0][2], 200)
                result = runtime.click_sequence(
                    "cid-a", [{"x": 40, "y": 40}, {"x": 40, "y": 40}],
                    160, 160, 320, 240, interval_ms=72, count=1)
            self.assertTrue(result["ok"])
            self.assertEqual(move.call_count, 2)
            self.assertFalse(result["clicks"][1]["moved"])
        finally:
            runtime.close()

    def test_click_tools_and_sequence_contract(self) -> None:
        from plugins.visual_operator_2.tools import VisionClickTool, build_tools

        self.assertEqual(VisionClickTool.parameters["interval_ms"]["default"], 72)
        self.assertEqual(VisionClickTool.parameters["interval_ms"]["minimum"], 72)
        names = [tool.name for tool in build_tools(self._runtime())]
        self.assertIn("vision_click", names)
        self.assertIn("vision_click_sequence", names)
        self.assertIn("vision_move_point", names)
        self.assertNotIn("vision_move_focus", names)
        self.assertNotIn("vision_move_to", names)
        self.assertNotIn("vision_move_box", names)
        self.assertNotIn("vision_click_at", names)
        self.assertNotIn("vision_click_offset", names)

    def test_visual_skill_is_registered(self) -> None:
        from pathlib import Path

        from plugins.skills.library import SkillManager

        root = Path(__file__).resolve().parent.parent
        skills = SkillManager(None, builtin_dir=root / "skills")
        self.assertIn("visual-operator-2", skills.list_skill_names())
        text = skills.get_skill("visual-operator-2") or ""
        self.assertIn("vision_click", text)
        self.assertIn("vision_move_point", text)
        self.assertNotIn("vision_move_focus", text)
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
                self.assertTrue(runtime.focus("cid-a", {
                    "x": 20, "y": 20, "width": 100, "height": 80,
                }, True)["ok"])
                setcur.assert_called()
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


if __name__ == "__main__":
    unittest.main()
