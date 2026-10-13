# -*- coding: utf-8 -*-
"""ContextPipeline 测试。

- 数据模型与展平（七块 / Round·ContextChunk / 展平顺序 / user 起轮）；
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
    dialogue_summary_excerpt_half_open_for_messages,
    excerpt_slice_to_rounds,
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

    def test_flatten_order_and_empty_skip(self) -> None:

        p = ContextPipeline("conv")
        self.assertEqual(p.flatten_to_messages(), [])
        p.append_system("S1")
        p.append_skill("K1")
        p.append_kb("B1")
        p.set_summaries([_msg("assistant", "SUM")])
        p.set_pure_rounds([_round(("user", "P1"))])
        p.append_new_msg("user", "U1")
        p.append_msg("assistant", "A1")
        p.set_mode_tail(_msg("system", "M1"))
        flat = p.flatten_to_messages()
        self.assertEqual(
            [m["content"] for m in flat],
            ["S1", "K1", "B1", "SUM", "P1", "U1", "A1", "M1"],
        )
        # sanitize 末端统一应用
        kept = p.flatten_to_messages(sanitize_fn=lambda ms: ms[:2])
        self.assertEqual([m["content"] for m in kept], ["S1", "K1"])
        # 深拷贝安全：修改返回不影响内部状态
        flat[0]["content"] = "MUT"
        self.assertEqual(p.flatten_to_messages()[0]["content"], "S1")

    def test_constructor_config(self) -> None:

        p = ContextPipeline(
            "conv-1", pure_user_rounds=1, full_user_rounds=3, summary_token_threshold=100
        )
        self.assertEqual(p.conversation_id, "conv-1")
        self.assertEqual(p.pure_user_rounds, 1)
        self.assertEqual(p.full_user_rounds, 3)
        self.assertEqual(p.summary_token_threshold, 100)

class WindowTest(unittest.TestCase):
    """越界轮提取。"""

    def _build(self, pure_n: int, full_n: int) -> ContextPipeline:
        p = ContextPipeline("c", pure_user_rounds=2, full_user_rounds=2)
        p.set_pure_rounds([_round(("user", f"p{i}")) for i in range(pure_n)])
        for i in range(full_n):
            p.append_new_msg("user", f"f{i}")
        return p

    def test_extract_over_rounds_branches(self) -> None:

        # ③ full(1) < window(4)：excess = 1 + 4 − 4 = 1 → pure[0:1]
        over = self._build(4, 1).extract_over_rounds()
        self.assertEqual([r.messages[0]["content"] for r in over], ["p0"])
        # ③ 无越界：full(1) + pure(1) − window(4) ≤ 0 → []
        self.assertEqual(self._build(1, 1).extract_over_rounds(), [])
        # ② full == window(4)：越界 = 全部 pure
        over = self._build(2, 4).extract_over_rounds()
        self.assertEqual([r.messages[0]["content"] for r in over], ["p0", "p1"])
        # ① full(6) > window(4)：越界 = 全部 pure + full 最早 2 轮
        over = self._build(2, 6).extract_over_rounds()
        self.assertEqual(
            [r.messages[0]["content"] for r in over], ["p0", "p1", "f0", "f1"]
        )
        # 深拷贝：修改返回不影响源
        p = self._build(4, 1)
        over = p.extract_over_rounds()
        over[0].messages[0]["content"] = "X"
        again = p.extract_over_rounds()
        self.assertEqual(again[0].messages[0]["content"], "p0")

class ExcerptTest(unittest.TestCase):
    """摘要取段与工具链完整性。"""

    def test_excerpt_none_cases(self) -> None:

        self.assertIsNone(dialogue_summary_excerpt_half_open_for_messages([], 2, 1))
        self.assertIsNone(
            dialogue_summary_excerpt_half_open_for_messages(
                [_msg("user", "u0"), _msg("assistant", "a0")], 2, 1
            )
        )

    def test_excerpt_branches(self) -> None:

        msgs = [
            _msg("user", "u0"),
            _msg("assistant", "a0"),
            _msg("user", "u1"),
            _msg("assistant", "a1"),
            _msg("user", "u2"),
            _msg("assistant", "a2"),
        ]
        # k(3) > reserve(2)：end_cap = 第 (3−2) 条 user 下标(2) → (0, 2)
        self.assertEqual(dialogue_summary_excerpt_half_open_for_messages(msgs, 1, 1), (0, 2))
        # k(2) ≤ reserve(3) 且 k > full(1)：end_cap = 第 (2−1) 条 user 下标(2) → (0, 2)
        self.assertEqual(dialogue_summary_excerpt_half_open_for_messages(msgs[:4], 1, 2), (0, 2))
        # ContextPipeline 的方法包装：与自由函数的取段入口一致
        p = ContextPipeline("c", pure_user_rounds=1, full_user_rounds=1)
        self.assertEqual(p.dialogue_summary_excerpt_half_open(msgs), (0, 2))

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

    def test_excerpt_slice_to_rounds(self) -> None:

        self.assertEqual(excerpt_slice_to_rounds([], 1, 1), [])
        msgs = [
            _msg("user", "u0"),
            _msg("assistant", "a0"),
            _msg("user", "u1"),
            _msg("assistant", "a1"),
            _msg("user", "u2"),
            _msg("assistant", "a2"),
        ]
        rounds = excerpt_slice_to_rounds(msgs, 1, 1)
        self.assertEqual(len(rounds), 1)
        self.assertEqual([m["content"] for m in rounds[0].messages], ["u0", "a0"])

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
        self.assertEqual(per["知识库"], 0)
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

if __name__ == "__main__":
    unittest.main()
