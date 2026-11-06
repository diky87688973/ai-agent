# -*- coding: utf-8 -*-
"""定时唤醒是独立任务：只投影本次输入及其后续工具链。"""
from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from agent.core.events import Event
from agent.core.modules.model_mod import ModelModule
from agent.core.session_log import SessionLog
from agent.mechanisms.context import ContextPipeline


def _wake(job_id: str, reminder: str, due_at: str) -> Event:
    return Event("input_claimed", {
        "content": reminder,
        "kind": "wake",
        "source": "wake_scheduler",
        "wake_job_id": job_id,
        "due_at": due_at,
    })


def _user(content: str) -> Event:
    return Event("input_claimed", {"content": content})


def _assistant(content: str, tool_calls=None) -> Event:
    data = {"content": content}
    if tool_calls is not None:
        data["tool_calls"] = tool_calls
    return Event("model_message", data)


class _Tools:
    @staticmethod
    def schemas():
        return []


class WakeIsolationTest(unittest.TestCase):
    def test_only_latest_wake_job_and_its_tool_chain_are_visible(self) -> None:
        tool_call = {
            "id": "call-current",
            "type": "function",
            "function": {"name": "echo", "arguments": "{}"},
        }
        log = SessionLog([
            _user("历史普通任务"),
            _assistant("历史普通回答"),
            _wake("wake-old-1", "历史提醒一", "2026-01-01T00:00:00Z"),
            _assistant("历史唤醒回答一"),
            _wake("wake-old-2", "历史提醒二", "2026-01-02T00:00:00Z"),
            _assistant("历史唤醒回答二"),
            _wake("wake-current", "查看当前构建结果", "2026-11-06T01:02:03Z"),
            _assistant("", [tool_call]),
            Event("tool_result", {
                "call_id": "call-current",
                "ok": True,
                "data": {"status": "green"},
            }),
        ])

        messages = log.derive_request_messages_from_latest_wake()
        self.assertIsNotNone(messages)
        rendered = json.dumps(messages, ensure_ascii=False)
        self.assertIn("wake-current", rendered)
        self.assertIn("2026-11-06T01:02:03Z", rendered)
        self.assertIn("查看当前构建结果", rendered)
        self.assertIn("call-current", rendered)
        self.assertIn("green", rendered)
        self.assertNotIn("wake-old-1", rendered)
        self.assertNotIn("wake-old-2", rendered)
        self.assertNotIn("历史提醒", rendered)
        self.assertNotIn("历史普通任务", rendered)

    def test_later_ordinary_input_restores_full_history(self) -> None:
        log = SessionLog([
            _user("需要保留的历史"),
            _assistant("历史回答"),
            _wake("wake-current", "提醒", "2026-11-06T01:02:03Z"),
            _assistant("唤醒回答"),
            _user("新的普通任务"),
        ])
        self.assertIsNone(log.derive_request_messages_from_latest_wake())
        rendered = json.dumps(log.derive_request_messages(), ensure_ascii=False)
        self.assertIn("需要保留的历史", rendered)
        self.assertIn("唤醒回答", rendered)
        self.assertIn("新的普通任务", rendered)

    def test_model_request_keeps_prompts_but_drops_summary_and_compaction_offset(self) -> None:
        log = SessionLog([
            _user("不能进入唤醒请求的历史"),
            _assistant("历史回答"),
            _wake("wake-current", "只执行当前提醒", "2026-11-06T01:02:03Z"),
        ])
        context = ContextPipeline("wake-isolation-0001")
        context.append_system("SYSTEM PROMPT")
        context.append_plugin("PLUGIN PROMPT", key="wake-test", label="测试插件")
        context.set_summary_messages([
            {"role": "system", "content": "OLD COMPRESSED SUMMARY"},
        ])

        class _Compactor:
            covered_end = 99
            summary_token_threshold = 0

            def __init__(self) -> None:
                self.remembered = 0

            def remember_sent_request(self, _messages, _prefix, _tools) -> None:
                self.remembered += 1

        compactor = _Compactor()
        ports = SimpleNamespace(
            log=log.readonly(),
            tool_port=_Tools(),
            conversation_id="wake-isolation-0001",
        )
        _request, messages, _segments = ModelModule(
            context=context, compactor=compactor)._build_request(ports)
        rendered = json.dumps(messages, ensure_ascii=False)
        self.assertIn("SYSTEM PROMPT", rendered)
        self.assertIn("PLUGIN PROMPT", rendered)
        self.assertIn("wake-current", rendered)
        self.assertIn("只执行当前提醒", rendered)
        self.assertNotIn("不能进入唤醒请求的历史", rendered)
        self.assertNotIn("OLD COMPRESSED SUMMARY", rendered)
        self.assertEqual(compactor.remembered, 0)


if __name__ == "__main__":
    unittest.main()
