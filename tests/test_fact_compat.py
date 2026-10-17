# -*- coding: utf-8 -*-
"""历史事实形态在当前内核里仍被消费。

老记录里有些事实用的是当时的写法（例如用户作答写成 `tool_result`，
当前内核写 `tool_done` / `tool_failed`）。不认它的后果不是"少一条消息"，
而是**用户的作答在模型眼里消失** —— 请求层只能补一句占位。
"""
from __future__ import annotations

import json
import unittest

from agent.core.events import Event


class ClassicToolResultTest(unittest.TestCase):
    """**历史记录里的 `tool_result` 结果事实必须仍被消费**。

    用户作答在旧记录里写成 `tool_result`（当前内核写 `tool_done` / `tool_failed`）。
    不认它的后果不是"少一条消息"，而是**用户的作答在模型眼里消失** ——
    请求层只能补一句"这次工具调用没有产生结果"的占位。
    """

    def _events(self):
        return [
            Event("turn_started", {"text": "写文件"}),
            Event("input_claimed", {"content": "写到 <盘根>/text.txt"}),
            Event("model_message", {"content": "需要你确认。", "tool_calls": [
                {"id": "call-confirm-1", "name": "user_confirm",
                 "arguments": {"title": "确认写入", "confirms": ["确认写入", "取消"]}}]}),
            Event("tool_started", {"call_id": "call-confirm-1", "name": "user_confirm",
                                   "arguments": {}}),
            Event("tool_suspended", {"call_id": "call-confirm-1", "name": "user_confirm",
                                     "envelope": {"title": "确认写入"}}),
            Event("tool_ended", {"call_id": "call-confirm-1", "name": "user_confirm",
                                 "status": "suspended"}),
            Event("input_claimed", {"content": ""}),
            # 历史格式的结果事实：
            Event("tool_result", {"call_id": "call-confirm-1", "ok": True,
                                  "data": {"confirm": "确认写入"}, "error": ""}),
        ]

    def test_user_answer_survives_in_the_tool_message(self) -> None:
        from agent.core.session_log import SessionLog

        log = SessionLog()
        log.append(self._events())
        for label, msgs in (("derive_messages", log.derive_messages()),
                            ("derive_request_messages", log.derive_request_messages())):
            hit = [m for m in msgs
                   if str(m.get("tool_call_id") or "") == "call-confirm-1"]
            self.assertEqual(len(hit), 1,
                             msg=f"[{label}] 该调用应恰好一条 tool 消息，实际 {len(hit)}")
            self.assertIn("确认写入", str(hit[0].get("content")),
                          msg=f"[{label}] 用户的作答必须真的到模型手里")

    def test_new_format_result_is_not_duplicated(self) -> None:
        """新格式（`tool_done` + `tool_ended`）下**不得**因为认 `tool_result` 而多一条。"""
        from agent.core.events import Event
        from agent.core.session_log import SessionLog

        log = SessionLog()
        log.append([
            Event("model_message", {"content": "", "tool_calls": [
                {"id": "c1", "name": "echo", "arguments": {}}]}),
            Event("tool_done", {"call_id": "c1", "name": "echo", "data": "结果"}),
            Event("tool_ended", {"call_id": "c1", "name": "echo", "status": "done"}),
        ])
        msgs = log.derive_request_messages()
        hit = [m for m in msgs if str(m.get("tool_call_id") or "") == "c1"]
        self.assertEqual(len(hit), 1, msg=f"只应一条 tool 消息，实际 {len(hit)}")
        self.assertEqual(
            str(hit[0].get("content")),
            json.dumps({"ok": True, "data": "结果"}, ensure_ascii=False),
        )

    def test_await_user_intermediate_result_does_not_reach_the_model(self) -> None:
        """标了 `await_user` 的**中间**结果不交给模型（按定义还没返回）。"""
        from agent.core.events import Event
        from agent.core.session_log import SessionLog

        log = SessionLog()
        log.append([
            Event("model_message", {"content": "", "tool_calls": [
                {"id": "c2", "name": "ask", "arguments": {}}]}),
            Event("tool_result", {"call_id": "c2", "ok": True, "await_user": True,
                                  "data": {"question": "选哪个？"}}),
        ])
        self.assertEqual([m for m in log.derive_messages()
                          if str(m.get("tool_call_id") or "") == "c2"], [],
                         msg="中间结果不得进模型上下文")

    def test_cancel_without_a_closing_terminal_still_reaches_the_model(self) -> None:
        """取消只写下 tool_failed、没有第二条终态时，模型仍要看到取消，而不是被请去重问。"""
        from agent.core.session_log import SessionLog

        log = SessionLog()
        log.append([
            Event("model_message", {"content": "请确认。", "tool_calls": [
                {"id": "call-confirm-1", "name": "user_confirm", "arguments": {}}]}),
            Event("tool_ended", {"call_id": "call-confirm-1", "name": "user_confirm",
                                 "status": "suspended"}),
            Event("tool_failed", {"call_id": "call-confirm-1", "name": "user_confirm",
                                  "error": "用户取消了这次确认（未作答）"}),
        ])
        for label, msgs in (("derive_messages", log.derive_messages()),
                            ("derive_request_messages", log.derive_request_messages())):
            hit = [m for m in msgs if str(m.get("tool_call_id") or "") == "call-confirm-1"]
            self.assertEqual(len(hit), 1, msg=f"[{label}] 应恰好一条 tool 消息，实际 {len(hit)}")
            text = str(hit[0].get("content"))
            self.assertIn("用户取消了这次确认", text, msg=f"[{label}] 模型必须看见取消")
            self.assertNotIn("请按需重新发起", text, msg=f"[{label}] 不能把取消说成没结果再请重问")
