# -*- coding: utf-8 -*-
"""`provider_meta` 透传契约。

内核不解释厂商私有元数据（Anthropic 的 thinking 块与签名），只保证三件事：

1. 适配器以 `StreamDelta(kind="meta")` 交上来的载荷，被原样收进 `model_message`；
2. `derive_messages()` 把它原样带回 assistant 消息，回放链路不丢签名；
3. 发给 OpenAI 兼容网关的线格式里不得出现这个键（未知字段可能被 400）。

第 3 条同时是负向断言：只要有一条路径漏了剥离，网关就会看到 Anthropic 专属键。
"""
from __future__ import annotations

import unittest

from agent.core.event_name import INPUT_CLAIMED, LLM_DONE, LLM_STARTED, MODEL_MESSAGE
from agent.core.events import Event
from agent.core.model_call import PROVIDER_META_KEY, StreamDelta
from agent.core.modules.model_mod import ModelModule
from agent.core.ports import ModelPort, Ports
from agent.core.session_log import SessionLog


class _ScriptedProvider:
    """按脚本产出流帧；只实现 `stream`，其余交给 `ModelPort` 包装。"""

    model = "scripted"

    def __init__(self, deltas) -> None:
        self._deltas = list(deltas)

    def stream(self, request):
        yield from self._deltas


class _ModelMessageCase(unittest.TestCase):
    def _model_message(self, deltas) -> dict:
        log = SessionLog(events=[Event(INPUT_CLAIMED, {"conversation_id": "c" * 8})])
        ports = Ports(emit=lambda ev: None, log=log,
                      model=ModelPort(_ScriptedProvider(deltas)))
        list(ModelModule().execute(ports))
        found = [ev for ev in log.events if ev.type == MODEL_MESSAGE]
        self.assertEqual(len(found), 1, msg="本轮应恰好落一条 model_message")
        return found[0].data


class LlmEventModelTest(unittest.TestCase):
    """模型生命周期事件必须报告本次请求的模型，而不是 provider 默认值。"""

    def test_done_reports_request_model(self) -> None:
        from agent.core.event_name import LLM_ENDED

        log = SessionLog(events=[Event(INPUT_CLAIMED, {"conversation_id": "c" * 8})])
        ports = Ports(emit=lambda ev: log.append([ev]), log=log,
                      model=ModelPort(_ScriptedProvider([])),
                      conversation_id="c" * 8)
        list(ModelModule(model="chosen-model").execute(ports))
        seen = {ev.type: str(ev.data.get("model") or "") for ev in log.events}
        for kind in (LLM_STARTED, LLM_DONE, LLM_ENDED):
            self.assertEqual(seen.get(kind), "chosen-model",
                             msg=f"{kind} 报默认模型会让多模型的观测与路由不一致")


class ModelMessageMetaTest(_ModelMessageCase):
    def test_meta_delta_is_collected_verbatim(self) -> None:
        blocks = [{"thinking": "想", "signature": "sig-1"}]
        data = self._model_message([
            StreamDelta(kind="text", text="答"),
            StreamDelta(kind="meta", meta={"anthropic": {"thinking_blocks": blocks}}),
        ])
        self.assertEqual(
            data.get(PROVIDER_META_KEY),
            {"anthropic": {"thinking_blocks": blocks}},
            msg="meta 载荷必须原样落进事实，内核不得改写结构",
        )

    def test_no_meta_delta_leaves_the_key_absent(self) -> None:
        data = self._model_message([StreamDelta(kind="text", text="答")])
        self.assertNotIn(PROVIDER_META_KEY, data,
                         msg="没有元数据时不能写空对象：读方以'键不存在'判定无 thinking")

    def test_later_meta_wins_on_shared_keys(self) -> None:
        data = self._model_message([
            StreamDelta(kind="meta", meta={"anthropic": {"thinking_blocks": ["旧"]}}),
            StreamDelta(kind="meta", meta={"anthropic": {"thinking_blocks": ["新"]}}),
        ])
        self.assertEqual(data[PROVIDER_META_KEY]["anthropic"]["thinking_blocks"], ["新"])


class DeriveMessagesMetaTest(unittest.TestCase):
    def test_provider_meta_survives_replay(self) -> None:
        meta = {"anthropic": {"thinking_blocks": [
            {"thinking": "想", "signature": "sig-1"},
        ]}}
        log = SessionLog(events=[
            Event(MODEL_MESSAGE, {"content": "答", PROVIDER_META_KEY: meta}),
        ])
        assistant = [m for m in log.derive_messages() if m["role"] == "assistant"]
        self.assertEqual(assistant[0].get(PROVIDER_META_KEY), meta)

    def test_old_logs_without_the_key_still_derive(self) -> None:
        log = SessionLog(events=[Event(MODEL_MESSAGE, {"content": "答"})])
        assistant = [m for m in log.derive_messages() if m["role"] == "assistant"]
        self.assertNotIn(PROVIDER_META_KEY, assistant[0],
                         msg="可选新增键：旧日志不得要求它存在")

    def test_unknown_subkeys_are_carried_not_validated(self) -> None:
        meta = {"future_vendor": {"whatever": 1}}
        log = SessionLog(events=[
            Event(MODEL_MESSAGE, {"content": "答", PROVIDER_META_KEY: meta}),
        ])
        assistant = [m for m in log.derive_messages() if m["role"] == "assistant"]
        self.assertEqual(assistant[0].get(PROVIDER_META_KEY), meta,
                         msg="前滚契约：未知子键忽略且不报错")


class OpenAiWireNeverSeesMetaTest(unittest.TestCase):
    def test_wire_messages_strip_provider_meta(self) -> None:
        from agent.mechanisms.providers.openai import _to_wire_messages

        wire = _to_wire_messages([
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "a",
             PROVIDER_META_KEY: {"anthropic": {"thinking_blocks": []}}},
        ])
        self.assertNotIn(PROVIDER_META_KEY, wire[1],
                         msg="OpenAI 兼容网关不认识这个键，必须剥掉")


if __name__ == "__main__":
    unittest.main()
