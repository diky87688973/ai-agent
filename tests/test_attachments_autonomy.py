# -*- coding: utf-8 -*-
"""截图附件与自主模式。

三层各钉一遍，因为"传了但没进去 / 开了但没续跑"是这两类功能最常见的坏法：
  1. 服务端 `images` 校验（MIME / 上限 / 静默丢弃 / 有图无字）；
  2. 附件 → `input_claimed` 事实 → 多模态 content 的组装；
  3. 视觉能力判定与非视觉模型的降级剥离；
  4. 自主模式的 runtime 续跑谓词。
"""
from __future__ import annotations

import base64
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.core.events import make_event  # noqa: E402
from agent.core.ports import LogicalRequest  # noqa: E402
from agent.core.session_log import SessionLog, _user_content  # noqa: E402
from agent.mechanisms.live_state import LiveState  # noqa: E402
from agent.shell.web import MAX_IMAGES, _normalize_images  # noqa: E402

PNG_B64 = base64.b64encode(b"\x89PNG fake bytes").decode()

def _img(mime: str = "image/png", data: str = PNG_B64) -> dict:
    return {"mime": mime, "data_base64": data}

class NormalizeImagesTest(unittest.TestCase):
    """服务端 images 校验。"""

    def test_accepts_valid_image(self) -> None:

        out = _normalize_images([_img()])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["mime"], "image/png")
        self.assertEqual(out[0]["data_base64"], PNG_B64)

    def test_mime_is_lowercased(self) -> None:

        out = _normalize_images([_img("IMAGE/PNG")])
        self.assertEqual(out[0]["mime"], "image/png")

    def test_drops_non_image_mime(self) -> None:

        self.assertEqual(_normalize_images([_img("text/plain")]), [])
        self.assertEqual(_normalize_images([_img("application/pdf")]), [])

    def test_drops_empty_or_missing_data(self) -> None:

        self.assertEqual(_normalize_images([_img(data="   ")]), [])
        self.assertEqual(_normalize_images([{"mime": "image/png"}]), [])

    def test_drops_non_dict_and_non_list(self) -> None:

        self.assertEqual(_normalize_images(["nope"]), [])
        self.assertEqual(_normalize_images("nope"), [])
        self.assertEqual(_normalize_images(None), [])

    def test_caps_at_max_images(self) -> None:

        self.assertEqual(len(_normalize_images([_img()] * 9)), MAX_IMAGES)
        self.assertEqual(MAX_IMAGES, 4, msg="单条消息的截图上限应为 4")

    def test_keeps_valid_when_mixed_with_invalid(self) -> None:
        """非法项静默丢弃，不连累合法项（附件是增强项）。"""

        out = _normalize_images([_img("text/plain"), _img(), {"mime": "image/png"}])
        self.assertEqual(len(out), 1)

