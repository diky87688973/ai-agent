# -*- coding: utf-8 -*-
"""ContextPipeline 测试。

- 数据模型与展平（分块 / Round·ContextChunk / 展平顺序 / user 起轮）；
- 窗口与摘要调度（越界轮三分支 / 取段区间 / 工具链外扩 / 素材切轮）；
- 待并摘要 / 估算 / 统计 / 追加语义 / 时序重建。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict, Tuple

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.mechanisms.context_pipeline import (  # noqa: E402
    CHUNK_ORDER,
    ContextChunk,
    ContextPipeline,
    Round,
    adjust_excerpt_range_half_open,
    approx_tokens_text,
    flat_messages_to_user_rounds,
)


def _msg(role: str, content: str, **extra: Any) -> Dict[str, Any]:
    return {"role": role, "content": content, **extra}

def _round(*pairs: Tuple[str, str]) -> Round:
    r = Round()
    for role, content in pairs:
        r.append(role, content)
    return r

def _tool_call_msg(tc_id: str) -> Dict[str, Any]:
    return _msg(
        "assistant",
        "",
        tool_calls=[
            {"id": tc_id, "type": "function", "function": {"name": "f", "arguments": "{}"}}
        ],
    )

class ChunksAndFlattenTest(unittest.TestCase):
    """数据模型与展平。"""

    def test_seven_chunks_order_and_add(self) -> None:

        p = ContextPipeline("conv")
        self.assertEqual([c.name for c in p.chunks], list(CHUNK_ORDER))
        self.assertEqual(set(p.name_map.keys()), set(CHUNK_ORDER))
        custom = ContextChunk("自定义")
        custom.append("system", "X", True)
        p.add(custom)
        self.assertIs(p.name_map["自定义"], custom)
        self.assertEqual(p.chunks[-1].name, "自定义")
        self.assertIn({"role": "system", "content": "X"}, p.flatten_to_messages())

    def test_round_and_chunk_append_semantics(self) -> None:

        chunk = ContextChunk("t")
        chunk.append("user", "a", True)
        chunk.append("assistant", "b", False)
        self.assertEqual(chunk.get_count(), 1)
        self.assertEqual(len(chunk.rounds[0].messages), 2)
        chunk.append("user", "c", True)
        self.assertEqual(chunk.get_count(), 2)
        chunk2 = ContextChunk("t2")
        chunk2.append("assistant", "x", False)  # 空块：尽管 is_new_msg=False 仍新开轮
        self.assertEqual(chunk2.get_count(), 1)

    def test_flat_messages_to_user_rounds(self) -> None:

        msgs = [
            _msg("system", "lead"),
            _msg("user", "u1", _agent_round_id="r1"),
            _msg("assistant", "a1"),
            _msg("user", "u2"),
            _msg("assistant", "a2"),
        ]
        rounds = flat_messages_to_user_rounds(msgs)
        self.assertEqual(len(rounds), 2)
        self.assertEqual(rounds[0].round_id, "r1")
        self.assertEqual(len(rounds[0].messages), 2)
        self.assertIsNone(rounds[1].round_id)

class ExcerptTest(unittest.TestCase):
    """摘要取段与工具链完整性。"""

    def test_adjust_back_extends_over_tool_chain(self) -> None:

        msgs = [
            _msg("user", "u1"),
            _tool_call_msg("c1"),
            _msg("tool", "t1"),
            _msg("user", "u2"),
            _msg("assistant", "a2"),
        ]
        # 起点落在 tool(2) 上 → 回扩至发起链的 assistant(1)（不含更早的 user）
        self.assertEqual(adjust_excerpt_range_half_open(msgs, 2, 4), (1, 4))
        # 多个连续 tool：起点落在末位 tool(3) → 回扩至 assistant(1)
        msgs_multi = [
            _msg("user", "u1"),
            _tool_call_msg("c1"),
            _msg("tool", "t1"),
            _msg("tool", "t2"),
            _msg("user", "u2"),
        ]
        self.assertEqual(adjust_excerpt_range_half_open(msgs_multi, 3, 5), (1, 5))

    def test_adjust_extends_end_for_open_results(self) -> None:

        msgs = [
            _msg("user", "u1"),
            _tool_call_msg("c1"),
            _msg("tool", "t1"),
            _msg("user", "u2"),
        ]
        self.assertEqual(adjust_excerpt_range_half_open(msgs, 0, 2), (0, 3))

class MemoryAndEstimateTest(unittest.TestCase):
    """待并摘要 / 估算 / 统计 / 追加。"""

    def test_pending_mem_flow(self) -> None:

        p = ContextPipeline("conv-9")
        p.put_new_mem_file("/tmp/mem.md", [_round(("user", "old"))])
        self.assertEqual(p.pending_mem_file_path, "/tmp/mem.md")
        self.assertEqual(len(p.pending_over_rounds or []), 1)
        calls = []

        def merge_fn(cid: str, messages: list) -> None:
            calls.append((cid, [m["content"] for m in messages]))

        target = [_msg("user", "x")]
        p.try_load_pending_mem_file(target, merge_fn)
        self.assertEqual(calls, [("conv-9", ["x"])])
        self.assertIsNone(p.pending_mem_file_path)
        self.assertIsNone(p.pending_over_rounds)

    def test_token_estimates(self) -> None:

        self.assertEqual(approx_tokens_text(""), 0)
        self.assertEqual(approx_tokens_text("abcd"), 5)
        p = ContextPipeline("c")
        p.append_system("abcd")
        p.append_new_msg("user", "12345678")

        def fn(m: Dict[str, Any]) -> int:
            return len(str(m.get("content") or ""))

        per = p.calculate_tokens(fn)
        self.assertEqual(per["系统提示词"], 4)
        self.assertEqual(per["近期记忆"], 8)
        self.assertEqual(per["插件段落"], 0)
        self.assertEqual(p.total_token_estimate(fn), sum(per.values()))

    def test_round_count(self) -> None:

        p = ContextPipeline("c")
        p.append_system("s")
        p.append_new_msg("user", "u")
        p.append_msg("assistant", "a")
        counts = p.calculate_round_count()
        self.assertEqual(counts["系统提示词"], 1)
        self.assertEqual(counts["近期记忆"], 1)
        self.assertEqual(counts["模式"], 0)

    def test_append_new_msg_and_append_msg(self) -> None:

        p = ContextPipeline("c")
        p.append_new_msg("user", "u1")
        p.append_msg("assistant", "a1")
        p.append_new_msg("user", "u2")
        full = p.name_map["近期记忆"]
        self.assertEqual(full.get_count(), 2)
        self.assertEqual([m["content"] for m in full.rounds[0].messages], ["u1", "a1"])

class RebuildTest(unittest.TestCase):
    """时序重建（走 MVP 路径）。"""

    def test_rebuild_from_messages(self) -> None:
        p = ContextPipeline("c")
        p.rebuild_from_messages(
            [_msg("user", "u1"), _msg("assistant", "a1"), _msg("user", "u2")]
        )
        full = p.name_map["近期记忆"]
        self.assertEqual(full.get_count(), 2)
        self.assertEqual(full.rounds[0].messages[0]["content"], "u1")

class DefaultConfigValues(unittest.TestCase):
    """配置默认值与机制层常量必须一致（三处口径：config.py / 管线常量 / 压缩器签名）。"""

    def test_summary_token_threshold_default(self) -> None:
        from agent.config import get_context
        from agent.mechanisms.context_pipeline import DEFAULT_SUMMARY_TOKEN_THRESHOLD
        c = get_context()
        self.assertEqual(c["summary_token_threshold"], 700000)
        self.assertEqual(DEFAULT_SUMMARY_TOKEN_THRESHOLD, 700000)

    def test_compactor_signature_matches_config(self) -> None:
        import inspect

        from agent.config import get_context
        from agent.mechanisms.context_compactor import ContextCompactor
        sig = inspect.signature(ContextCompactor.__init__)
        c = get_context()
        self.assertEqual(sig.parameters["summary_token_threshold"].default,
                         c["summary_token_threshold"])
        self.assertEqual(sig.parameters["full_user_rounds"].default,
                         c["full_user_rounds"])

    def test_other_context_defaults(self) -> None:
        from agent.config import get_context
        c = get_context()
        self.assertEqual(c["summary_output_max_chars"], 5000)
        self.assertEqual(c["image_turns"], 1)
        self.assertEqual(c["image_max"], 8)


class MaxPassesConfigTest(unittest.TestCase):
    """`[agent] max_passes`：一回合的操作次数上限，可配。"""

    def test_default_is_64(self) -> None:
        from agent.config import DEFAULT_MAX_PASSES, get_max_passes
        from agent.core.host import MAX_PASSES_DEFAULT
        self.assertEqual(MAX_PASSES_DEFAULT, 64)
        self.assertEqual(DEFAULT_MAX_PASSES, 64, msg="config 转出的默认值要与内核一致")
        self.assertEqual(get_max_passes(), 64)

    def test_config_value_wins(self) -> None:
        import tempfile
        from pathlib import Path

        from agent.config import get_max_passes
        with tempfile.TemporaryDirectory() as tmp:
            ini = Path(tmp) / "config.ini"
            ini.write_text("[agent]\nmax_passes = 200\n", encoding="utf-8")
            self.assertEqual(get_max_passes(ini), 200)

    def test_bad_value_falls_back(self) -> None:
        """写错不该让回合跑不起来：非法值回落默认，0/负数按 1。"""
        import tempfile
        from pathlib import Path

        from agent.config import get_max_passes
        with tempfile.TemporaryDirectory() as tmp:
            for text, want in (("max_passes = abc\n", 64),
                               ("max_passes =\n", 64),
                               ("max_passes = 0\n", 1),
                               ("max_passes = -5\n", 1),
                               ("max_passes = 3\n", 3)):
                ini = Path(tmp) / "config.ini"
                ini.write_text(f"[agent]\n{text}", encoding="utf-8")
                self.assertEqual(get_max_passes(ini), want, msg=text.strip())

    def test_app_carries_the_value(self) -> None:
        import inspect

        from agent.app import App
        from agent.core.host import MAX_PASSES_DEFAULT
        sig = inspect.signature(App.__init__)
        self.assertEqual(sig.parameters["max_passes"].default, MAX_PASSES_DEFAULT)

    def test_engine_carries_the_value(self) -> None:
        import inspect

        from agent.config import get_max_passes
        from agent.core.engine import Engine
        sig = inspect.signature(Engine.__init__)
        self.assertEqual(sig.parameters["max_passes"].default, get_max_passes())

if __name__ == "__main__":
    unittest.main()
