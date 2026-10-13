# -*- coding: utf-8 -*-
"""写盘门控桥接测试：四步写盘协议 + 门控在注册制管道下不丢失。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.app import build_app  # noqa: E402
from agent.core.tool_call import ToolCallRequest  # noqa: E402


class WriteGateTest(unittest.TestCase):
    """经管道驱动 write_file（预览）/ commit_write（提交）：四步协议 / 违规拒绝 / 红灯回灌。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.app = build_app()
        self._seq = 0

    # ── helpers ──────────────────────────────────────────

    def _call(self, name: str, arguments: dict):
        """经管道唯一入口驱动一次工具调用。"""
        self._seq += 1
        call = ToolCallRequest(call_id=f"c{self._seq}", name=name, arguments=arguments)
        return self.app.pipeline.execute(self.app.registry, call, None)

    def _preview(self, path: Path, content: str):
        return self._call("write_file", {"path": str(path), "content": content})

    def _commit(self, confirm_id: str):
        return self._call("commit_write", {"confirm_id": confirm_id})

    def _ready(self, path: Path, content: str) -> str:
        """预览 + 确认（四步前两步），返回 confirm_id。"""
        r = self._preview(path, content)
        self.assertTrue(r.ok)
        cid = str(r.data.get("confirm_id") or "")
        self.assertTrue(cid)
        self.app.gate.confirm(cid)
        return cid

    def _norm(self, path: Path) -> str:
        return str(path).replace("\\", "/")

    # ── 正向四步 ─────────────────────────────────────────

    def test_preview_does_not_write(self) -> None:
        """预览：不落盘，返回字节数、存在标记与 confirm_id。"""
        f = self.root / "a.txt"
        r = self._preview(f, "v1")
        self.assertTrue(r.ok)
        self.assertFalse(f.exists())
        self.assertEqual(r.data["bytes"], 2)
        self.assertFalse(r.data["exists"])
        self.assertTrue(r.data["confirm_id"])

    def test_full_four_steps(self) -> None:
        """预览 → 确认 → 凭 ID 提交 → 重读：真实文件走通完整四步。"""
        f = self.root / "b.txt"
        cid = self._ready(f, "v1")
        r = self._commit(cid)
        self.assertTrue(r.ok)
        self.assertEqual(f.read_text(encoding="utf-8"), "v1")
        self.assertIn(self._norm(f), self.app.gate.needs_reread)
        r2 = self._call("read_file", {"path": str(f)})
        self.assertTrue(r2.ok)
        self.assertNotIn(self._norm(f), self.app.gate.needs_reread)

    def test_commit_consumes_id_once(self) -> None:
        """提交凭 ID 且一次性：同一 ID 二次提交被拒。"""
        f = self.root / "b2.txt"
        cid = self._ready(f, "v1")
        self.assertTrue(self._commit(cid).ok)
        again = self._commit(cid)
        self.assertFalse(again.ok)
        self.assertIn("无效", again.error)

    # ── 违规反向场景 ─────────────────────────────────────

    def test_commit_without_preview_rejected(self) -> None:
        """无预览直提交（伪造 ID）：被拒，文件不落盘；不产生记账。"""
        f = self.root / "c.txt"
        r = self._commit("forged-id-0000")
        self.assertFalse(r.ok)
        self.assertIn("无效", r.error)
        self.assertFalse(f.exists())
        self.assertNotIn(self._norm(f), self.app.gate.needs_reread)

    def test_commit_without_confirm_rejected(self) -> None:
        """预览后未确认即提交：被拒；确认后凭同一 ID 提交成功。"""
        f = self.root / "d.txt"
        r = self._preview(f, "v1")
        cid = str(r.data["confirm_id"])
        blocked = self._commit(cid)
        self.assertFalse(blocked.ok)
        # 引导质量：错误文案必须指向 `review_conclusion`
        self.assertIn("未解锁", blocked.error)   # 语义：卡在"预览未解锁"这一关
        self.assertIn("review_conclusion", blocked.error)
        self.assertIn("confirm_id", blocked.error)
        self.assertFalse(f.exists())
        self.app.gate.confirm(cid)
        self.assertTrue(self._commit(cid).ok)
        self.assertEqual(f.read_text(encoding="utf-8"), "v1")

    def test_cross_file_review_gate(self) -> None:
        """写后未 review 跨文件：被拒；review_done 后放行。"""
        a = self.root / "f_a.txt"
        b = self.root / "f_b.txt"
        cid_a = self._ready(a, "va")
        self.assertTrue(self._commit(cid_a).ok)
        cid_b = self._ready(b, "vb")
        blocked = self._commit(cid_b)
        self.assertFalse(blocked.ok)
        self.assertIn("review", blocked.error)
        self.app.gate.review_done()
        self.assertTrue(self._commit(cid_b).ok)

    def test_reread_required_before_second_edit(self) -> None:
        """写后未重读前再次提交：被拒；重读后放行。"""
        f = self.root / "g.txt"
        cid1 = self._ready(f, "v1")
        self.assertTrue(self._commit(cid1).ok)
        cid2 = self._ready(f, "v2")
        blocked = self._commit(cid2)
        self.assertFalse(blocked.ok)
        self.assertIn("先 read", blocked.error)
        self._call("read_file", {"path": str(f)})
        self.assertTrue(self._commit(cid2).ok)
        self.assertEqual(f.read_text(encoding="utf-8"), "v2")

    # ── 红灯回灌与限面 ───────────────────────────────────

    def test_diagnose_red_and_recovery(self) -> None:
        """写坏语法 → 红灯回灌；修复后转绿。"""
        f = self.root / "bad.py"
        cid1 = self._ready(f, "def f(:\n")
        r = self._commit(cid1)
        self.assertTrue(r.ok)
        self.assertEqual(r.data["host_quality"]["overall"], "red")
        self.assertTrue(self.app.gate.pending_diagnose_red)
        self._call("read_file", {"path": str(f)})
        cid2 = self._ready(f, "def f():\n    return 1\n")
        r2 = self._commit(cid2)
        self.assertTrue(r2.ok)
        self.assertEqual(r2.data["host_quality"]["overall"], "green")
        self.assertFalse(self.app.gate.pending_diagnose_red)

    def test_red_light_limits_scope(self) -> None:
        """红灯未清时，改其他文件被拒（限面）。"""
        bad = self.root / "bad2.py"
        other = self.root / "other.txt"
        cid_bad = self._ready(bad, "def g(:\n")
        self.assertTrue(self._commit(cid_bad).ok)
        cid_other = self._ready(other, "t")
        blocked = self._commit(cid_other)
        self.assertFalse(blocked.ok)
        self.assertIn("诊断", blocked.error)
        self.assertFalse(other.exists())

    # ── 边界与接线 ───────────────────────────────────────

    def test_write_missing_path_rejected(self) -> None:
        """缺 path：工具报错经管道结构化回灌。"""
        r = self._call("write_file", {"content": "v1"})
        self.assertFalse(r.ok)
        self.assertIn("缺少 path", r.error)

    def test_write_missing_content_rejected(self) -> None:
        """缺 content：工具报错经管道结构化回灌。"""
        r = self._call("write_file", {"path": str(self.root / "x.txt")})
        self.assertFalse(r.ok)
        self.assertIn("缺少 content", r.error)

    def test_commit_missing_id_rejected(self) -> None:
        """缺 confirm_id：提交被拒。"""
        r = self._call("commit_write", {})
        self.assertFalse(r.ok)
        self.assertIn("confirm_id", r.error)

    def test_commit_creates_parent_dirs(self) -> None:
        """提交：目标父目录不存在时自动创建。"""
        f = self.root / "newdir" / "sub" / "n.txt"
        cid = self._ready(f, "v1")
        r = self._commit(cid)
        self.assertTrue(r.ok)
        self.assertEqual(f.read_text(encoding="utf-8"), "v1")

    def test_large_overwrite_flags_red(self) -> None:
        """提交覆盖既有大文件（大幅缩水）：大删除红灯 + 报告回灌 red。"""
        f = self.root / "big.txt"
        f.write_text("\n".join(f"line {i}" for i in range(1, 41)), encoding="utf-8")
        cid = self._ready(f, "tiny")
        r = self._commit(cid)
        self.assertTrue(r.ok)
        self.assertTrue(self.app.gate.large_delete_flag)
        self.assertEqual(r.data["host_quality"]["overall"], "red")


if __name__ == "__main__":
    unittest.main()
