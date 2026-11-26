# -*- coding: utf-8 -*-
"""降级可见性：本地引擎不可用时，状态必须说清楚，且不能偷偷换成 edge。

这两条是这个插件最容易被掩盖的失败：引擎换了、模型没装，界面上却一切正常。
"""
from __future__ import annotations

import dataclasses
import unittest

from agent.common.tts_contract import (
    TTSCapabilities,
    TTSRequest,
    TTSUnavailable,
)
from plugins.tts.config import load_config
from plugins.tts.plugin import _UnavailableProvider
from plugins.tts.service import INSTALL_HINT, TTSService


class _DeadProvider:
    """本地引擎装不起来的样子：可用性为假、一说话就报错。"""

    name = "breeze"

    def available(self) -> bool:
        return False

    def capabilities(self) -> TTSCapabilities:
        return TTSCapabilities(supports_instruction=False, supports_speed=False,
                               supports_cfg=False, needs_pinyin_hints=False)

    def synthesize(self, request: TTSRequest):
        raise TTSUnavailable("本地引擎不可用")

    def release_idle(self) -> bool:
        return False

    def dispose(self) -> None:
        return None


class _EdgeProvider(_DeadProvider):
    name = "edge"

    def available(self) -> bool:
        return True

    def synthesize(self, request: TTSRequest):
        return "edge-audio"


def _config(**over):
    return dataclasses.replace(load_config(), **over)


class StatusTest(unittest.TestCase):
    def test_engine_is_configured_not_active(self) -> None:
        """engine 必须是配置值；实际在用的放 active_engine。"""
        service = TTSService(_config(engine="breeze"), _EdgeProvider(), None, None,
                             degraded_reason="本地引擎不可用：缺 model_dir")
        status = service.status()
        self.assertEqual(status["engine"], "breeze")
        self.assertEqual(status["active_engine"], "edge")

    def test_degraded_is_visible(self) -> None:
        service = TTSService(_config(engine="breeze"), _EdgeProvider(), None, None,
                             degraded_reason="本地引擎不可用：缺 model_dir")
        status = service.status()
        self.assertTrue(status["degraded"])
        self.assertIn("model_dir", str(status["degraded_reason"]))
        self.assertEqual(status["engine_ready"], False)
        self.assertEqual(status["install_hint"], INSTALL_HINT)

    def test_healthy_engine_has_no_hint(self) -> None:
        class _Ready(_EdgeProvider):
            name = "breeze"

        service = TTSService(_config(engine="breeze"), _Ready(), None, None)
        status = service.status()
        self.assertTrue(status["engine_ready"])
        self.assertFalse(status["degraded"])
        self.assertEqual(status["install_hint"], "")

    def test_edge_engine_has_no_hint(self) -> None:
        service = TTSService(_config(engine="edge"), _EdgeProvider(), None, None)
        status = service.status()
        self.assertTrue(status["engine_ready"])
        self.assertEqual(status["install_hint"], "")


class UnavailableProviderTest(unittest.TestCase):
    def test_raises_with_install_hint(self) -> None:
        provider = _UnavailableProvider("本地引擎不可用：缺 model_dir")
        self.assertFalse(provider.available())
        with self.assertRaises(TTSUnavailable) as ctx:
            provider.synthesize(TTSRequest(text="试一句。"))
        message = str(ctx.exception)
        self.assertIn("model_dir", message)
        self.assertIn(INSTALL_HINT, message)

    def test_capabilities_are_all_off(self) -> None:
        caps = _UnavailableProvider("x").capabilities()
        self.assertFalse(caps.supports_instruction)
        self.assertFalse(caps.supports_speed)
        self.assertFalse(caps.supports_cfg)

    def test_release_and_dispose_are_safe(self) -> None:
        provider = _UnavailableProvider("x")
        self.assertFalse(provider.release_idle())
        provider.dispose()


if __name__ == "__main__":
    unittest.main()
