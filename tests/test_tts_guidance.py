# -*- coding: utf-8 -*-
"""语音合成失败时的引导：文案归 tts，上游只透传。

分两层验证：tts 自己能不能拼出「原因 + 加载哪个技能」；ai_speek 是否原样抛出、
有没有自造措辞。
"""
from __future__ import annotations

import dataclasses
import unittest
from unittest import mock

from agent.common.tts_contract import TTSUnavailable
from plugins.ai_cosplay.config import load_config as load_cosplay
from plugins.ai_cosplay.runtime import AICosplayRuntime
from plugins.ai_cosplay.tool import AICosplayTool
from plugins.tts.config import load_config
from plugins.tts.plugin import make_service
from plugins.tts.service import MODEL_DIRECTIVE, TTSService


class _Service:
    def __init__(self, hint, ready=False):
        self._hint = hint
        self._ready = ready

    def ready(self) -> bool:
        return self._ready

    def unavailable_hint(self) -> str:
        return self._hint


class _Runtime:
    def __init__(self, service, config):
        self._service = service
        self.config = config

    def provider_ready(self) -> bool:
        return bool(self._service.ready())

    def provider_reason(self) -> str:
        return AICosplayRuntime.provider_reason(self)


def _tool(hint, ready=False):
    runtime = _Runtime(_Service(hint, ready), load_cosplay())
    tool = AICosplayTool.__new__(AICosplayTool)
    tool._runtime = runtime
    return tool


class PassThroughTest(unittest.TestCase):
    def test_message_is_passed_through_verbatim(self) -> None:
        hint = "本地引擎不可用：缺少 model_dir。" + MODEL_DIRECTIVE
        with self.assertRaises(TTSUnavailable) as ctx:
            _tool(hint).execute({"msg": "说一句。"})
        self.assertEqual(str(ctx.exception), hint)

    def test_empty_hint_falls_back_to_neutral_line(self) -> None:
        with self.assertRaises(TTSUnavailable) as ctx:
            _tool("").execute({"msg": "说一句。"})
        self.assertIn("语音合成不可用", str(ctx.exception))

    def test_status_error_does_not_break_reporting(self) -> None:
        class _Broken:
            def ready(self) -> bool:
                return False

            def unavailable_hint(self) -> str:
                raise RuntimeError("boom")

        runtime = _Runtime(_Broken(), None)
        self.assertEqual(AICosplayRuntime.provider_reason(runtime), "")


class TtsHintTest(unittest.TestCase):
    def _service(self, **over):
        config = dataclasses.replace(load_config(), **over)
        with mock.patch("plugins.tts.plugin.load_config", return_value=config):
            return make_service(None)

    def test_hint_names_skill_when_local_missing(self) -> None:
        hint = self._service(model_dir="", fallback_to_edge=False).unavailable_hint()
        self.assertIn("tts-setup", hint)
        self.assertIn("model_dir", hint)

    def test_hint_orders_user_confirm(self) -> None:
        """只提一句不够：必须明写先调 user_confirm 征得同意。"""
        hint = self._service(model_dir="", fallback_to_edge=False).unavailable_hint()
        self.assertIn("user_confirm", hint)
        self.assertIn("不得只口头提一句", hint)
        self.assertIn("现在安装", hint)

    def test_hint_empty_when_local_ready(self) -> None:
        service = TTSService(dataclasses.replace(load_config(), engine="edge"),
                             _Ready(), None, None)
        self.assertEqual(service.unavailable_hint(), "")

    def test_hint_offers_edge_fallback(self) -> None:
        hint = self._service(model_dir="", fallback_to_edge=False).unavailable_hint()
        self.assertIn("Edge 兜底", hint)


class _Ready:
    name = "edge"

    def available(self) -> bool:
        return True

    def capabilities(self):
        from agent.common.tts_contract import TTSCapabilities
        return TTSCapabilities(supports_instruction=False, supports_speed=False,
                               supports_cfg=False, needs_pinyin_hints=False)

    def synthesize(self, request):
        return "audio"

    def release_idle(self) -> bool:
        return False

    def dispose(self) -> None:
        return None


class AssemblyTest(unittest.TestCase):
    def test_closed_fallback_keeps_local_engine(self) -> None:
        config = dataclasses.replace(load_config(), model_dir="",
                                     fallback_to_edge=False)
        with mock.patch("plugins.tts.plugin.load_config", return_value=config):
            service = make_service(None)
        self.assertFalse(service.ready())
        status = service.status()
        self.assertEqual(status["engine"], "breeze")
        self.assertEqual(status["active_engine"], "breeze")
        self.assertFalse(status["engine_ready"])

    def test_open_fallback_degrades_to_edge(self) -> None:
        config = dataclasses.replace(load_config(), model_dir="",
                                     fallback_to_edge=True)
        with mock.patch("plugins.tts.plugin.load_config", return_value=config):
            service = make_service(None)
        self.assertTrue(service.ready())
        self.assertEqual(service.status()["active_engine"], "edge")
        self.assertTrue(service.status()["degraded"])


if __name__ == "__main__":
    unittest.main()
