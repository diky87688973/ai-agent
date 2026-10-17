# -*- coding: utf-8 -*-
"""质量管线测试：写前 gate / 写中 inspect / 写后 feedback 三段。

真实文件（临时目录）驱动。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.mechanisms.quality import WriteContext  # noqa: E402
from tests.gate_fixtures import make_gate  # noqa: E402


class QualityPipelineTest(unittest.TestCase):
    """三段检查与红灯生命周期。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.gate = make_gate()

    def _ready(self, path: Path, content: str = "v", *, tool: str = "write_file") -> str:
        """预览登记 + 确认（四步前两步），返回 confirm_id。"""
        cid = self.gate.register_preview(tool, {"path": str(path), "content": content})
        self.gate.confirm(cid)
        return cid

    def _wc(self, cid: str) -> WriteContext:
        return WriteContext(confirm_id=cid)

    # ── 写前 gate ──────────────────────────────────────────

    def test_path_required(self) -> None:
        """空路径被拒。"""

        cid = self.gate.register_preview("write_file", {"path": "   ", "content": "v"})
        self.gate.confirm(cid)
        decision = self.gate.check_write(self._wc(cid))
        self.assertFalse(decision.allow)

    def test_path_format_equivalent(self) -> None:
        """反斜杠/正斜杠路径等价。"""

        target = self.root / "fmt.txt"
        cid = self._ready(target)
        self.gate.note_committed(str(target))
        self.assertFalse(self.gate.check_write(self._wc(cid)).allow)
        self.gate.note_read(str(target).replace("\\", "/"))
        self.assertTrue(self.gate.check_write(self._wc(cid)).allow)

    def test_intent_evidence_gate(self) -> None:
        """debug 意图下无证据拒写；采证后放行。"""

        target = self.root / "a.py"
        cid = self._ready(target, "v1")
        self.gate.set_intent("debug")
        self.assertFalse(self.gate.check_write(self._wc(cid)).allow)
        self.gate.note_evidence()
        self.assertTrue(self.gate.check_write(self._wc(cid)).allow)

    def test_intent_switch_resets_evidence(self) -> None:
        """切换意图重置证据状态。"""

        self.gate.set_intent("debug")
        self.gate.note_evidence()
        self.assertTrue(self.gate.evidence_ok)
        self.gate.set_intent("troubleshoot")
        self.assertFalse(self.gate.evidence_ok)
        self.gate.set_intent("whatever")
        self.assertEqual(self.gate.intent, "")

    def test_apply_patch_channel(self) -> None:
        """apply_patch：写之前解锁的另一份仍可提交；同一路径写之后才解锁的要先 review。"""

        a = self.root / "pa.txt"
        b = self.root / "pb.txt"
        self._ready(a, "va", tool="apply_patch")
        cid_b = self._ready(b, "vb", tool="apply_patch")
        self.gate.note_committed(str(a), tool="apply_patch")
        sibling = self.gate.check_write(self._wc(cid_b))
        self.assertTrue(sibling.allow, sibling.reason)
        cid_again = self._ready(a, "vb", tool="apply_patch")
        blocked = self.gate.check_write(self._wc(cid_again))
        self.assertFalse(blocked.allow)
        self.assertIn("apply_patch", blocked.reason)
        self.gate.review_done()
        self.gate.note_read(str(a))
        self.assertTrue(self.gate.check_write(self._wc(cid_again)).allow)

    def test_large_diff_blocked(self) -> None:
        """单次替换过大被拒、拆分后放行。"""

        a = self.root / "d.txt"
        big = "line\n" * 90
        cid = self.gate.register_preview("replace_in_file", {"path": str(a), "new_text": big})
        self.gate.confirm(cid)
        blocked = self.gate.check_write(self._wc(cid))
        self.assertFalse(blocked.allow)
        self.assertIn("过大", blocked.reason)
        small = "line\n" * 5
        cid2 = self.gate.register_preview("replace_in_file", {"path": str(a), "new_text": small})
        self.gate.confirm(cid2)
        self.assertTrue(self.gate.check_write(self._wc(cid2)).allow)

    # ── 写中 inspect ───────────────────────────────────────

    def test_large_delete_flag(self) -> None:
        """大删除检测置红灯。"""

        a = self.root / "ld.txt"
        diff = "".join(f"-line{i}\n" for i in range(30)) + "+new\n"
        self.gate.note_committed(str(a), diff_text=diff)
        self.assertTrue(self.gate.large_delete_flag)
        self.assertTrue(self.gate.pending_diagnose_red)

    # ── 写后 feedback ──────────────────────────────────────

    def test_review_clears_large_delete_not_diag(self) -> None:
        """大删除因 review 解除；诊断红灯不解除。"""

        a = self.root / "rv.txt"
        diff = "".join(f"-l{i}\n" for i in range(30))
        self.gate.note_committed(str(a), diff_text=diff)
        self.gate.review_done()
        self.assertFalse(self.gate.large_delete_flag)
        self.assertFalse(self.gate.pending_diagnose_red)
        self.gate._flag_diag_fail("demo")
        self.gate.review_done()
        self.assertTrue(self.gate.pending_diagnose_red)
        self.assertTrue(self.gate.diag_fail_flag)

    def test_post_write_checks_py(self) -> None:
        """Python 文件本地检查：坏→红灯，修复→转绿。"""

        good = self.root / "good.py"
        good.write_text("x = 1\n", encoding="utf-8")
        checks = self.gate.run_post_write_checks(str(good))
        self.assertTrue(checks and all(c["status"] == "pass" for c in checks))
        bad = self.root / "bad.py"
        bad.write_text("def f(:\n", encoding="utf-8")
        checks_bad = self.gate.run_post_write_checks(str(bad))
        self.assertEqual(checks_bad[-1]["status"], "fail")
        self.assertTrue(self.gate.diag_fail_flag)
        bad.write_text("def f():\n    return 1\n", encoding="utf-8")
        checks_fix = self.gate.run_post_write_checks(str(bad))
        self.assertTrue(all(c["status"] == "pass" for c in checks_fix))
        self.assertFalse(self.gate.diag_fail_flag)

    def test_post_write_checks_json(self) -> None:
        """JSON 文件本地检查。"""

        good = self.root / "ok.json"
        good.write_text('{"a": 1}', encoding="utf-8")
        checks = self.gate.run_post_write_checks(str(good))
        self.assertTrue(all(c["status"] == "pass" for c in checks))
        bad = self.root / "bad.json"
        bad.write_text("{a: 1", encoding="utf-8")
        checks_bad = self.gate.run_post_write_checks(str(bad))
        self.assertEqual(checks_bad[-1]["status"], "fail")

    def test_report_structure(self) -> None:
        """质量报告结构。"""

        a = self.root / "rep.py"
        a.write_text("x = 1\n", encoding="utf-8")
        self.gate.note_committed(str(a))
        report = self.gate.build_quality_report(str(a))
        self.assertEqual(report["overall"], "green")
        self.assertTrue(report["checks"])
        self.assertIn(
            "若继续改其他文件，请先做写后复核（review_conclusion）",
            report["required_next_actions"],
        )
        b = self.root / "rep_bad.py"
        b.write_text("def f(:\n", encoding="utf-8")
        report_red = self.gate.build_quality_report(str(b))
        self.assertEqual(report_red["overall"], "red")

    def test_assistant_claim_fixed(self) -> None:
        """无证据声称"已修复"会被拦下。"""

        self.gate.note_assistant_text("问题已修复")
        self.assertFalse(self.gate.claim_fixed_blocked)
        a = self.root / "cl.txt"
        self.gate.note_committed(str(a))
        self.gate.note_assistant_text("问题已修复")
        self.assertTrue(self.gate.claim_fixed_blocked)
        self.gate.review_done()
        self.assertFalse(self.gate.claim_fixed_blocked)

if __name__ == "__main__":
    unittest.main()
