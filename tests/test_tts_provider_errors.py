# -*- coding: utf-8 -*-
"""Breeze 请求的 HTTP 错误分层：引擎层不可用与单段合成失败必须分开。

分开才能让「并发忙」「服务暂不可用」触发回落，而不是把整段播报判死。
"""
from __future__ import annotations

import io
import unittest
import urllib.error
from unittest import mock

from agent.common.tts_contract import TTSEngineUnavailable, TTSRequest, TTSSynthesisError
from plugins.tts import breeze_provider


class _FakeSupervisor:
    def ensure_ready(self) -> str:
        return "http://127.0.0.1:18137"

    def missing_reason(self) -> str:
        return ""


class _ErrorOpener:
    def __init__(self, code: int, detail: bytes = b'{"error":"x"}') -> None:
        self._code = code
        self._detail = detail

    def open(self, request, timeout=None):
        raise urllib.error.HTTPError(
            "http://127.0.0.1:18137/v1/audio/speech", self._code, "err", {},
            io.BytesIO(self._detail))


def _provider() -> "breeze_provider.BreezeProvider":
    return breeze_provider.BreezeProvider(
        supervisor=_FakeSupervisor(), voice_desc="一位温柔的女性", emotion="",
        cfg_scale=3.0, voice_id="fanyin", temperature=0.9, top_k=50)


class HttpErrorMappingTest(unittest.TestCase):
    def _raise_with(self, code: int) -> BaseException:
        with mock.patch.object(breeze_provider, "_NO_PROXY", _ErrorOpener(code)):
            with self.assertRaises((TTSEngineUnavailable, TTSSynthesisError)) as ctx:
                _provider().synthesize(TTSRequest(text="测试一句话。", timeout_s=30))
        return ctx.exception

    def test_busy_is_engine_unavailable(self) -> None:
        self.assertIsInstance(self._raise_with(409), TTSEngineUnavailable)

    def test_throttled_is_engine_unavailable(self) -> None:
        self.assertIsInstance(self._raise_with(429), TTSEngineUnavailable)

    def test_service_down_is_engine_unavailable(self) -> None:
        self.assertIsInstance(self._raise_with(503), TTSEngineUnavailable)

    def test_bad_request_is_synthesis_error(self) -> None:
        self.assertIsInstance(self._raise_with(400), TTSSynthesisError)

    def test_missing_model_is_synthesis_error(self) -> None:
        self.assertIsInstance(self._raise_with(404), TTSSynthesisError)

    def test_error_message_keeps_detail(self) -> None:
        exc = self._raise_with(409)
        self.assertIn("409", str(exc))


if __name__ == "__main__":
    unittest.main()
