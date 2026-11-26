# -*- coding: utf-8 -*-
"""门面的回落策略与进程管理的失败分类。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.common.tts_contract import (
    TTSCapabilities,
    TTSEngineUnavailable,
    TTSNotInstalled,
    TTSRequest,
    TTSResult,
    TTSSynthesisError,
)
from plugins.tts.config import TTSConfig
from plugins.tts.service import TTSService
from plugins.tts.supervisor import ServerSupervisor

_CAPS = TTSCapabilities(True, True, True, False)


class _Provider:
    def __init__(self, name: str, *, fail: Exception | None = None,
                 available: bool = True) -> None:
        self.name = name
        self._fail = fail
        self._available = available
        self.calls = 0

    def capabilities(self) -> TTSCapabilities:
        return _CAPS

    def available(self) -> bool:
        return self._available

    def synthesize(self, request: TTSRequest) -> TTSResult:
        self.calls += 1
        if self._fail is not None:
            raise self._fail
        return TTSResult(audio=b"x", sample_rate=24000, mime="audio/wav", engine=self.name)

    def release_idle(self) -> bool:
        return False

    def dispose(self) -> None:
        pass


def _service(primary: _Provider, fallback: _Provider | None = None) -> TTSService:
    """装配方决定带不带兜底；service 只管用传进来的那个。"""
    return TTSService(TTSConfig(), primary, fallback)


class FallbackTest(unittest.TestCase):
    def test_engine_unavailable_falls_back(self) -> None:
        fallback = _Provider("edge")
        service = _service(_Provider("breeze", fail=TTSEngineUnavailable("启动失败")), fallback)
        result = service.synthesize(TTSRequest(text="你好"))
        self.assertEqual(result.engine, "edge")
        self.assertEqual(fallback.calls, 1)
        self.assertIn("breeze", service.status()["last_fallback_reason"])

    def test_synthesis_error_does_not_fall_back(self) -> None:
        fallback = _Provider("edge")
        service = _service(_Provider("breeze", fail=TTSSynthesisError("被拒绝")), fallback)
        with self.assertRaises(TTSSynthesisError):
            service.synthesize(TTSRequest(text="你好"))
        self.assertEqual(fallback.calls, 0)

    def test_fallback_disabled_keeps_error(self) -> None:
        service = _service(_Provider("breeze", fail=TTSEngineUnavailable("未安装")), None)
        with self.assertRaises(TTSEngineUnavailable):
            service.synthesize(TTSRequest(text="你好"))

    def test_ready_true_when_either_side_works(self) -> None:
        self.assertTrue(_service(_Provider("breeze"), _Provider("edge")).ready())
        self.assertTrue(_service(_Provider("breeze", available=False), _Provider("edge")).ready())
        self.assertFalse(_service(_Provider("breeze", available=False),
                                 _Provider("edge", available=False)).ready())
        self.assertFalse(_service(_Provider("breeze", available=False)).ready())


class StatusTest(unittest.TestCase):
    def test_status_exposes_engine_and_capabilities(self) -> None:
        service = _service(_Provider("breeze"), _Provider("edge"))
        status = service.status()
        self.assertEqual(status["engine"], "breeze")
        self.assertEqual(status["fallback_engine"], "edge")
        self.assertTrue(status["primary_ready"])
        self.assertTrue(status["capabilities"]["supports_instruction"])


class SupervisorTest(unittest.TestCase):
    def test_missing_files_are_reported_before_spawn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            supervisor = ServerSupervisor(exe=root / "nope.exe",
                                          model=root / "nope.gguf", port=18137)
            self.assertIn("推理程序不存在", supervisor.missing_reason())
            with self.assertRaises(TTSNotInstalled):
                supervisor.ensure_ready()

    def test_idle_release_without_process_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            supervisor = ServerSupervisor(exe=root / "nope.exe",
                                          model=root / "nope.gguf", port=18138,
                                          idle_timeout=1.0)
            self.assertFalse(supervisor.release_idle())
            self.assertFalse(supervisor.is_running())


if __name__ == "__main__":
    unittest.main()
