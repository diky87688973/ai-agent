# -*- coding: utf-8 -*-
"""写路径工具测试：replace_in_file / apply_patch / read_write / delete_file / file_ops / file_undo。

经管道唯一入口驱动（与 test_write_gate 同风格）：预览 → 确认 → 凭 ID 提交 → 重读。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.app import build_app  # noqa: E402
from agent.core.tool_call import ToolCallRequest  # noqa: E402
from agent.mechanisms.file_safety import FileBackups  # noqa: E402


def _patch(old: str, new: str, header_old: str = "-1,3", header_new: str = "+1,3") -> str:
    """构造单 hunk 补丁（3 行上下文）。"""
    return "\n".join(
        [
            "--- a/p.txt",
            "+++ b/p.txt",
            f"@@ {header_old} {header_new} @@",
            " a",
            f"-{old}",
            f"+{new}",
            " c",
        ]
    ) + "\n"

class WritePathToolsTest(unittest.TestCase):
    """六工具：正向提交 / 违规拒绝 / 门控联动。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.app = build_app(
            backup_root=self.root / "bk",
            recycle_root=self.root / "rc",
        )
        self._seq = 0

    # ── helpers ──────────────────────────────────────────

    def _call(self, name: str, arguments: dict):
        self._seq += 1
        call = ToolCallRequest(call_id=f"c{self._seq}", name=name, arguments=arguments)
        return self.app.pipeline.execute(self.app.registry, call, None)

    def _ready(self, name: str, arguments: dict) -> str:
        r = self._call(name, arguments)
        self.assertTrue(r.ok, msg=str(r.error))
        cid = str(r.data.get("confirm_id") or "")
        self.assertTrue(cid)
        self.app.gate.confirm(cid)
        return cid

    def _commit(self, cid: str):
        return self._call("commit_write", {"confirm_id": cid})

    def _norm(self, path: Path) -> str:
        return str(path).replace("\\", "/")

    def _write_file(self, f: Path, content: str) -> object:
        cid = self._ready("write_file", {"path": str(f), "content": content})
        return self._commit(cid)

    def _backup_meta(self, f: Path, index: int = 0) -> dict:
        """备份的 metadata（列表是**新→旧**，`index=0` 即最近一次）。"""
        import json

        versions = FileBackups(self.root / "bk").list_for(f)
        self.assertTrue(versions, msg=f"没有备份：{f}")
        mid = str(versions[index]["mod_id"])
        group, ver = mid.split(":")
        meta_fp = self.root / "bk" / group / ver / "metadata.json"
        return json.loads(meta_fp.read_text(encoding="utf-8"))

    # ── 备份留档：mode 与 diff ────────────────────────────

    def test_backup_records_what_the_write_changed(self) -> None:
        """写盘触发的备份要记下「这一版改了什么」。

        旧内容与新内容在提交时都在手边，diff 是顺手就能留下的；
        不留的话事后只能看到一份孤立的旧内容，看不出改动。
        """
        f = self.root / "b1.txt"
        f.write_text("旧内容\n共两行\n", encoding="utf-8")
        r = self._write_file(f, "新内容\n共两行\n")
        self.assertTrue(r.ok, msg=str(r.error))
        meta = self._backup_meta(f)
        self.assertEqual(meta["mode"], "write")
        self.assertIn("-旧内容", meta["diff_text"])
        self.assertIn("+新内容", meta["diff_text"])
        self.assertIn("@@", meta["diff_text"])

    def test_backup_mode_reflects_the_replace_mode(self) -> None:
        """`replace_in_file` 的 mode 要区分字面替换与行区间替换，不能一律写成工具名。"""
        f = self.root / "b2.txt"
        f.write_text("alpha beta\n", encoding="utf-8")
        cid = self._ready("replace_in_file",
                          {"path": str(f), "old_text": "beta", "new_text": "BETA"})
        self.assertTrue(self._commit(cid).ok)
        self.assertEqual(self._backup_meta(f)["mode"], "literal")

    def test_backup_of_a_patch_records_the_patch_diff(self) -> None:
        f = self.root / "p.txt"
        f.write_text("a\nold\nc\n", encoding="utf-8")
        cid = self._ready("apply_patch",
                          {"path": str(self.root), "patch_text": _patch("old", "new")})
        r = self._commit(cid)
        self.assertTrue(r.ok, msg=str(r.error))
        meta = self._backup_meta(f)
        self.assertEqual(meta["mode"], "patch")
        self.assertIn("-old", meta["diff_text"])
        self.assertIn("+new", meta["diff_text"])

    def test_undo_backup_records_what_the_rollback_undid(self) -> None:
        """回滚前的留档也要记 diff —— 否则"回滚"这一动作本身无迹可查。"""
        f = self.root / "b3.txt"
        f.write_text("v1\n", encoding="utf-8")
        self.assertTrue(self._write_file(f, "v2\n").ok)
        # 质量门控要求写盘前先读一遍当前内容
        self.assertTrue(self._call("read_file", {"path": str(f)}).ok)
        versions = FileBackups(self.root / "bk").list_for(f)
        self.assertEqual(len(versions), 1)
        first = str(versions[0]["mod_id"])
        cid = self._ready("file_undo", {"action": "undo", "mod_id": first, "path": str(f)})
        r = self._commit(cid)
        self.assertTrue(r.ok, msg=str(r.error))
        self.assertEqual(f.read_text(encoding="utf-8"), "v1\n")
        # 版本目录名精确到秒，写盘与回滚可能落在同一秒 —— 那时按名字排序分不出先后，
        # 所以按 mode 找，不按位置取
        modes = {self._backup_meta(f, index=i)["mode"]
                 for i in range(len(FileBackups(self.root / "bk").list_for(f)))}
        self.assertEqual(modes, {"write", "undo"})
        for i in range(2):
            meta = self._backup_meta(f, index=i)
            if meta["mode"] == "undo":
                self.assertIn("-v2", meta["diff_text"])
                self.assertIn("+v1", meta["diff_text"])

    # ── replace_in_file ──────────────────────────────────

    def test_replace_preview_no_write(self) -> None:

        f = self.root / "r1.txt"
        f.write_text("hello world", encoding="utf-8")
        r = self._call("replace_in_file", {"path": str(f), "old_text": "world", "new_text": "earth"})
        self.assertTrue(r.ok, msg=str(r.error))
        self.assertEqual(r.data["matches"], 1)
        self.assertEqual(f.read_text(encoding="utf-8"), "hello world")

    def test_replace_commit_applies(self) -> None:
        f = self.root / "r2.txt"
        f.write_text("hello world", encoding="utf-8")
        cid = self._ready("replace_in_file", {"path": str(f), "old_text": "world", "new_text": "earth"})
        r = self._commit(cid)
        self.assertTrue(r.ok, msg=str(r.error))
        self.assertEqual(f.read_text(encoding="utf-8"), "hello earth")
        self.assertIn(self._norm(f), self.app.gate.needs_reread)
        self._call("read_file", {"path": str(f)})
        self.assertNotIn(self._norm(f), self.app.gate.needs_reread)

    def test_replace_expected_mismatch_rejected(self) -> None:
        f = self.root / "r3.txt"
        f.write_text("a a", encoding="utf-8")
        r = self._call(
            "replace_in_file",
            {"path": str(f), "old_text": "a", "new_text": "b", "expected_replacements": 3},
        )
        self.assertFalse(r.ok)
        self.assertIn("命中数", str(r.error))

    def test_replace_old_text_not_found(self) -> None:
        f = self.root / "r4.txt"
        f.write_text("abc", encoding="utf-8")
        r = self._call("replace_in_file", {"path": str(f), "old_text": "zzz", "new_text": "y"})
        self.assertFalse(r.ok)
        self.assertIn("未找到", str(r.error))

    def test_replace_line_mode(self) -> None:
        f = self.root / "r5.txt"
        f.write_text("L1\nL2\nL3\nL4", encoding="utf-8")
        cid = self._ready("replace_in_file", {"path": str(f), "line_start": 2, "line_end": 3, "new_text": "X"})
        r = self._commit(cid)
        self.assertTrue(r.ok, msg=str(r.error))
        self.assertEqual(f.read_text(encoding="utf-8"), "L1\nX\nL4")

    def test_replace_stale_file_rejected(self) -> None:

        f = self.root / "r6.txt"
        f.write_text("v1 v1", encoding="utf-8")
        cid = self._ready("replace_in_file", {"path": str(f), "old_text": "v1", "new_text": "v2"})
        f.write_text("zzz", encoding="utf-8")  # 预览后外部改动
        r = self._commit(cid)
        self.assertFalse(r.ok)
        self.assertEqual(f.read_text(encoding="utf-8"), "zzz")

    # ── apply_patch ──────────────────────────────────────

    def test_patch_preview_stats_no_write(self) -> None:
        f = self.root / "p.txt"
        f.write_text("a\nb\nc\n", encoding="utf-8")
        r = self._call("apply_patch", {"path": str(self.root), "patch_text": _patch("b", "B")})
        self.assertTrue(r.ok, msg=str(r.error))
        self.assertEqual(r.data["files"][0]["additions"], 1)
        self.assertEqual(r.data["files"][0]["deletions"], 1)
        self.assertEqual(f.read_text(encoding="utf-8"), "a\nb\nc\n")

    def test_patch_commit_applies(self) -> None:
        f = self.root / "p.txt"
        f.write_text("a\nb\nc\n", encoding="utf-8")
        cid = self._ready("apply_patch", {"path": str(self.root), "patch_text": _patch("b", "B")})
        r = self._commit(cid)
        self.assertTrue(r.ok, msg=str(r.error))
        self.assertEqual(f.read_text(encoding="utf-8"), "a\nB\nc\n")

    def test_patch_context_mismatch_rejected(self) -> None:
        f = self.root / "p.txt"
        f.write_text("a\nx\nc\n", encoding="utf-8")
        r = self._call("apply_patch", {"path": str(self.root), "patch_text": _patch("b", "B")})
        self.assertFalse(r.ok)
        self.assertIn("hunk", str(r.error))

    def test_patch_outside_root_rejected(self) -> None:
        outside = self.root / "out.txt"
        outside.write_text("a\nb\nc\n", encoding="utf-8")
        proj = self.root / "proj"
        proj.mkdir()
        patch = "\n".join(
            ["--- a/../out.txt", "+++ b/../out.txt", "@@ -1,3 +1,3 @@", " a", "-b", "+B", " c"]
        ) + "\n"
        r = self._call("apply_patch", {"path": str(proj), "patch_text": patch})
        self.assertFalse(r.ok)
        self.assertIn("越出根目录", str(r.error))

    def test_patch_missing_target_rejected(self) -> None:
        r = self._call("apply_patch", {"path": str(self.root), "patch_text": _patch("b", "B")})
        self.assertFalse(r.ok)
        self.assertIn("不存在", str(r.error))

    def test_patch_second_needs_review(self) -> None:

        f = self.root / "p.txt"
        f.write_text("a\nb\nc\n", encoding="utf-8")
        cid1 = self._ready("apply_patch", {"path": str(self.root), "patch_text": _patch("b", "B")})
        r1 = self._commit(cid1)
        self.assertTrue(r1.ok, msg=str(r1.error))
        self.assertEqual(f.read_text(encoding="utf-8"), "a\nB\nc\n")
        cid2 = self._ready("apply_patch", {"path": str(self.root), "patch_text": _patch("B", "BB")})
        r2 = self._commit(cid2)
        self.assertFalse(r2.ok)
        self.assertIn("review", str(r2.error))
        self.app.gate.review_done()
        r3 = self._commit(cid2)
        self.assertTrue(r3.ok, msg=str(r3.error))
        self.assertEqual(f.read_text(encoding="utf-8"), "a\nBB\nc\n")

    # ── read_write ───────────────────────────────────────

    def test_read_write_slice_and_backup(self) -> None:

        src = self.root / "src.txt"
        src.write_text("a\nb\nc", encoding="utf-8")
        dst = self.root / "dst.txt"
        cid1 = self._ready(
            "read_write",
            {"source_path": str(src), "dest_path": str(dst), "line_start": 2, "line_end": 3},
        )
        r1 = self._commit(cid1)
        self.assertTrue(r1.ok, msg=str(r1.error))
        self.assertEqual(dst.read_text(encoding="utf-8"), "b\nc")
        self.assertEqual(r1.data["mod_id"], "")
        self._call("read_file", {"path": str(dst)})
        cid2 = self._ready("read_write", {"source_path": str(src), "dest_path": str(dst)})
        r2 = self._commit(cid2)
        self.assertTrue(r2.ok, msg=str(r2.error))
        self.assertTrue(r2.data.get("mod_id"))
        versions = FileBackups(self.root / "bk").list_for(dst)
        self.assertEqual(len(versions), 1)

    # ── delete_file / file_ops ───────────────────────────

    def test_delete_file_to_recycle(self) -> None:
        f = self.root / "d.txt"
        f.write_text("bye", encoding="utf-8")
        r = self._call("delete_file", {"path": str(f)})
        self.assertTrue(r.ok)
        self.assertEqual(Path(str(r.data.get("recycle_dir"))), self.root / "rc")
        self.assertTrue(f.exists())  # 预览不落盘
        cid = self._ready("delete_file", {"path": str(f)})
        r2 = self._commit(cid)
        self.assertTrue(r2.ok, msg=str(r2.error))
        self.assertFalse(f.exists())
        moved = Path(str(r2.data["moved_to"]))
        self.assertTrue(moved.is_file())
        self.assertEqual(moved.read_text(encoding="utf-8"), "bye")

    def test_delete_file_dir_rejected(self) -> None:
        d = self.root / "sub"
        d.mkdir()
        r = self._call("delete_file", {"path": str(d)})
        self.assertFalse(r.ok)
        self.assertIn("file_ops", str(r.error))

    def test_file_ops_copy_and_overwrite_refused(self) -> None:
        src = self.root / "s.txt"
        src.write_text("data", encoding="utf-8")
        dst = self.root / "t.txt"
        cid = self._ready("file_ops", {"action": "copy", "source": str(src), "dest": str(dst)})
        r = self._commit(cid)
        self.assertTrue(r.ok, msg=str(r.error))
        self.assertEqual(dst.read_text(encoding="utf-8"), "data")
        r2 = self._call("file_ops", {"action": "copy", "source": str(src), "dest": str(dst)})
        self.assertFalse(r2.ok)
        self.assertIn("拒绝覆盖", str(r2.error))

    # ── file_undo ────────────────────────────────────────

    def test_file_undo_restore_and_list(self) -> None:
        f = self.root / "u.txt"
        f.write_text("v1", encoding="utf-8")
        r0 = self._write_file(f, "v2")
        self.assertTrue(r0.ok, msg=str(r0.error))
        mid = str(r0.data.get("mod_id") or "")
        self.assertTrue(mid)
        self._call("read_file", {"path": str(f)})
        lst = self._call("file_undo", {"action": "list", "path": str(f)})
        self.assertTrue(lst.ok)
        self.assertFalse(lst.data.get("needs_commit", True))
        self.assertGreaterEqual(lst.data["count"], 1)
        cid = self._ready("file_undo", {"action": "undo", "path": str(f), "mod_id": mid})
        r = self._commit(cid)
        self.assertTrue(r.ok, msg=str(r.error))
        self.assertEqual(f.read_text(encoding="utf-8"), "v1")
        self.assertEqual(r.data["restored_from"], mid)

    def test_file_undo_requires_path(self) -> None:
        r = self._call("file_undo", {"action": "undo", "mod_id": "nope"})
        self.assertFalse(r.ok)
        self.assertIn("mod_id 与 path", str(r.error))

    # ── 门控联动 ─────────────────────────────────────────

    def test_cross_file_review_block(self) -> None:

        a = self.root / "ca.txt"
        b = self.root / "cb.txt"
        r1 = self._write_file(a, "A")
        self.assertTrue(r1.ok, msg=str(r1.error))
        cid_b = self._ready("write_file", {"path": str(b), "content": "B"})
        r2 = self._commit(cid_b)
        self.assertFalse(r2.ok)
        self.assertIn("review", str(r2.error))
        self.app.gate.review_done()
        r3 = self._commit(cid_b)
        self.assertTrue(r3.ok, msg=str(r3.error))
        self.assertEqual(b.read_text(encoding="utf-8"), "B")

    def test_reread_block_before_second_write(self) -> None:

        a = self.root / "ra.txt"
        a.write_text("v1", encoding="utf-8")
        cid1 = self._ready("replace_in_file", {"path": str(a), "old_text": "v1", "new_text": "v2"})
        r1 = self._commit(cid1)
        self.assertTrue(r1.ok, msg=str(r1.error))
        cid2 = self._ready("replace_in_file", {"path": str(a), "old_text": "v2", "new_text": "v3"})
        r2 = self._commit(cid2)
        self.assertFalse(r2.ok)
        self.assertIn("read", str(r2.error))
        self._call("read_file", {"path": str(a)})
        r3 = self._commit(cid2)
        self.assertTrue(r3.ok, msg=str(r3.error))
        self.assertEqual(a.read_text(encoding="utf-8"), "v3")

if __name__ == "__main__":
    unittest.main()
