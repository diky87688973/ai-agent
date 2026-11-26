# -*- coding: utf-8 -*-
"""端点错误映射：参数错必须是 400，引擎不可用是 503，不能冒成 500。

用假对象驱动 handler，不依赖模型服务，能在任意环境跑。
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any

from agent.common.tts_contract import TTSEngineUnavailable
from plugins.tts.plugin import (
    make_route_voice_current,
    make_route_voice_delete,
    make_route_voice_list,
    make_route_voice_options,
    make_route_voice_preview,
    make_route_voice_save,
)


class _FakeLab:
    """按需抛错的替身。"""

    def __init__(self, error: BaseException | None = None) -> None:
        self._error = error

    def _maybe_raise(self) -> None:
        if self._error is not None:
            raise self._error

    def preview(self, dims: Any) -> Any:
        self._maybe_raise()
        return SimpleNamespace(mime="audio/wav", sample_rate=24000, audio=b"\x00\x00")

    def save(self, dims: Any, voice_id: str) -> Any:
        self._maybe_raise()
        return {"id": voice_id}

    def list_voices(self) -> Any:
        self._maybe_raise()
        return []

    def delete_voice(self, voice_id: str) -> Any:
        self._maybe_raise()
        return {"id": voice_id}

    def set_current(self, voice_id: str) -> Any:
        self._maybe_raise()
        return {"voice_id": voice_id}


def _service(lab: Any) -> Any:
    return SimpleNamespace(lab=lab, config=SimpleNamespace(voice_id="fanyin"))


_DIMS = {"dim_age": "少女", "dim_timbre": "清亮", "dim_persona": "温柔亲切",
         "dim_pace": "适中", "dim_emotion": "平和"}


class _Base(unittest.TestCase):
    def status(self, handler: Any, args: Any) -> int:
        result = handler(args)
        self.assertIsInstance(result, tuple)
        return int(result[0])


class ErrorMappingTest(_Base):
    def test_options_ok(self) -> None:
        handler = make_route_voice_options(None, _service(_FakeLab()))
        self.assertEqual(self.status(handler, None), 200)

    def test_preview_value_error_is_400(self) -> None:
        handler = make_route_voice_preview(None, _service(_FakeLab(ValueError("缺少维度 timbre"))))
        self.assertEqual(self.status(handler, {"body": {"dim_age": "少女"}}), 400)

    def test_save_value_error_is_400(self) -> None:
        handler = make_route_voice_save(None, _service(_FakeLab(ValueError("非法音色 id"))))
        self.assertEqual(self.status(handler, {"body": dict(_DIMS, id="1bad")}), 400)

    def test_list_value_error_is_400(self) -> None:
        handler = make_route_voice_list(None, _service(_FakeLab(ValueError("服务返回无法解析"))))
        self.assertEqual(self.status(handler, None), 400)

    def test_delete_value_error_is_400(self) -> None:
        handler = make_route_voice_delete(None, _service(_FakeLab(ValueError("非法音色 id"))))
        self.assertEqual(self.status(handler, {"body": {"id": "BAD ID"}}), 400)

    def test_current_value_error_is_400(self) -> None:
        handler = make_route_voice_current(None, _service(_FakeLab(ValueError("不存在"))))
        self.assertEqual(self.status(handler, {"body": {"id": "nosuch"}}), 400)


class EngineUnavailableTest(_Base):
    def test_preview_is_503(self) -> None:
        handler = make_route_voice_preview(None, _service(_FakeLab(TTSEngineUnavailable("起不来"))))
        self.assertEqual(self.status(handler, {"body": _DIMS}), 503)

    def test_list_is_503(self) -> None:
        handler = make_route_voice_list(None, _service(_FakeLab(TTSEngineUnavailable("起不来"))))
        self.assertEqual(self.status(handler, None), 503)

    def test_save_is_503(self) -> None:
        handler = make_route_voice_save(
            None, _service(_FakeLab(TTSEngineUnavailable("起不来"))))
        self.assertEqual(self.status(handler, {"body": dict(_DIMS, id="fanyin")}), 503)


class NoLabTest(_Base):
    def test_network_engine_returns_400(self) -> None:
        service = SimpleNamespace(lab=None, config=SimpleNamespace(voice_id=""))
        for factory in (make_route_voice_options, make_route_voice_preview,
                        make_route_voice_save, make_route_voice_list,
                        make_route_voice_delete, make_route_voice_current):
            with self.subTest(factory=factory.__name__):
                self.assertEqual(self.status(factory(None, service), {"body": {}}), 400)


if __name__ == "__main__":
    unittest.main()
