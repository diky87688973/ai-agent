# -*- coding: utf-8 -*-
"""工具调用配对修补：只补缺结果，只删孤儿结果，其余原样保留。"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.core.session_log import (  # noqa: E402
    REPAIR_REASON_INTERRUPTED,
    REPAIR_REASON_SUSPENDED,
    ensure_tool_pairs,
)


def _shape(messages):
    """消息序列的可比较形状：角色 + 声明/回答的 id。"""
    out = []
    for msg in messages:
        role = msg.get("role")
        if role == "tool":
            out.append(f"tool:{msg.get('tool_call_id')}")
        elif role == "assistant" and msg.get("tool_calls"):
            ids = ",".join(str(c.get("id") or "") for c in msg["tool_calls"])
            out.append(f"assistant:[{ids}]")
        else:
            out.append(str(role))
    return out


class EnsureToolPairsTest(unittest.TestCase):
    """缺结果补占位，孤儿结果删除，真实结果与调用相邻。"""

    def test_missing_result_gets_placeholder(self) -> None:
        """声明了两个 id 只回来一个：缺的那个紧跟声明补占位。"""
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}, {"id": "c2"}]},
            {"role": "tool", "tool_call_id": "c1", "content": "{}"},
        ]
        out = ensure_tool_pairs(messages)
        # 占位紧跟声明；已有的 tool 消息位置不变，整体只是插入一条
        self.assertEqual(_shape(out), ["user", "assistant:[c1,c2]", "tool:c2", "tool:c1"])
        placeholder = json.loads(out[2]["content"])
        self.assertFalse(placeholder["ok"])
        self.assertIn("没有回执", placeholder["error"])

    def test_placeholder_text_follows_reason(self) -> None:
        """补位文案按成因分档：挂起、中断、未知三套，不合用一句。"""
        messages = [
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]},
        ]
        suspended = ensure_tool_pairs(
            messages, reasons={"c1": REPAIR_REASON_SUSPENDED})
        interrupted = ensure_tool_pairs(
            messages, reasons={"c1": REPAIR_REASON_INTERRUPTED})
        unknown = ensure_tool_pairs(messages)

        suspended_text = json.loads(suspended[1]["content"])["error"]
        interrupted_text = json.loads(interrupted[1]["content"])["error"]
        unknown_text = json.loads(unknown[1]["content"])["error"]

        self.assertIn("用户", suspended_text)
        self.assertNotIn("用户", interrupted_text)
        self.assertNotIn("用户", unknown_text)
        self.assertIn("异常中断", interrupted_text)
        self.assertEqual(len({suspended_text, interrupted_text, unknown_text}), 3)

    def test_placeholder_does_not_explain_turn(self) -> None:
        """补位只说调用没结果，不解释回合怎么结束。"""
        messages = [
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]},
        ]
        for reason in (REPAIR_REASON_SUSPENDED, REPAIR_REASON_INTERRUPTED, ""):
            out = ensure_tool_pairs(messages, reasons={"c1": reason})
            text = json.loads(out[1]["content"])["error"]
            with self.subTest(reason=reason or "unknown"):
                self.assertNotIn("回合", text)

    def test_placeholder_is_brief_and_impersonal(self) -> None:
        """补位文案给模型看：第三人称指用户，不得用「你」；且保持短句。"""
        messages = [
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]},
        ]
        for reason in (REPAIR_REASON_SUSPENDED, REPAIR_REASON_INTERRUPTED, ""):
            out = ensure_tool_pairs(messages, reasons={"c1": reason})
            text = json.loads(out[1]["content"])["error"]
            with self.subTest(reason=reason or "unknown"):
                self.assertNotIn("你", text)
                self.assertLessEqual(len(text), 30)

    def test_placeholder_text_ends_without_full_stop(self) -> None:
        """三档文案一律不加句号。"""
        messages = [
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]},
        ]
        for reason in (REPAIR_REASON_SUSPENDED, REPAIR_REASON_INTERRUPTED, ""):
            out = ensure_tool_pairs(messages, reasons={"c1": reason})
            text = json.loads(out[1]["content"])["error"]
            with self.subTest(reason=reason or "unknown"):
                self.assertFalse(
                    text.endswith("。") or text.endswith("."),
                    msg=f"补位文案不得以句号结尾：{text!r}")

    def test_orphan_result_is_dropped(self) -> None:
        """没有任何 assistant 声明过的 tool 消息：删掉，不补合成声明。"""
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "tool", "tool_call_id": "c9", "content": "{}"},
            {"role": "assistant", "content": "done"},
        ]
        out = ensure_tool_pairs(messages)
        self.assertEqual(_shape(out), ["user", "assistant"])
        self.assertEqual(out[1]["content"], "done")

    def test_duplicate_declaration_is_left_alone(self) -> None:
        """同一 ID 的两次调用分别配对，已有的相邻结果留给当前调用。"""
        messages = [
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]},
            {"role": "tool", "tool_call_id": "c1", "content": "{}"},
        ]
        out = ensure_tool_pairs(messages)
        self.assertEqual(
            _shape(out), ["assistant:[c1]", "tool:c1", "assistant:[c1]", "tool:c1"])
        self.assertEqual(out[-1], messages[-1])

    def test_extra_result_is_orphan_and_late_result_moves_to_its_call(self) -> None:
        """迟到的真实结果移到调用旁，多出来的无主结果从请求投影移除。"""
        messages = [
            {"role": "user", "content": "开始"},
            {"role": "assistant", "tool_calls": [{"id": "c1", "name": "echo"}]},
            {"role": "user", "content": "后续输入"},
            {"role": "tool", "tool_call_id": "c1", "content": "真实结果"},
            {"role": "tool", "tool_call_id": "c1", "content": "重复结果"},
        ]
        expected = [messages[i] for i in (0, 1, 3, 2)]
        self.assertEqual(ensure_tool_pairs(messages), expected)
        self.assertEqual(ensure_tool_pairs(expected), expected)
        from agent.mechanisms.providers.anthropic import _to_anthropic_messages
        wire = _to_anthropic_messages(expected)
        self.assertEqual(wire[2]["content"][0]["type"], "tool_result")

    def test_empty_call_id_is_left_alone(self) -> None:
        """空 id 不在这里派生：适配器解析入口已经排除这种形状。"""
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "", "name": "x"}]},
        ]
        out = ensure_tool_pairs(messages)
        self.assertEqual(out, messages)

    def test_multiple_missing_results_all_filled(self) -> None:
        """三个 id 只回来一个：另外两个都补占位，不丢任何一条。"""
        messages = [
            {"role": "assistant", "content": "",
             "tool_calls": [{"id": "a"}, {"id": "b"}, {"id": "c"}]},
            {"role": "tool", "tool_call_id": "b", "content": "{}"},
        ]
        out = ensure_tool_pairs(messages)
        self.assertEqual(
            _shape(out), ["assistant:[a,b,c]", "tool:a", "tool:c", "tool:b"])

    def test_no_existing_message_is_dropped(self) -> None:
        """除孤儿外，已有消息一条都不丢，且顺序不变。"""
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "文字", "tool_calls": [{"id": "c1"}]},
            {"role": "tool", "tool_call_id": "c1", "content": "{}"},
            {"role": "assistant", "content": "收尾"},
        ]
        out = ensure_tool_pairs(messages)
        self.assertEqual(out, messages)

    def test_well_formed_sequence_is_untouched(self) -> None:
        """已经成对的序列原样返回。"""
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]},
            {"role": "tool", "tool_call_id": "c1", "content": "{}"},
            {"role": "assistant", "content": "done"},
        ]
        self.assertEqual(ensure_tool_pairs(messages), messages)

    def test_empty_input(self) -> None:
        """空序列返回空。"""
        self.assertEqual(ensure_tool_pairs([]), [])

    def test_input_is_not_mutated(self) -> None:
        """修补不修改入参。"""
        messages = [{"role": "assistant", "content": "",
                     "tool_calls": [{"id": "c1"}]}]
        before = json.dumps(messages, ensure_ascii=False, sort_keys=True)
        ensure_tool_pairs(messages)
        self.assertEqual(json.dumps(messages, ensure_ascii=False, sort_keys=True), before)

    def test_idempotent(self) -> None:
        """对输出再修补一次不再变动。"""
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}, {"id": "c2"}]},
            {"role": "tool", "tool_call_id": "c1", "content": "{}"},
            {"role": "tool", "tool_call_id": "orphan", "content": "{}"},
        ]
        once = ensure_tool_pairs(messages)
        twice = ensure_tool_pairs(once)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
