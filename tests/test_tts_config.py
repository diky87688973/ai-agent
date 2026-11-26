# -*- coding: utf-8 -*-
"""语音合成配置的容错行为：设置页能填任意文本，配置层必须扛住。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plugins.tts import config as config_mod
from plugins.tts.config import (
    DEFAULT_CFG_SCALE,
    DEFAULT_EDGE_VOICE,
    DEFAULT_ENGINE,
    DEFAULT_IDLE_TIMEOUT,
    DEFAULT_MODEL,
    DEFAULT_PORT,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_K,
    ConfigError,
    load_config,
)


def _load(text: str):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "plugin-config.ini"
        path.write_text(text, encoding="utf-8")
        return load_config(path)


class EngineFallbackTest(unittest.TestCase):
    def test_unknown_engine_falls_back_with_warning(self) -> None:
        cfg = _load("[config]\nengine = edeg\n")
        self.assertEqual(cfg.engine, DEFAULT_ENGINE)
        self.assertTrue(any("engine" in item for item in cfg.warnings))

    def test_engine_is_case_insensitive(self) -> None:
        self.assertEqual(_load("[config]\nengine = EDGE\n").engine, "edge")

    def test_empty_engine_uses_default(self) -> None:
        cfg = _load("[config]\nengine =\n")
        self.assertEqual(cfg.engine, DEFAULT_ENGINE)
        self.assertEqual(cfg.warnings, ())


class ModelFallbackTest(unittest.TestCase):
    def test_unregistered_model_falls_back_with_warning(self) -> None:
        cfg = _load("[config]\ndefault_model = breeze-tts-9\n")
        self.assertEqual(cfg.default_model, DEFAULT_MODEL)
        self.assertTrue(any("default_model" in item for item in cfg.warnings))

    def test_known_model_is_kept(self) -> None:
        cfg = _load("[config]\ndefault_model = breeze-tts-2-q4k\n")
        self.assertEqual(cfg.default_model, "breeze-tts-2-q4k")
        self.assertEqual(cfg.warnings, ())


class LimitsFallbackTest(unittest.TestCase):
    def test_unknown_speed_key_is_ignored(self) -> None:
        """语速已不归 tts 管：旧配置里残留 speed 不应报错，也不应生效。"""
        cfg = _load("[config]\nspeed = 9\n")
        self.assertFalse(hasattr(cfg, "speed"))
        self.assertEqual(cfg.warnings, ())

    def test_cfg_scale_decimal_is_accepted(self) -> None:
        cfg = _load("[config]\ncfg_scale = 2.5\n")
        self.assertEqual(cfg.cfg_scale, 2.5)
        self.assertEqual(cfg.warnings, ())

    def test_cfg_scale_out_of_range(self) -> None:
        self.assertEqual(_load("[config]\ncfg_scale = 9\n").cfg_scale, DEFAULT_CFG_SCALE)

    def test_port_out_of_range(self) -> None:
        self.assertEqual(_load("[config]\nserver_port = 70000\n").server_port, DEFAULT_PORT)

    def test_negative_idle_is_clamped_to_zero(self) -> None:
        self.assertEqual(_load("[config]\nidle_timeout = -1\n").idle_timeout, 0.0)

    def test_empty_values_use_defaults_silently(self) -> None:
        cfg = _load("[config]\nidle_timeout =\n")
        self.assertEqual(cfg.idle_timeout, DEFAULT_IDLE_TIMEOUT)
        self.assertEqual(cfg.warnings, ())


class SamplingTest(unittest.TestCase):
    def test_defaults_match_model_values(self) -> None:
        """采样默认值跟模型自带值一致：压低会连情绪起伏一起抹平，不作为稳定音色的手段。"""
        cfg = _load("[config]\n")
        self.assertEqual(cfg.temperature, DEFAULT_TEMPERATURE)
        self.assertEqual(cfg.top_k, DEFAULT_TOP_K)

    def test_out_of_range_falls_back(self) -> None:
        cfg = _load("[config]\ntemperature = 9\ntop_k = 500\n")
        self.assertEqual(cfg.temperature, DEFAULT_TEMPERATURE)
        self.assertEqual(cfg.top_k, DEFAULT_TOP_K)
        self.assertEqual(len(cfg.warnings), 2)

    def test_zero_keeps_model_default(self) -> None:
        cfg = _load("[config]\ntemperature = 0\ntop_k = 0\n")
        self.assertEqual(cfg.temperature, 0.0)
        self.assertEqual(cfg.top_k, 0)
        self.assertEqual(cfg.warnings, ())

    def test_decimal_temperature_is_accepted(self) -> None:
        self.assertEqual(_load("[config]\ntemperature = 0.7\n").temperature, 0.7)


class MiscTest(unittest.TestCase):
    def test_empty_edge_voice_falls_back(self) -> None:
        self.assertEqual(_load("[config]\nedge_voice =\n").edge_voice, DEFAULT_EDGE_VOICE)

    def test_broken_file_raises_config_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plugin-config.ini"
            path.write_text("这不是 ini\n", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_missing_file_uses_defaults(self) -> None:
        cfg = load_config(Path(tempfile.gettempdir()) / "tts_no_such_config.ini")
        self.assertEqual(cfg.engine, DEFAULT_ENGINE)
        self.assertEqual(cfg.warnings, ())

    def test_defaults_match_module_constants(self) -> None:
        cfg = config_mod.TTSConfig()
        self.assertEqual(cfg.engine, DEFAULT_ENGINE)
        self.assertEqual(cfg.default_model, DEFAULT_MODEL)


if __name__ == "__main__":
    unittest.main()
