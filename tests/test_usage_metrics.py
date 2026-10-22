# -*- coding: utf-8 -*-
"""命中率口径测试：只用官方 usage 的三个值，不自己造。

命中率一律取自官方返回值。这条测试守三件事：

1. 官方返回的 `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` 原样落进
   `usage` 事实、原样转发到 SSE（不改名、不丢字段、不重算）；
2. 界面读的就是契约里那几个字段名（读错名 = 命中率永远 0）；
3. 界面显示的命中率是"官方命中 / (官方命中 + 官方未命中)"，分母不含估算。
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.shell.classic_adapter import contract as C  # noqa: E402
from agent.shell.classic_adapter.outbound import ClassicStream  # noqa: E402
from agent.shell.ui_bundle import read_ui_js  # noqa: E402

#: 官方返回的字段（DeepSeek 文档：usage 里的缓存命中情况）
OFFICIAL = {
    "prompt_tokens": 1000,
    "completion_tokens": 200,
    "prompt_cache_hit_tokens": 800,
    "prompt_cache_miss_tokens": 200,
}


class UsageFieldsAreOfficialTest(unittest.TestCase):
    """官方字段一路原样：事件 → 转发 → 界面读取。"""

    def test_contract_lists_the_official_fields(self) -> None:
        for name in ("prompt_cache_hit_tokens", "prompt_cache_miss_tokens",
                     "prompt_tokens", "completion_tokens"):
            self.assertIn(name, C.SSE_USAGE_FIELDS, msg=f"契约少了 {name}")

    def _stream(self) -> ClassicStream:
        """最小可用的适配流：`_on_usage` 只用到 `cid` 与 `_ev`。"""
        stream = ClassicStream.__new__(ClassicStream)
        stream.cid = "usage-metrics-cid"
        stream._frame_seq = None
        return stream

    def test_outbound_forwards_them_unchanged(self) -> None:
        stream = self._stream()
        out = ClassicStream._on_usage(stream, dict(OFFICIAL))
        self.assertEqual(len(out), 1)
        frame = out[0]
        self.assertEqual(frame.get("type"), "usage")
        got = frame.get("usage") or {}
        for key, value in OFFICIAL.items():
            self.assertEqual(got.get(key), value,
                             msg=f"{key} 被改过或丢了：{got!r}")

    def test_unknown_extra_fields_are_dropped_not_invented(self) -> None:
        stream = self._stream()
        payload = dict(OFFICIAL)
        payload["prompt_tokens_details"] = {"cached_tokens": 800}
        got = (ClassicStream._on_usage(stream, payload)[0].get("usage") or {})
        self.assertNotIn("prompt_tokens_details", got,
                         msg="只转发契约里的字段，不塞别的东西")

class UiReadsTheOfficialFieldsTest(unittest.TestCase):
    """界面读的字段名与契约一致；命中率只用官方两个值算。"""

    def _src(self) -> str:
        return read_ui_js()

    def test_ui_reads_the_official_names(self) -> None:
        src = self._src()
        for name in C.SSE_USAGE_FIELDS:
            if name in ("prompt_tokens", "completion_tokens",
                        "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"):
                self.assertIn(f"u.{name}", src, msg=f"界面没读 {name}")

    def test_hit_rate_uses_only_the_official_pair(self) -> None:
        src = self._src()
        m = re.search(r"const totalCache=([^;]+);const hitPct=([^;]+);", src)
        self.assertIsNotNone(m, msg="找不到命中率的算法")
        expr = m.group(0)
        self.assertIn("totalCacheHitTokens", expr)
        self.assertIn("totalCacheMissTokens", expr)
        # 分母只能是官方两个值之和：出现估算器就是口径混了
        for forbidden in ("total_tokens", "estimate", "budget_tokens", "layout"):
            self.assertNotIn(forbidden, expr, msg=f"命中率掺了 {forbidden}")

    def test_accumulators_only_add_official_values(self) -> None:
        src = self._src()
        self.assertIn("totalCacheHitTokens+=hitTok", src)
        self.assertIn("totalCacheMissTokens+=missTok", src)
        self.assertIn("Number(u.prompt_cache_hit_tokens??0)", src)
        self.assertIn("Number(u.prompt_cache_miss_tokens??0)", src)


class WindowComesFromKernelTest(unittest.TestCase):
    """用量环分母 = 内核给的模型窗口，不是写死的常量。"""

    def test_pipeline_reports_the_configured_window(self) -> None:
        from agent.mechanisms.context import ContextPipeline

        pipe = ContextPipeline("c", model_context_window=1_000_000)
        payload = pipe.layout_payload(budget_tokens=700_000)
        self.assertEqual(payload["model_max_context_tokens"], 1_000_000)
        self.assertEqual(payload["budget_tokens"], 700_000)
        # 界面经 context_layout 灌入同一字段
        src = read_ui_js()
        self.assertIn("function setModelContextWindow(", src)
        self.assertIn("setModelContextWindow(ev.model_max_context_tokens)", src)


if __name__ == "__main__":
    unittest.main()