class UserContentTest(unittest.TestCase):
    """附件 → 多模态 content。"""

    def test_no_attachments_is_plain_string(self) -> None:

        self.assertEqual(_user_content("你好", None), "你好")
        self.assertEqual(_user_content("你好", []), "你好")

    def test_text_and_image_parts(self) -> None:

        parts = _user_content("这是什么", [_img()])
        self.assertIsInstance(parts, list)
        self.assertEqual(parts[0], {"type": "text", "text": "这是什么"})
        self.assertEqual(parts[1]["type"], "image_url")
        self.assertTrue(parts[1]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_image_only_has_no_empty_text_part(self) -> None:
        """纯截图提问：不得插入空文本段。"""

        parts = _user_content("", [_img()])
        self.assertTrue(all(p["type"] == "image_url" for p in parts))

    def test_invalid_attachment_ignored(self) -> None:

        self.assertEqual(_user_content("hi", [{"mime": "", "data_base64": "x"}]), "hi")

    def test_derive_messages_builds_multimodal_user_message(self) -> None:

        log = SessionLog(events=[
            make_event("input_claimed", content="看图", attachments=[_img()],
                       conversation_id="c1"),
        ])
        messages = log.derive_messages()
        user = [m for m in messages if m["role"] == "user"][-1]
        self.assertIsInstance(user["content"], list)
        self.assertEqual(user["content"][0]["text"], "看图")

    def test_derive_messages_without_attachments_stays_string(self) -> None:

        log = SessionLog(events=[
            make_event("input_claimed", content="纯文本", conversation_id="c1"),
        ])
        user = [m for m in log.derive_messages() if m["role"] == "user"][-1]
        self.assertEqual(user["content"], "纯文本")

class VisionDegradeTest(unittest.TestCase):
    """视觉能力判定与非视觉模型降级。"""

    def setUp(self) -> None:
        import agent.mechanisms.model_provider as mp

        self.mp = mp
        self.sent: list = []
        self._orig = mp.urllib.request.urlopen

        def fake_urlopen(req, timeout=None):
            self.sent.append(json.loads(req.data.decode("utf-8")))
            resp = io.BytesIO(b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n')
            resp.__enter__ = lambda: resp          # type: ignore[attr-defined]
            resp.__exit__ = lambda *a: False       # type: ignore[attr-defined]
            return resp

        mp.urllib.request.urlopen = fake_urlopen
        self.addCleanup(lambda: setattr(mp.urllib.request, "urlopen", self._orig))

    def _provider(self, model: str, **kw):
        return self.mp.OpenAICompatibleProvider(
            base_url="http://example.invalid/v1", api_key="k", model=model, **kw)

    def test_vision_by_model_name(self) -> None:

        self.assertTrue(self._provider("deepseek-v4-flash-vision-exp").supports_vision())
        self.assertFalse(self._provider("glm-5.2").supports_vision())

    def test_vision_model_keeps_image_parts(self) -> None:

        provider = self._provider("deepseek-v4-flash-vision-exp")
        request = LogicalRequest(
            messages=[{"role": "user", "content": _user_content("看图", [_img()])}], tools=[])
        list(provider.stream(request))
        content = self.sent[-1]["messages"][-1]["content"]
        self.assertIsInstance(content, list)
        self.assertEqual(content[1]["type"], "image_url")

    def test_non_vision_model_strips_images(self) -> None:
        """非视觉模型必须剥掉图片，否则整轮请求会被 API 拒。"""

        provider = self._provider("glm-5.2")
        request = LogicalRequest(
            messages=[{"role": "user", "content": _user_content("看图", [_img()])}], tools=[])
        list(provider.stream(request))
        content = self.sent[-1]["messages"][-1]["content"]
        self.assertIsInstance(content, str)
        # 图片被剥掉，但**必须留下说明**：静默丢图会让模型以为用户只发了文字，
        # 于是它会言之凿凿地描述一张自己没看到的图。
        self.assertIn("看图", content, msg="原文字必须保留")
        self.assertIn("图片", content, msg="必须说明图片已省略")
        self.assertNotIn("image_url", str(self.sent[-1]["messages"][-1]),
                         msg="图片本身必须已被移除，否则 API 会拒整轮请求")

    def test_non_vision_model_placeholder_when_image_only(self) -> None:

        provider = self._provider("glm-5.2")
        request = LogicalRequest(
            messages=[{"role": "user", "content": _user_content("", [_img()])}], tools=[])
        list(provider.stream(request))
        content = self.sent[-1]["messages"][-1]["content"]
        self.assertIsInstance(content, str)
        self.assertTrue(content.strip(), msg="不得发空 content")

class AutonomyTest(unittest.TestCase):
    """自主模式的存储与续跑判定。"""

    def test_live_state_roundtrip(self) -> None:

        state = LiveState()
        self.assertFalse(state.get_autonomy("c1")["enabled"])
        state.set_autonomy("c1", True)
        self.assertTrue(state.get_autonomy("c1")["enabled"])
        state.set_autonomy("c1", False)
        self.assertFalse(state.get_autonomy("c1")["enabled"])

    def test_per_conversation(self) -> None:

        state = LiveState()
        state.set_autonomy("c1", True)
        self.assertFalse(state.get_autonomy("c2")["enabled"], msg="不得串到别的会话")

    def test_runner_auto_continue_predicate_used(self) -> None:
        """`SessionRunner(auto_continue=...)` 被真正查询；谓词异常不得炸线程。"""

        from agent.shell.session_runner import SessionRunner

        calls: list = []
        runner = SessionRunner(app=None, mesh=None, auto_continue=lambda cid: calls.append(cid) or False)
        self.assertFalse(runner._should_auto_continue("c1"))
        self.assertEqual(calls, ["c1"])

        def boom(cid):
            raise RuntimeError("predicate 炸了")

        self.assertFalse(SessionRunner(app=None, mesh=None, auto_continue=boom)._should_auto_continue("c1"))

    def test_no_predicate_means_no_continue(self) -> None:

        from agent.shell.session_runner import SessionRunner

        self.assertFalse(SessionRunner(app=None, mesh=None)._should_auto_continue("c1"))

    def test_auto_continue_prompt_is_non_empty(self) -> None:

        from agent.shell.session_runner import AUTO_CONTINUE_PROMPT

        self.assertTrue(AUTO_CONTINUE_PROMPT.strip())

if __name__ == "__main__":
    unittest.main()
