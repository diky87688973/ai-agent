# -*- coding: utf-8 -*-
"""安全插入点：队列消息转成输入事实。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.core.modules.queued_input_mod import QueuedInputModule  # noqa: E402
from agent.mechanisms.conversation_queue import ConversationQueue  # noqa: E402


class _Queue:
    def __init__(self) -> None:
        self.done: list = []
        self.released: list = []

    def claim_insert(self, cid: str):
        return {
            "id": "q1",
            "content": "插入内容",
            "attachments": [{"mime": "image/png", "data_base64": "abc"}],
            "sender": {"cid": "agent-0001", "name": "Worker"},
        }

    def complete(self, cid: str, item_id: str) -> None:
        self.done.append(item_id)

    def release(self, cid: str, item_id: str) -> None:
        self.released.append(item_id)


class _Ports:
    conversation_id = "queue-insert-01"

    def emit(self, type_: str, **data):
        return {"type": type_, "data": data}


class QueuedInputModuleTest(unittest.TestCase):
    def test_claims_one_insert_item_and_emits_input_fact(self) -> None:
        queue = _Queue()
        events = list(QueuedInputModule(queue=queue).execute(_Ports()))
        self.assertEqual(events[0]["type"], "input_claimed")
        self.assertEqual(events[0]["data"]["content"], "插入内容")
        self.assertEqual(events[0]["data"]["_sender"], "agent-0001")
        self.assertEqual(events[0]["data"]["_sender_name"], "Worker")
        self.assertTrue(events[0]["data"]["attachments"][0]["attachment_id"].startswith("att-"))
        self.assertEqual(queue.done, ["q1"])

    def test_batch_contains_system_agent_and_user_inserts_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = ConversationQueue(Path(tmp))
            cid = "queue-batch-0001"
            normal = queue.enqueue(cid, content="普通", origin="user")
            first = queue.enqueue(cid, content="用户插入", origin="user",
                                  delivery="next_pass")
            second = queue.enqueue(cid, content="系统插入", origin="system",
                                   delivery="next_pass")
            third = queue.enqueue(cid, content="Agent 插入", origin="agent",
                                  sender={"cid": "agent-a", "name": "A"},
                                  delivery="next_pass")
            for item in (first, second, third):
                queue.set_insert(cid, item["id"])
            items = queue.claim_insert_batch(cid)
            self.assertEqual([item["content"] for item in items],
                             ["用户插入", "系统插入", "Agent 插入"])
            self.assertEqual(queue.claim_after_turn(cid)["id"], normal["id"])

    def test_batch_emits_each_input_as_a_separate_fact(self) -> None:
        class _BatchQueue(_Queue):
            def claim_insert_batch(self, cid: str):
                return [
                    {"id": "q1", "content": "甲"},
                    {"id": "q2", "content": "乙"},
                ]

        queue = _BatchQueue()
        events = list(QueuedInputModule(queue=queue).execute(_Ports()))
        self.assertEqual([event["type"] for event in events],
                         ["input_claimed", "input_claimed"])
        self.assertEqual([event["data"]["content"] for event in events], ["甲", "乙"])
        self.assertEqual(queue.done, ["q1", "q2"])

    def test_no_insert_item_is_noop(self) -> None:
        class _Empty(_Queue):
            def claim_insert(self, cid: str):
                return None

        queue = _Empty()
        self.assertEqual(list(QueuedInputModule(queue=queue).execute(_Ports())), [])
        self.assertEqual(queue.done, [])


if __name__ == "__main__":
    unittest.main()
