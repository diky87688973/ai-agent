# -*- coding: utf-8 -*-
"""估算与上游用量对账：字符近似会系统性偏小，预算与压缩都按同一个修正值算。

实测偏差来源：同一轮本地 64.6 万 token、网关报 90.2 万，压缩判据按偏小的
那份算，护栏提前失效。这里钉住修正只做乘算，不再引入第二套口径。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.core.context_usage import TokenCalibration  # noqa: E402
from agent.mechanisms.context.pipeline import (  # noqa: E402
    TOKEN_RATIO_MAX,
    TOKEN_RATIO_MIN,
    ContextPipeline,
)


def _pipeline() -> ContextPipeline:
    pipeline = ContextPipeline("ratio")
    pipeline.append_system("abcd")
    pipeline.append_new_msg("user", "12345678")
    return pipeline


class TokenRatioTest(unittest.TestCase):
    """上游比值 → 估算乘算。"""

    def test_default_ratio_is_identity(self) -> None:
        pipeline = _pipeline()
        raw = pipeline.raw_total_token_estimate()
        self.assertEqual(pipeline.token_ratio, 1.0)
        self.assertEqual(pipeline.total_token_estimate(), raw)

    def test_observed_ratio_scales_every_consumer(self) -> None:
        """分段与合计读同一份，乘算只发生一次。"""

        pipeline = _pipeline()
        raw = pipeline.raw_total_token_estimate()
        pipeline.observe_usage(raw * 2, raw)
        self.assertAlmostEqual(pipeline.token_ratio, 2.0)
        self.assertEqual(pipeline.total_token_estimate(), 2 * raw)
        segments = pipeline.calculate_tokens()
        self.assertEqual(sum(segments.values()), pipeline.total_token_estimate())

    def test_ratio_is_clamped(self) -> None:
        pipeline = _pipeline()
        raw = pipeline.raw_total_token_estimate()
        pipeline.observe_usage(10 ** 9, raw)
        self.assertLessEqual(pipeline.token_ratio, TOKEN_RATIO_MAX)
        pipeline.observe_usage(1, raw)
        self.assertGreaterEqual(pipeline.token_ratio, TOKEN_RATIO_MIN)

    def test_invalid_usage_is_ignored(self) -> None:
        pipeline = _pipeline()
        before = pipeline.token_ratio
        pipeline.observe_usage(0, 100)
        pipeline.observe_usage(100, 0)
        pipeline.observe_usage("x", 100)
        pipeline.observe_usage(100, None)
        self.assertEqual(pipeline.token_ratio, before)

    def test_ratio_uses_median_of_samples(self) -> None:
        """单次抖动不该把预算带飞：四次样本里一次离群，中位数不受影响。"""

        pipeline = _pipeline()
        raw = pipeline.raw_total_token_estimate()
        for _ in range(3):
            pipeline.observe_usage(raw * 2, raw)
        pipeline.observe_usage(raw * 3, raw)
        self.assertAlmostEqual(pipeline.token_ratio, 2.0)


class CalibrationContractTest(unittest.TestCase):
    """能力面走 `TokenCalibration` 协议，模块不再按方法名探测。"""

    def test_pipeline_satisfies_the_protocol(self) -> None:
        self.assertIsInstance(_pipeline(), TokenCalibration)

    def test_plain_object_is_not_calibratable(self) -> None:
        """只实现装配的替身不算具备计量能力：模块据此跳过校正。"""

        self.assertNotIsInstance(object(), TokenCalibration)

    def test_module_skips_context_without_the_protocol(self) -> None:
        from agent.core.modules.model_mod import ModelModule

        module = ModelModule(context=object())
        module._observe_usage({"prompt_tokens": 1234})


if __name__ == "__main__":
    unittest.main()
