# -*- coding: utf-8 -*-
"""两条前端路径各自的返回契约。

刷新渲染走 `/api/chat/history`：**只读** `items`（气泡与工具卡）、顶层
`context_layout`（右栏分段条）、`todo_list`（清单）。这三样就是回显的全部依据 ——
`events`（逐条老事件）曾占该响应体的 99.6%，而浏览器一个字段都不读它，已删除。

实时与重连走 SSE：帧由 `ClassicStream.translate` 产出，每帧带合法
`conversation_id`（前端按它分派到正确的会话页面），且**不漏内核坐标 `_seq`** ——
漏了它会带过期坐标，客户端拿旧坐标重连会重复收到那批帧。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.core.events import Event  # noqa: E402
from agent.mechanisms.session_store import SessionStore  # noqa: E402
from agent.shell.classic_adapter.adapter import ClassicAdapter  # noqa: E402

CID = "frame-align-0001"


class _FakeApp:
    """只够适配层用的最小 App：store + 工具注册表（布局要拼系统提示词）。"""

    def __init__(self, store: SessionStore) -> None:
        from agent.capabilities.registry import ToolRegistry

        self.store = store
        self.plugin_host = None
        self.registry = ToolRegistry()


def _events() -> List[Event]:
    """覆盖几条代表性事件：轮次边界、流式增量、工具调用、用量。"""
    return [
        Event("turn_started", {}),
        Event("input_claimed", {"content": "读一下 README"}),
        Event("llm_started", {"model": "m", "messages": 3, "tools": 41}),
        Event("reasoning_delta", {"text": "先看文件"}),
        Event("assistant_delta", {"text": "好的"}),
        Event("model_message", {"content": "", "tool_calls": [
            {"id": "c1", "name": "read_file", "arguments": {"path": "README.md"}}]}),
        Event("tool_started", {"call_id": "c1", "name": "read_file", "arguments": {}}),
        Event("tool_ended", {"call_id": "c1", "name": "read_file", "status": "ok",
                             "data": {"stdout": "hi"}}),
        Event("usage", {"prompt_tokens": 10, "completion_tokens": 2}),
        Event("turn_ended", {"paused": False, "passes": 1}),
    ]


class HistoryContractTest(unittest.TestCase):
    """`/api/chat/history` 的返回契约：回显需要什么、不需要什么。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = SessionStore(Path(self._tmp.name))
        self.store.append(CID, _events())
        self.adapter = ClassicAdapter(_FakeApp(self.store))

    def test_payload_carries_only_what_the_page_reads(self) -> None:
        """只给回显需要的三样：`ok` / `items` / `context_layout` / `todo_list`。"""
        payload = self.adapter.history(CID)
        self.assertIs(payload.get("ok"), True)
        self.assertEqual(payload.get("conversation_id"), CID)
        self.assertIsInstance(payload.get("items"), list)
        self.assertIn("context_layout", payload)
        self.assertIsInstance(payload.get("todo_list"), list)

    def test_no_events_field(self) -> None:
        """逐条老事件不再随回显下发 —— 浏览器不读它，而它按事件条数增长。"""
        self.assertNotIn("events", self.adapter.history(CID))

    def test_items_carry_tool_role_for_cards(self) -> None:
        """工具卡靠 `items` 里的 `tool` 角色重建（气泡之外还有卡片要恢复）。"""
        items = self.adapter.history(CID)["items"]
        roles = [i.get("role") for i in items]
        self.assertIn("user", roles)
        self.assertIn("tool", roles)


class SseFrameContractTest(unittest.TestCase):
    """SSE 帧的契约。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = SessionStore(Path(self._tmp.name))
        self.store.append(CID, _events())

    def _frames(self) -> List[Dict[str, Any]]:
        from agent.shell.classic_adapter.outbound import ClassicStream

        stream = ClassicStream(CID, mode_resolver=lambda c: "auto",
                               model_resolver=lambda c="": "m")
        frames: List[Dict[str, Any]] = []
        for seq, _cid, event in self.store.tail_across(-1, limit=1000):
            payload = dict(event.data or {})
            payload["_seq"] = seq
            frames.extend(stream.translate(str(event.type), payload))
        return frames

    def test_every_frame_carries_cid(self) -> None:
        frames = self._frames()
        self.assertTrue(frames)
        for f in frames:
            self.assertTrue(str(f.get("conversation_id") or "").strip()
                            or f.get("type") in (
                                "heartbeat", "global_sse_ready", "plugins_changed"),
                            msg=f"帧缺 conversation_id：{f}")

    def test_seq_never_leaks_into_frame_payloads(self) -> None:
        """内核坐标只用于 SSE 的 `id:` 行，不能留在帧载荷里。"""
        for f in self._frames():
            self.assertNotIn("_seq", f)

    def test_frames_are_single_line_json(self) -> None:
        """一帧一行 JSON（SSE 的 `data:` 行按行发，不能含裸换行）。"""
        for f in self._frames():
            self.assertNotIn("\n", json.dumps(f, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
