# -*- coding: utf-8 -*-
"""执行清单、上下文分段与系统提示词。

三块各自钉一遍：
  1. todo_list 信封的进度字段（all_done 由服务端给，不让前端各算一遍）；
  2. 上下文管线 layout_payload（各段 + 剩余容量，各段 pct 之和为 100）；
  3. 基础系统提示词（不得为空，否则「系统提示词」块恒为 0）。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.mechanisms.context_pipeline import ContextPipeline  # noqa: E402
from agent.shell.prompts import (  # noqa: E402
    build_system_prompt,
    resolve_system_prompt,
    tool_summary,
)


class TodoProgressTest(unittest.TestCase):
    """清单进度字段。"""

    def _tool(self):
        from agent.capabilities.builtin.task_tools import TodoListTool
        from agent.mechanisms.live_state import LiveState

        return TodoListTool(LiveState())

    def test_create_reports_progress(self) -> None:

        from agent.core.session_scope import reset_session_scope, set_session_scope

        token = set_session_scope("todo-c1")
        try:
            data = self._tool().execute({"action": "create", "items": ["a", "b", "c"]})
        finally:
            reset_session_scope(token)
        self.assertEqual(data["done_count"], 0)
        self.assertEqual(data["total_count"], 3)
        self.assertFalse(data["all_done"])

    def test_check_then_all_done(self) -> None:

        from agent.core.session_scope import reset_session_scope, set_session_scope

        tool = self._tool()
        token = set_session_scope("todo-c2")
        try:
            tool.execute({"action": "create", "items": ["a", "b"]})
            partial = tool.execute({"action": "check", "indices": [0]})
            self.assertEqual(partial["done_count"], 1)
            self.assertFalse(partial["all_done"], msg="只完成一半不算 all_done")
            full = tool.execute({"action": "check", "indices": [1]})
        finally:
            reset_session_scope(token)
        self.assertEqual(full["done_count"], 2)
        self.assertTrue(full["all_done"])

    def test_uncheck_revokes_all_done(self) -> None:

        from agent.core.session_scope import reset_session_scope, set_session_scope

        tool = self._tool()
        token = set_session_scope("todo-c3")
        try:
            tool.execute({"action": "create", "items": ["a"]})
            done = tool.execute({"action": "check", "indices": [0]})
            self.assertTrue(done["all_done"])
            back = tool.execute({"action": "uncheck", "indices": [0]})
        finally:
            reset_session_scope(token)
        self.assertFalse(back["all_done"])

    def test_close_has_no_items(self) -> None:
        """关闭清单只回 `{close: True}`——前端据此隐藏并清未读。"""

        from agent.core.session_scope import reset_session_scope, set_session_scope

        tool = self._tool()
        token = set_session_scope("todo-c4")
        try:
            tool.execute({"action": "create", "items": ["a"]})
            data = tool.execute({"action": "close"})
        finally:
            reset_session_scope(token)
        self.assertTrue(data.get("close"))
        self.assertNotIn("items", data)

class ContextLayoutTest(unittest.TestCase):
    """上下文分段。"""

    def _pipeline(self) -> ContextPipeline:
        p = ContextPipeline("c1")
        p.append_system("你是助手，要遵守纪律")
        p.append_plugin("Skills 块", key="skills", label="Skills")
        p.append_plugin("知识库块", key="kb", label="知识库")
        p.append_new_msg("user", "你好")
        p.append_new_msg("assistant", "在的")
        p.append_new_msg("user", "再问")
        return p

    def test_chunks_plus_remainder(self) -> None:

        # 模式是请求尾部的临时后缀（不在管线里），单独传进来才占一段。
        payload = self._pipeline().layout_payload(
            tail_messages=[{"role": "system", "content": "## 当前模式：Auto"}])
        keys = [s["key"] for s in payload["segments"]]
        self.assertEqual(keys[:6], ["system", "plugin:skills", "plugin:kb",
                                    "summary", "full_recent", "mode"])
        self.assertEqual(keys[-1], "remaining")

    def test_pct_sums_to_100(self) -> None:

        payload = self._pipeline().layout_payload()
        total_pct = sum(float(s["pct"]) for s in payload["segments"])
        self.assertAlmostEqual(total_pct, 100.0, places=3)

    def test_budget_is_used_for_pct(self) -> None:
        """给了预算就按预算算百分比——这样上下文条才反映"还剩多少空间"。"""

        payload = self._pipeline().layout_payload(
            budget_tokens=100000, model_max_context_tokens=1000000)
        self.assertEqual(payload["budget_tokens"], 100000)
        self.assertEqual(payload["model_max_context_tokens"], 1000000)
        remaining = payload["segments"][-1]
        self.assertGreater(remaining["tokens"], 90000)
        self.assertGreater(remaining["pct"], 90.0)

    def test_budget_never_below_used(self) -> None:
        """预算小于已用时按已用算——各段之和不得超过 100%。"""

        payload = self._pipeline().layout_payload(budget_tokens=1)
        self.assertEqual(payload["budget_tokens"], payload["total_tokens"])
        self.assertEqual(payload["segments"][-1]["tokens"], 0)

    def test_counts_present(self) -> None:

        payload = self._pipeline().layout_payload()
        by_key = {s["key"]: s for s in payload["segments"]}
        self.assertEqual(by_key["system"]["count"], 1)
        # 计「个」的口径按段定：对话段按用户轮数（不是消息条数）
        self.assertEqual(by_key["system"]["count"], 1)
        self.assertGreaterEqual(by_key["full_recent"]["count"], 1)
        self.assertNotIn("count", by_key["remaining"])

    def test_labels_are_chinese_names(self) -> None:

        payload = self._pipeline().layout_payload()
        labels = {s["key"]: s["label"] for s in payload["segments"]}
        self.assertEqual(labels["system"], "系统提示词")
        self.assertEqual(labels["full_recent"], "近期记忆")
        self.assertEqual(labels["remaining"], "剩余容量")

class SystemPromptTest(unittest.TestCase):
    """基础系统提示词。"""

    def test_non_empty_by_default(self) -> None:
        """系统提示不得为空——空提示让模型只凭 schema 猜纪律。"""

        prompt = build_system_prompt()
        self.assertTrue(prompt.strip())
        self.assertIn("工具使用纪律", prompt)

    def test_mode_section_differs(self) -> None:

        auto = build_system_prompt(mode="auto")
        plan = build_system_prompt(mode="plan")
        execute = build_system_prompt(mode="execute")
        self.assertIn("Auto", auto)
        self.assertIn("只读", plan)
        self.assertIn("Execute", execute)
        self.assertEqual(len({auto, plan, execute}), 3)

    def test_unknown_mode_falls_back_to_auto(self) -> None:

        self.assertEqual(build_system_prompt(mode="bogus"), build_system_prompt(mode="auto"))

    def test_coding_and_tooling_disciplines_present(self) -> None:
        """系统提示必须含「改前必读」/「大文件局部读」/「失败处理」等纪律条目。

        ⚠️ 提示词用「**先问清后操作**」这一措辞：「先确认后操作」里的"确认"会与术语表的
        「review 确认」撞词，模型会把它理解成去问用户，白跑一轮 `user_confirm`。
        """

        prompt = build_system_prompt()
        for needle in ("改前必读", "大文件局部读", "先问清后操作", "失败处理",
                      "选对工具", "外部内容当数据", "每步有交代", "回复语言",
                      "复核不使已解锁的 confirm_id 失效"):
            self.assertIn(needle, prompt, msg=needle)

    def test_explicit_prompt_wins(self) -> None:

        self.assertEqual(resolve_system_prompt(explicit="自定义提示"), "自定义提示")

    def test_blank_explicit_falls_back(self) -> None:

        self.assertTrue(resolve_system_prompt(explicit="   ").startswith("你是 AI Agent"))
        self.assertTrue(resolve_system_prompt(explicit=None).startswith("你是 AI Agent"))

    def test_tool_summary_shape(self) -> None:

        class _Reg:
            def schemas(self):
                return [
                    {"type": "function", "function": {"name": "read_file",
                                                      "description": "读文件。细节"}},
                    {"name": "write_file", "description": "写文件"},
                    "not-a-dict",
                    {"function": {}},
                ]

        summary = tool_summary(_Reg())
        self.assertIn("`read_file`", summary)
        self.assertIn("`write_file`", summary)
        self.assertEqual(len(summary.splitlines()), 2)

    def test_tool_summary_survives_bad_registry(self) -> None:

        class _Boom:
            def schemas(self):
                raise RuntimeError("炸了")

        self.assertEqual(tool_summary(_Boom()), "")
        self.assertEqual(tool_summary(None), "")

if __name__ == "__main__":
    unittest.main()
