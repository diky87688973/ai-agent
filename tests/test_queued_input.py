# -*- coding: utf-8 -*-
"""安全插入点：队列消息转成输入事实。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.core.modules.queued_input_mod import QueuedInputModule  # noqa: E402


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
        self.assertEqual(queue.done, ["q1"])

    def test_no_insert_item_is_noop(self) -> None:
        class _Empty(_Queue):
            def claim_insert(self, cid: str):
                return None

        queue = _Empty()
        self.assertEqual(list(QueuedInputModule(queue=queue).execute(_Ports())), [])
        self.assertEqual(queue.done, [])


if __name__ == "__main__":
    unittest.main()
