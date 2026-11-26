# -*- coding: utf-8 -*-
"""两个引擎的能力声明与指令拼装：数值语速到自然语言的映射是这里的核心。"""
from __future__ import annotations

import asyncio
import sys
import types
import unittest
from unittest import mock

from agent.common.tts_contract import TTSRequest
from plugins.tts.breeze_provider import BreezeProvider
from plugins.tts.edge_provider import EdgeProvider


class _FakeSupervisor:
    def missing_reason(self) -> str:
        return ""

    def ensure_ready(self) -> str:
        raise AssertionError("本次用例不应触发服务启动")

    def release_idle(self) -> bool:
        return False

    def stop(self) -> None:
        pass


def _breeze(**kwargs) -> BreezeProvider:
    params = {"supervisor": _FakeSupervisor(),
              "voice_desc": "一位温柔清晰的年轻女性",
              "emotion": "平静",
              "cfg_scale": 2.0}
    params.update(kwargs)
    return BreezeProvider(**params)


class InstructionTest(unittest.TestCase):
    def test_explicit_instruction_wins(self) -> None:
        provider = _breeze()
        request = TTSRequest(text="你好", voice="苍老的男声", instruction="压低嗓音，缓慢")
        self.assertEqual(provider.build_instruction(request), "压低嗓音，缓慢")

    def test_upstream_voice_overrides_default_desc(self) -> None:
        provider = _breeze()
        request = TTSRequest(text="你好", voice="低沉的男声", speed=1.2)
        self.assertEqual(provider.build_instruction(request), "低沉的男声，平静")

    def test_default_desc_used_when_upstream_silent(self) -> None:
        provider = _breeze()
        self.assertEqual(provider.build_instruction(TTSRequest(text="你好")),
                         "一位温柔清晰的年轻女性，平静")

    def test_empty_emotion_is_skipped(self) -> None:
        provider = _breeze(emotion="")
        self.assertEqual(provider.build_instruction(TTSRequest(text="你好", voice="女声")),
                         "女声")

    def test_voice_id_drops_voice_description(self) -> None:
        """有参考音色时说话人已定死，再拼音色描述会跟参考音色打架。"""
        provider = _breeze(voice_id="fanyin")
        self.assertEqual(provider.build_instruction(TTSRequest(text="你好", voice="低沉的男声")),
                         "平静")

    def test_voice_id_keeps_emotion(self) -> None:
        provider = _breeze(voice_id="fanyin", emotion="开心")
        self.assertEqual(provider.build_instruction(TTSRequest(text="你好", speed=1.2)),
                         "开心")

    def test_speed_never_enters_instruction(self) -> None:
        """实测该引擎不响应语速描述（要求快反而慢 17%），所以不拼进指令。"""
        provider = _breeze(emotion="")
        self.assertEqual(provider.build_instruction(TTSRequest(text="你好", speed=1.5)),
                         "一位温柔清晰的年轻女性")


class CapabilitiesTest(unittest.TestCase):
    def test_breeze_supports_instruction_and_cfg(self) -> None:
        caps = _breeze().capabilities()
        self.assertTrue(caps.supports_instruction)
        self.assertFalse(caps.supports_speed)
        self.assertTrue(caps.supports_cfg)
        self.assertFalse(caps.needs_pinyin_hints)

    def test_edge_ignores_instruction_and_needs_pinyin(self) -> None:
        caps = EdgeProvider(voice="zh-CN-XiaoxiaoNeural").capabilities()
        self.assertFalse(caps.supports_instruction)
        self.assertTrue(caps.supports_speed)
        self.assertFalse(caps.supports_cfg)
        self.assertTrue(caps.needs_pinyin_hints)

    def test_edge_ignores_upstream_voice(self) -> None:
        provider = EdgeProvider(voice="zh-CN-XiaoxiaoNeural")
        self.assertEqual(provider.name, "edge")
        self.assertFalse(provider.capabilities().supports_instruction)


class TextGuardTest(unittest.TestCase):
    def test_rejects_empty_text(self) -> None:
        from agent.common.tts_contract import TTSSynthesisError

        with self.assertRaises(TTSSynthesisError):
            _breeze().synthesize(TTSRequest(text="   "))

    def test_rejects_overlong_segment(self) -> None:
        from agent.common.tts_contract import TTSSynthesisError

        with self.assertRaises(TTSSynthesisError):
            _breeze().synthesize(TTSRequest(text="字" * 801))


class EdgeSynthesisTest(unittest.TestCase):
    """Edge 引擎走假 edge_tts 模块，验证合成成功、缺依赖、空音频与超时。"""

    def _fake_edge(self, *, delay: float = 0.0, audio: bytes = b"audio"):
        module = types.ModuleType("edge_tts")

        class Communicate:
            def __init__(self, text: str, voice: str, rate: str = "") -> None:
                self.text = text
                self.voice = voice
                self.rate = rate

            async def stream(self):
                if delay:
                    await asyncio.sleep(delay)
                if audio:
                    yield {"type": "audio", "data": audio}

        module.Communicate = Communicate
        return module

    def test_synthesize_uses_configured_voice(self) -> None:
        provider = EdgeProvider(voice="zh-CN-XiaoxiaoNeural")
        with mock.patch.dict(sys.modules, {"edge_tts": self._fake_edge()}):
            self.assertTrue(provider.available())
            result = provider.synthesize(TTSRequest(text="你好", voice="上游诉求", timeout_s=1.0))
        self.assertEqual(result.audio, b"audio")
        self.assertEqual(result.mime, "audio/mpeg")
        self.assertEqual(result.engine, "edge")

    def test_pinyin_is_applied_before_synthesis(self) -> None:
        from plugins.tts import pinyin

        captured: list = []

        class _Recording:
            def apply(self, text: str) -> str:
                captured.append(text)
                return "改写后"

        provider = EdgeProvider(voice="zh-CN-XiaoxiaoNeural", pinyin=_Recording())
        with mock.patch.dict(sys.modules, {"edge_tts": self._fake_edge()}):
            provider.synthesize(TTSRequest(text="36行。", timeout_s=1.0))
        self.assertEqual(captured, ["36行。"])
        self.assertEqual(pinyin.apply("36行。"), "36 háng。")

    def test_missing_dependency(self) -> None:
        from agent.common.tts_contract import TTSEngineUnavailable

        provider = EdgeProvider(voice="zh-CN-XiaoxiaoNeural")
        with mock.patch.dict(sys.modules, {"edge_tts": None}):
            self.assertFalse(provider.available())
            with self.assertRaises(TTSEngineUnavailable):
                provider.synthesize(TTSRequest(text="你好", timeout_s=1.0))

    def test_empty_audio(self) -> None:
        from agent.common.tts_contract import TTSSynthesisError

        provider = EdgeProvider(voice="zh-CN-XiaoxiaoNeural")
        with mock.patch.dict(sys.modules, {"edge_tts": self._fake_edge(audio=b"")}):
            with self.assertRaises(TTSSynthesisError):
                provider.synthesize(TTSRequest(text="你好", timeout_s=1.0))

    def test_timeout(self) -> None:
        from agent.common.tts_contract import TTSSynthesisError

        provider = EdgeProvider(voice="zh-CN-XiaoxiaoNeural")
        with mock.patch.dict(sys.modules, {"edge_tts": self._fake_edge(delay=0.2)}):
            with self.assertRaises(TTSSynthesisError) as ctx:
                provider.synthesize(TTSRequest(text="你好", timeout_s=0.01))
        self.assertIn("超时", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
