# -*- coding: utf-8 -*-
"""写盘四步协议门控测试（id 制）：预览登记 → 确认 → 凭 ID 提交 → 重读。

用真实文件（临时目录）驱动：提交由测试内 helper 消费快照并实际写入，
gate 负责流程控制与状态记账。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.core.tool_call import GateDecision  # noqa: E402
from agent.mechanisms.quality_gate import QualityGate, WriteContext  # noqa: E402


class FourStepGateTest(unittest.TestCase):
    """四步协议本体（id 制）。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.gate = QualityGate()

    def _ready(self, path: Path, content: str) -> str:
        """预览登记 + 确认（四步前两步），返回 confirm_id。"""
        cid = self.gate.register_preview("write_file", {"path": str(path), "content": content})
        self.gate.confirm(cid)
        return cid

    def _commit(self, cid: str) -> GateDecision:
        """模拟提交（工具层）：凭 ID 过 gate；放行则消费快照并真实写入。"""
        decision = self.gate.check_write(WriteContext(confirm_id=cid))
        if not decision.allow:
            return decision
        snapshot = self.gate.take(cid)
        if snapshot:
            target = Path(str(snapshot.get("path")))
            target.write_text(str(snapshot.get("content") or ""), encoding="utf-8")
            self.gate.note_committed(str(target))
        return decision

    def test_no_preview_denied(self) -> None:
        """无预览的直接提交被拒。"""

        target = self.root / "a.txt"
        decision = self.gate.check_write(WriteContext(confirm_id="no-such-id"))
        self.assertFalse(decision.allow)
        self.assertFalse(target.exists())

    def test_unconfirmed_preview_denied(self) -> None:
        """协议顺序：预览后未确认即提交，被拒。"""
        target = self.root / "b.txt"
        cid = self.gate.register_preview("write_file", {"path": str(target), "content": "draft"})
        decision = self.gate.check_write(WriteContext(confirm_id=cid))
        self.assertFalse(decision.allow)
        # 语义：明确是"未解锁"，且**必须点明解锁入口** ——
        # 只说"请先完成确认"有歧义，模型会误去问用户（`user_confirm`）；
        # 这里要的是 review 确认（`review_conclusion` 带 `confirm_id` 解锁）。
        self.assertIn("未解锁", decision.reason)
        self.assertIn("review_conclusion", decision.reason)
        self.assertIn("confirm_id", decision.reason)

    def test_snapshot_binding_and_single_use(self) -> None:
        """提交内容以快照为准；confirm_id 一次性。"""

        target = self.root / "c.txt"
        cid = self._ready(target, "version-A")
        ok = self._commit(cid)
        self.assertTrue(ok.allow)
        self.assertEqual(target.read_text(encoding="utf-8"), "version-A")
        again = self.gate.check_write(WriteContext(confirm_id=cid))
        self.assertFalse(again.allow)
        self.assertIsNone(self.gate.take(cid))

    def test_happy_path_four_steps(self) -> None:
        """四步全流程：预览 → 确认 → 提交（真实写入）→ 重读。"""
        target = self.root / "d.txt"
        cid = self._ready(target, "final")
        decision = self._commit(cid)
        self.assertTrue(decision.allow)
        self.assertEqual(target.read_text(encoding="utf-8"), "final")
        norm = str(target).replace("\\", "/")
        self.assertIn(norm, self.gate.needs_reread)
        self.assertIn(norm, self.gate.pending_review)
        self.assertFalse(self.gate.reviewed_ok)
        self.gate.note_read(str(target))
        self.gate.review_done()
        self.assertNotIn(norm, self.gate.needs_reread)
        self.assertEqual(self.gate.pending_review, [])
        self.assertTrue(self.gate.reviewed_ok)

    def test_reread_required_for_next_edit(self) -> None:
        """写后未重读前，再次提交被拒；read 后放行。"""

        target = self.root / "e.txt"
        cid1 = self._ready(target, "v1")
        self.assertTrue(self._commit(cid1).allow)
        cid2 = self._ready(target, "v2")
        blocked = self.gate.check_write(WriteContext(confirm_id=cid2))
        self.assertFalse(blocked.allow)
        self.assertIn("read", blocked.reason)
        self.gate.note_read(str(target))
        self.assertTrue(self.gate.check_write(WriteContext(confirm_id=cid2)).allow)

if __name__ == "__main__":
    unittest.main()
