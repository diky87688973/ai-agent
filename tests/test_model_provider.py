# -*- coding: utf-8 -*-
"""模型 provider 的请求级模型选择。

**为什么要能按请求选模型**：一个 provider 实例绑定一个 `base_url` / `api_key`，
但同一个网关下往往有多个模型名可选。
把模型放进**请求**，provider 便可复用，不必按模型各建一个实例 ——
会话选择因此只影响装配时注入的请求参数，不影响链上的模块。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.core.ports import LogicalRequest  # noqa: E402
from agent.mechanisms.model_provider import OpenAICompatibleProvider  # noqa: E402


class _Capturing(OpenAICompatibleProvider):
    """把 `_post_stream` 换掉：不发网络请求，只记下 payload。"""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.payloads: list[dict] = []

    def _post_stream(self, url, payload):        # type: ignore[override]
        self.payloads.append(payload)
        return iter(())

def _provider(model: str = "default-model") -> _Capturing:
    return _Capturing(base_url="https://example.invalid", api_key="k", model=model)

class RequestLevelModelTest(unittest.TestCase):

    def test_request_model_wins_over_instance_default(self) -> None:
        p = _provider("default-model")
        list(p.stream(LogicalRequest(messages=[], tools=[], model="chosen-model")))
        self.assertEqual(p.payloads[0]["model"], "chosen-model",
                         msg="请求里指定了模型就必须用它（会话级选择靠这条生效）")

    def test_empty_request_model_falls_back_to_instance_default(self) -> None:
        """空串 = 不指定 ⇒ 用实例默认模型，既有调用方行为不变。"""
        p = _provider("default-model")
        list(p.stream(LogicalRequest(messages=[], tools=[])))
        self.assertEqual(p.payloads[0]["model"], "default-model")

    def test_whitespace_is_treated_as_unspecified(self) -> None:
        p = _provider("default-model")
        list(p.stream(LogicalRequest(messages=[], tools=[], model="   ")))
        self.assertEqual(p.payloads[0]["model"], "default-model")

    def test_vision_is_judged_per_requested_model(self) -> None:
        """图片能力**逐个模型**不同，所以 `supports_vision` 按本次请求的模型判定。

        按实例默认模型判定会"该剥的图不剥"→ 整轮请求被 API 拒绝。
        """
        p = _provider("plain-model")
        self.assertFalse(p.supports_vision())
        self.assertTrue(p.supports_vision("deepseek-v4-flash-vision-exp"),
                        msg="本次选的是视觉模型，就该按视觉模型处理")

    def test_local_model_check_is_per_requested_model(self) -> None:
        """本地模型的判定同理：默认是云端、本次选本地时不能照旧下发推理档位。"""
        p = _provider("plain-model")
        self.assertFalse(p._is_local_model())
        self.assertTrue(p._is_local_model("local-model"))

    def test_effort_still_reaches_the_wire(self) -> None:
        """推理档位照常透传到请求载荷。"""
        p = _provider()
        list(p.stream(LogicalRequest(messages=[], tools=[], effort="max")))
        self.assertEqual(p.payloads[0].get("reasoning_effort"), "max")

if __name__ == "__main__":
    unittest.main()

class ImageStrippingIsNotSilentTest(unittest.TestCase):
    """非视觉模型收到图片时**必须留一句说明**，不能静默丢图。

    静默丢图的症状：模型不知道自己漏看了图，会当成"用户只发了文字"，
    于是言之凿凿地描述一张它没看到的图；用户也收不到任何提示。
    """

    def test_notice_is_added_even_when_text_is_present(self) -> None:
        from agent.mechanisms.model_provider import _strip_images

        out = _strip_images([{
            "role": "user",
            "content": [
                {"type": "text", "text": "这张图什么颜色？"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}},
            ],
        }])
        text = str(out[0].get("content"))
        self.assertIn("这张图什么颜色？", text, msg="原文字必须保留")
        self.assertIn("图片", text, msg="必须说明图片被省略了")
        self.assertNotIn("image_url", str(out[0]), msg="图片本身必须已被移除")

    def test_notice_still_added_when_there_is_no_text(self) -> None:
        from agent.mechanisms.model_provider import _strip_images

        out = _strip_images([{
            "role": "user",
            "content": [{"type": "image_url",
                         "image_url": {"url": "data:image/png;base64,AA"}}],
        }])
        self.assertIn("图片", str(out[0].get("content")))

    def test_plain_text_is_untouched(self) -> None:
        from agent.mechanisms.model_provider import _strip_images

        out = _strip_images([{"role": "user", "content": "只有文字"}])
        self.assertEqual(out[0]["content"], "只有文字")

class SessionModelSelectionTest(unittest.TestCase):
    """会话级模型选择：选中即生效、可读回、**跨进程仍在**。

    选择必须落盘：只活在内存里的话，换个进程/换台机器打开同一会话就回默认，
    而"选了却没生效"比"没有这个功能"更坏 —— 用户以为换成了另一个模型。
    """

    def setUp(self) -> None:
        import tempfile
        from pathlib import Path as _P

        self._tmp = tempfile.TemporaryDirectory()
        self.dir = _P(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _state(self, default_model: str = "base-model"):
        from agent.mechanisms.live_state import LiveState

        return LiveState(storage_dir=self.dir, default_model=default_model)

    def test_select_then_read_back(self) -> None:
        st = self._state()
        self.assertEqual(st.get_model("cid-12345678"), "base-model",
                         msg="未选择时应回落到全局默认")
        st.set_model("cid-12345678", "chosen-model")
        self.assertEqual(st.get_model("cid-12345678"), "chosen-model")

    def test_choice_survives_a_new_process(self) -> None:
        """换一个 LiveState 实例（= 换进程）后选择仍在 —— 靠落盘，不靠内存。"""
        self._state().set_model("cid-12345678", "chosen-model")
        again = self._state()
        self.assertEqual(again.get_model("cid-12345678"), "chosen-model")

    def test_empty_clears_the_choice(self) -> None:
        st = self._state()
        st.set_model("cid-12345678", "chosen-model")
        st.set_model("cid-12345678", "")
        self.assertEqual(st.get_model("cid-12345678"), "base-model")

    def test_read_only_is_never_used(self) -> None:
        """**只读**会话（`is_read_only` 的 cid）不落盘 —— 同 todo 的白名单纪律。"""
        st = self._state()
        st.set_model("../../etc/passwd", "x")
        self.assertEqual(list(self.dir.iterdir()), [],
                         msg="非法 cid 不得拼出路径")

class AvailableModelsWireTest(unittest.TestCase):
    """`/health` 的 `allowed_models` 必须给出**完整清单**。

    它是经典 UI 模型下拉的唯一数据来源，也是选择时的白名单。
    清单不得退化成"只有当前模型"——那样**下拉只画一项，且选择被白名单校验拒掉**。
    """

    def _app(self):
        from agent.app import build_app

        app = build_app()
        app._available_models = ["m-one", "m-two", "m-three"]
        return app

    def test_health_lists_all_configured_models(self) -> None:
        from agent.shell.classic_adapter.adapter import ClassicAdapter

        adapter = ClassicAdapter(self._app())
        body = adapter.health()
        self.assertEqual(body.get("allowed_models"), ["m-one", "m-two", "m-three"])

    def test_current_model_is_always_in_the_list(self) -> None:
        """`model` 必须在清单里，否则 UI 的白名单校验会丢弃它（顶栏永远"加载中"）。"""
        from agent.shell.classic_adapter.adapter import ClassicAdapter

        app = self._app()
        app._available_models = ["other-a", "other-b"]
        body = ClassicAdapter(app).health()
        provider_model = str(getattr(app.provider, "model", "") or "")
        if provider_model:
            self.assertIn(provider_model, body.get("allowed_models") or [])

    def test_shell_health_also_lists_all_models(self) -> None:
        from agent.shell.web import create_server

        app = self._app()
        _srv, shell = create_server(app, host="127.0.0.1", port=0)
        _status, body = shell.health()
        self.assertEqual(body.get("allowed_models"), ["m-one", "m-two", "m-three"])

class UserFacingTextTest(unittest.TestCase):
    """用户可见的文案不得混入内部术语。

    `_DEEPSEEK_HTTP_HINTS` 的取值会作为 `ModelRequestError.detail` 直接回给用户，
    所以它只能说清"哪一端出了问题"。

    只查这些字符串的**取值**，不查注释。
    """

    #: 不该出现在用户可见文案里的词
    INTERNAL_TERMS = ("上一版", "原项目", "重构", "移植")

    def test_http_hints_are_user_facing_and_history_free(self) -> None:
        from agent.mechanisms.model_provider import _DEEPSEEK_HTTP_HINTS

        self.assertEqual(len(self.INTERNAL_TERMS), 4, "禁用词表不得被误改")
        self.assertEqual(len(set(self.INTERNAL_TERMS)), 4, "禁用词不得重复")
        self.assertTrue(_DEEPSEEK_HTTP_HINTS, "提示表不该为空")
        for status, text in _DEEPSEEK_HTTP_HINTS.items():
            for bad in self.INTERNAL_TERMS:
                self.assertNotIn(
                    bad, text,
                    f"HTTP {status} 的提示语含内部术语 {bad!r}：{text!r} —— "
                    "它直接显示给用户，应说清是「模型服务端」的问题")

    def test_500_and_503_name_the_model_server(self) -> None:
        from agent.mechanisms.model_provider import _DEEPSEEK_HTTP_HINTS

        for status in (500, 503):
            self.assertIn("服务端", _DEEPSEEK_HTTP_HINTS[status],
                          f"HTTP {status} 的提示应指明是「服务端」的问题")
