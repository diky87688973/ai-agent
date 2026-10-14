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

_PNG_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
            "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def _img() -> dict:
    """附件形态与上传链路一致（`mime` + `data_base64`）。"""
    return {"mime": "image/png", "data_base64": _PNG_B64}


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

class ImagesAlwaysReachTheWireTest(unittest.TestCase):
    """图片一律原样发给模型 —— 不按模型名猜能力、不做降级剥图。

    "名字含 vision 才算视觉模型"是猜的判据：`deepseek-flash` 这类名字里没有
    `vision` 的模型其实支持图片，被剥图后模型只能看到一句占位说明，
    用户以为发了图、模型却什么也没看到。
    """

    def test_image_block_survives_into_the_payload(self) -> None:
        p = _provider("deepseek-flash")
        list(p.stream(LogicalRequest(messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "这张图什么颜色？"},
                {"type": "image_url",
                 "image_url": {"url": "data:image/png;base64,AA"}},
            ],
        }], tools=[])))
        sent = p.payloads[0]["messages"][0]["content"]
        self.assertIsInstance(sent, list, msg="多模态 content 必须原样下发")
        kinds = [part.get("type") for part in sent]
        self.assertIn("image_url", kinds, msg="图片块不能被剥掉")
        self.assertIn("text", kinds, msg="文字块要保留")

    def test_plain_text_message_is_untouched(self) -> None:
        p = _provider("deepseek-flash")
        list(p.stream(LogicalRequest(messages=[
            {"role": "user", "content": "只有文字"}], tools=[])))
        self.assertEqual(p.payloads[0]["messages"][0]["content"], "只有文字")

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


class ReasonNotReplayedTest(unittest.TestCase):
    """历史推理不回传：它必然未命中缓存，回传等于每轮多算几万 token。"""

    def _sample(self):
        return [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1", "reasoning_content": "旧推理",
             "tool_calls": [{"id": "c1", "name": "t", "arguments": {}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "结果"},
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a2", "reasoning_content": "本轮推理"},
        ]

    def test_cut_drops_everything_before_it(self) -> None:
        from agent.mechanisms.model_provider import _to_wire_messages

        wire = _to_wire_messages(self._sample(), keep_reasoning_from=5)
        self.assertNotIn("reasoning_content", wire[2])
        self.assertEqual(wire[5].get("reasoning_content"), "本轮推理")

    def test_cut_none_keeps_everything(self) -> None:
        from agent.mechanisms.model_provider import _to_wire_messages

        wire = _to_wire_messages(self._sample(), keep_reasoning_from=None)
        self.assertEqual(wire[2].get("reasoning_content"), "旧推理")

    def test_tool_calls_survive_the_cut(self) -> None:
        from agent.mechanisms.model_provider import _to_wire_messages

        wire = _to_wire_messages(self._sample(), keep_reasoning_from=5)
        calls = wire[2].get("tool_calls") or []
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["function"]["name"], "t")

    def test_original_messages_are_not_mutated(self) -> None:
        from agent.mechanisms.model_provider import _to_wire_messages

        sample = self._sample()
        _to_wire_messages(sample, keep_reasoning_from=5)
        self.assertEqual(sample[2].get("reasoning_content"), "旧推理")

    def test_provider_passes_the_boundary_and_defaults_to_stripping(self) -> None:
        from agent.mechanisms.model_provider import OpenAICompatibleProvider

        src = (ROOT / "agent/mechanisms/model_provider.py").read_text(encoding="utf-8")
        self.assertIn('getattr(request, "turn_start", None)', src)
        provider = OpenAICompatibleProvider(base_url="http://x/v1", api_key="k", model="m")
        self.assertFalse(provider.replay_history_reasoning)
        self.assertTrue(OpenAICompatibleProvider(
            base_url="http://x/v1", api_key="k", model="m",
            replay_history_reasoning=True).replay_history_reasoning)


class TurnStartAssemblyTest(unittest.TestCase):
    """装配时把"本轮起点"标出来，provider 才有裁的依据。"""

    def test_model_module_marks_turn_start(self) -> None:
        src = (ROOT / "agent/core/modules.py").read_text(encoding="utf-8")
        self.assertIn("turn_start=len(messages) - len(dialogue) + turn_start", src)

    def test_port_default_keeps_everything(self) -> None:
        from agent.core.ports import LogicalRequest

        req = LogicalRequest(messages=[{"role": "user", "content": "x"}], tools=[])
        self.assertIsNone(req.turn_start)
