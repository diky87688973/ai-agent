# -*- coding: utf-8 -*-
"""会话待发送队列：状态机、附件与持久化。"""
from __future__ import annotations

import base64
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.mechanisms.conversation_queue import ConversationQueue, QueueError  # noqa: E402

_PNG = base64.b64encode(
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x00\x03\x00\x01\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84\x00\x00\x00"
    b"\x00IEND\xaeB`\x82"
).decode("ascii")


class ConversationQueueTest(unittest.TestCase):
    CID = "queue-test-0001"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.queue = ConversationQueue(Path(self._tmp.name) / "queues")

    def test_fifo_and_state(self) -> None:
        first = self.queue.enqueue(self.CID, content="one")
        second = self.queue.enqueue(self.CID, content="two")
        self.assertEqual(self.queue.size(self.CID), 2)
        claimed = self.queue.claim_after_turn(self.CID)
        self.assertEqual(claimed["content"], "one")
        self.queue.complete(self.CID, first["id"])
        self.assertEqual(self.queue.list(self.CID)["items"][0]["content"], "two")
        self.queue.cancel(self.CID, second["id"])
        self.assertEqual(self.queue.size(self.CID), 0)

    def test_image_roundtrip_and_recall(self) -> None:
        item = self.queue.enqueue(
            self.CID,
            attachments=[{"mime": "image/png", "data_base64": _PNG}],
        )
        self.assertEqual(len(item["attachments"]), 1)
        recalled = self.queue.recall(self.CID, item["id"])
        self.assertEqual(recalled["attachments"][0]["data_base64"], _PNG)
        self.assertEqual(self.queue.size(self.CID), 0)
        self.queue.cancel(self.CID, recalled["id"])

    def test_draft_resubmit_preserves_agent_origin(self) -> None:
        item = self.queue.enqueue(
            self.CID,
            content="from agent",
            origin="agent",
            sender={"cid": "agent-0001", "name": "Worker", "thread_id": "t1"},
        )
        recalled = self.queue.recall(self.CID, item["id"])
        again = self.queue.resubmit_draft(
            self.CID, recalled["id"], content="edited",
        )
        self.assertEqual(again["origin"], "agent")
        self.assertEqual(again["sender"]["name"], "Worker")
        self.assertEqual(again["content"], "edited")

    def test_claimed_cannot_be_recalled_or_cancelled(self) -> None:
        item = self.queue.enqueue(self.CID, content="x")
        self.queue.claim_after_turn(self.CID)
        with self.assertRaises(QueueError):
            self.queue.recall(self.CID, item["id"])
        with self.assertRaises(QueueError):
            self.queue.cancel(self.CID, item["id"])

    def test_persistence_and_claimed_recovery(self) -> None:
        item = self.queue.enqueue(self.CID, content="persisted")
        self.queue.claim_after_turn(self.CID)
        again = ConversationQueue(Path(self._tmp.name) / "queues")
        recovered = again.list(self.CID)["items"]
        self.assertEqual(recovered[0]["id"], item["id"])
        self.assertEqual(recovered[0]["state"], "queued")
        self.assertEqual(recovered[0]["content"], "persisted")

    def test_system_item_hidden_but_claimable(self) -> None:
        item = self.queue.enqueue(
            self.CID, origin="system",
            payload={"resume": {"call_id": "c1", "ok": True}},
        )
        self.assertEqual(self.queue.list(self.CID)["items"], [])
        claimed = self.queue.claim_after_turn(self.CID)
        self.assertEqual(claimed["id"], item["id"])
        self.assertEqual(claimed["payload"]["resume"]["call_id"], "c1")


if __name__ == "__main__":
    unittest.main()
