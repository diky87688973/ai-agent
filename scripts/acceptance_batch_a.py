# -*- coding: utf-8 -*-
"""验收：写路径 6 件（replace_in_file / apply_patch / read_write / delete_file / file_ops / file_undo）headless 演示。

场景：① 正向——写路径 6 件工具对真实文件走通完整四步（预览 → 确认 → 凭 ID 提交 → 重读）；
② 反向——违规与校验拒绝（伪 ID / 未确认 / 替换未命中 / 补丁不符 / 越根 / 目录删除 / 覆盖目标）；
③ 门控联动——跨文件 review/ 补丁先 review/ 先读再改/ 预览后文件变化/ 大删除红灯。
运行：python scripts/acceptance_batch_a.py（全部通过退出码 0）
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.app import build_app  # noqa: E402
from agent.core.tool_call import ToolResult  # noqa: E402


def _patch(old: str, new: str) -> str:
    """构造单 hunk 补丁（3 行上下文，目标 p.txt）。"""
    return "\n".join(
        [
            "--- a/p.txt",
            "+++ b/p.txt",
            "@@ -1,3 +1,3 @@",
            " a",
            f"-{old}",
            f"+{new}",
            " c",
        ]
    ) + "\n"


class Acceptance:
    """headless 验收运行器：经管道唯一入口驱动，逐项打印 PASS/FAIL。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.app = build_app(
            backup_root=root / "bk",
            recycle_root=root / "rc",
        )
        self.seq = 0
        self.failures: list = []

    # ── 基础操作 ────────────────────────────────────────────

    def call(self, name: str, arguments: dict) -> ToolResult:
        self.seq += 1
        return self.app.execute_tool(
            name, arguments, call_id=f"c{self.seq}"
        )

    def ready(self, name: str, arguments: dict):
        """预览 + 确认（四步前两步）；返回 (预览结果, confirm_id)。"""
        r = self.call(name, arguments)
        cid = str(r.data.get("confirm_id") or "") if (r.ok and isinstance(r.data, dict)) else ""
        if cid:
            self.app.gate.confirm(cid)
        return r, cid

    def commit(self, confirm_id: str) -> ToolResult:
        return self.call("commit_write", {"confirm_id": confirm_id})

    def check(self, label: str, cond: object, detail: str = "") -> None:
        status = "PASS" if cond else "FAIL"
        line = f"  [{status}] {label}"
        if detail:
            line += f" — {detail}"
        print(line)
        if not cond:
            self.failures.append(label)

    # ── 场景 ① 正向 ────────────────────────────────────────

    def scenario_1(self) -> None:
        print("\n场景① 正向：写路径 6 件工具走通完整四步（预览 → 确认 → 凭 ID 提交 → 重读）")
        f1 = self.root / "s1.txt"
        f1.write_text("hello world", encoding="utf-8")
        r, cid = self.ready("replace_in_file", {"path": str(f1), "old_text": "world", "new_text": "earth"})
        self.check("replace 预览：不落盘 + 命中 1 处", r.ok and r.data["matches"] == 1 and f1.read_text(encoding="utf-8") == "hello world")
        r = self.commit(cid)
        self.check("replace 提交：替换生效", r.ok and f1.read_text(encoding="utf-8") == "hello earth")
        self.call("read_file", {"path": str(f1)})
        self.app.gate.review_done()

        f2 = self.root / "p.txt"
        f2.write_text("a\nb\nc\n", encoding="utf-8")
        r, cid = self.ready("apply_patch", {"path": str(self.root), "patch_text": _patch("b", "B")})
        self.check("patch 预览：统计 + 不落盘", r.ok and r.data["files"][0]["additions"] == 1 and f2.read_text(encoding="utf-8") == "a\nb\nc\n")
        r = self.commit(cid)
        self.check("patch 提交：补丁生效", r.ok and f2.read_text(encoding="utf-8") == "a\nB\nc\n")
        self.call("read_file", {"path": str(f2)})
        self.app.gate.review_done()

        src = self.root / "src.txt"
        src.write_text("a\nb\nc", encoding="utf-8")
        dst = self.root / "dst.txt"
        r, cid = self.ready("read_write", {"source_path": str(src), "dest_path": str(dst), "line_start": 2, "line_end": 3})
        self.check("read_write 预览：切片不落盘", r.ok and not dst.exists())
        r = self.commit(cid)
        self.check("read_write 提交：片段写入", r.ok and dst.read_text(encoding="utf-8") == "b\nc")
        self.call("read_file", {"path": str(dst)})
        self.app.gate.review_done()

        r, cid = self.ready("read_write", {"source_path": str(src), "dest_path": str(dst)})
        r = self.commit(cid)
        self.check("read_write 覆盖：版本化备份产生 mod_id", r.ok and bool(r.data.get("mod_id")))
        self.call("read_file", {"path": str(dst)})
        self.app.gate.review_done()

        f3 = self.root / "d.txt"
        f3.write_text("bye", encoding="utf-8")
        r, cid = self.ready("delete_file", {"path": str(f3)})
        self.check("delete 预览：文件仍在", r.ok and f3.exists())
        r = self.commit(cid)
        moved = Path(str(r.data.get("moved_to") or ""))
        self.check("delete 提交：移入回收目录（可恢复）", r.ok and (not f3.exists()) and moved.is_file() and moved.read_text(encoding="utf-8") == "bye")
        self.app.gate.review_done()

        f4 = self.root / "f4.txt"
        f4.write_text("data", encoding="utf-8")
        f5 = self.root / "f5.txt"
        r, cid = self.ready("file_ops", {"action": "copy", "source": str(f4), "dest": str(f5)})
        r = self.commit(cid)
        self.check("file_ops 复制：目标内容一致", r.ok and f5.read_text(encoding="utf-8") == "data")
        self.app.gate.review_done()

        u = self.root / "u.txt"
        u.write_text("v1", encoding="utf-8")
        r, cid = self.ready("write_file", {"path": str(u), "content": "v2"})
        r = self.commit(cid)
        mid = str(r.data.get("mod_id") or "")
        self.check("write_file 覆盖：产生备份 mod_id", r.ok and bool(mid))
        self.call("read_file", {"path": str(u)})
        lst = self.call("file_undo", {"action": "list", "path": str(u)})
        self.check("file_undo 列表：只读（needs_commit=False）+ 有历史", lst.ok and lst.data.get("needs_commit") is False and lst.data["count"] >= 1)
        r, cid = self.ready("file_undo", {"action": "undo", "path": str(u), "mod_id": mid})
        r = self.commit(cid)
        self.check("file_undo 回滚：内容还原（回滚前再备份）", r.ok and u.read_text(encoding="utf-8") == "v1" and r.data.get("restored_from") == mid)
        self.call("read_file", {"path": str(u)})
        self.app.gate.review_done()

    # ── 场景 ② 反向 ────────────────────────────────────────

    def scenario_2(self) -> None:
        print("\n场景② 反向：违规与校验拒绝")
        r = self.commit("forged-id-0000")
        self.check("伪 ID 提交被拒", (not r.ok) and ("无效" in str(r.error)))

        f1 = self.root / "s1.txt"
        r = self.call("replace_in_file", {"path": str(f1), "old_text": "zzz", "new_text": "x"})
        self.check("replace：old_text 未命中被拒", (not r.ok) and ("未找到" in str(r.error)))

        r = self.call("apply_patch", {"path": str(self.root), "patch_text": _patch("zzz", "x")})
        self.check("patch：上下文不符被拒", (not r.ok) and ("hunk" in str(r.error)))

        outside = self.root / "outside.txt"
        outside.write_text("a\nb\nc\n", encoding="utf-8")
        proj = self.root / "proj"
        proj.mkdir()
        patch = "\n".join(["--- a/../outside.txt", "+++ b/../outside.txt", "@@ -1,3 +1,3 @@", " a", "-b", "+B", " c"]) + "\n"
        r = self.call("apply_patch", {"path": str(proj), "patch_text": patch})
        self.check("patch：目标越出根被拒", (not r.ok) and ("越出根目录" in str(r.error)))

        sub = self.root / "sub"
        sub.mkdir()
        r = self.call("delete_file", {"path": str(sub)})
        self.check("delete：目录被拒（提示 file_ops）", (not r.ok) and ("file_ops" in str(r.error)))

        f4 = self.root / "f4.txt"
        f5 = self.root / "f5.txt"
        # 同内容再 copy → 幂等已应用（不必 commit）
        r = self.call("file_ops", {"action": "copy", "source": str(f4), "dest": str(f5)})
        self.check(
            "file_ops：同内容再复制为 already_applied",
            r.ok and r.data.get("status") == "already_applied"
            and not r.data.get("needs_commit", True),
        )
        # 内容不同且默认 on_exists=error → 拒绝覆盖
        f4.write_text("changed", encoding="utf-8")
        r = self.call("file_ops", {"action": "copy", "source": str(f4), "dest": str(f5)})
        self.check("file_ops：覆盖已存在目标被拒", (not r.ok) and ("拒绝覆盖" in str(r.error)))

        c7 = self.root / "c7.txt"
        rp = self.call("write_file", {"path": str(c7), "content": "x"})
        cid = str(rp.data.get("confirm_id") or "")
        r = self.commit(cid)
        self.check("未确认提交被拒",
                   (not r.ok)
                   and ("未解锁" in str(r.error))
                   # 拒绝文案必须点明解锁入口是 review_conclusion，
                   # 只说"未解锁"会让模型去发起 user_confirm
                   and ("review_conclusion" in str(r.error)))

        r, cid = self.ready("replace_in_file", {"path": str(f1), "old_text": "hello earth", "new_text": "x"})
        f1.write_text("mutated", encoding="utf-8")  # 模拟预览之后文件被外部改动
        r = self.commit(cid)
        self.check(" 预览后文件变化被拒 + 不改写", (not r.ok) and ("未找到" in str(r.error)) and f1.read_text(encoding="utf-8") == "mutated")

    # ── 场景 ③ 门控联动 ────────────────────────────────────

    def scenario_3(self) -> None:
        print("\n场景③ 门控联动：cross-file review / 连改重读 / 补丁通道 / 大删除红灯")
        g1 = self.root / "g1.txt"
        g2 = self.root / "g2.txt"
        r, cid = self.ready("write_file", {"path": str(g1), "content": "A"})
        r = self.commit(cid)
        self.check("首文件提交成功", r.ok)
        r, cid = self.ready("write_file", {"path": str(g2), "content": "B"})
        r = self.commit(cid)
        self.check(" 跨文件未 review 被拒", (not r.ok) and ("review" in str(r.error)))
        self.app.gate.review_done()
        r = self.commit(cid)
        ok_after = r.ok
        self.call("read_file", {"path": str(g2)})
        self.app.gate.review_done()
        self.check(" review 后放行", ok_after and g2.read_text(encoding="utf-8") == "B")

        a1 = self.root / "a1.txt"
        r, cid = self.ready("write_file", {"path": str(a1), "content": "L1"})
        r = self.commit(cid)
        self.check("a1 初写成功", r.ok)
        r, cid = self.ready("replace_in_file", {"path": str(a1), "old_text": "L1", "new_text": "L2"})
        r = self.commit(cid)
        self.check(" 连改未重读被拒", (not r.ok) and ("read" in str(r.error)))
        self.call("read_file", {"path": str(a1)})
        r = self.commit(cid)
        self.check(" 重读后放行", r.ok and a1.read_text(encoding="utf-8") == "L2")
        self.call("read_file", {"path": str(a1)})
        self.app.gate.review_done()

        p = self.root / "p.txt"
        r, cid1 = self.ready("apply_patch", {"path": str(self.root), "patch_text": _patch("B", "BB")})
        r = self.commit(cid1)
        self.check("补丁①提交成功", r.ok)
        r, cid2 = self.ready("apply_patch", {"path": str(self.root), "patch_text": _patch("BB", "BBB")})
        r = self.commit(cid2)
        self.check(" 第二补丁先 review 被拒", (not r.ok) and ("review" in str(r.error)))
        self.app.gate.review_done()
        self.call("read_file", {"path": str(p)})
        r = self.commit(cid2)
        self.check(" review + 重读后放行", r.ok and p.read_text(encoding="utf-8") == "a\nBBB\nc\n")
        self.app.gate.review_done()

        big = self.root / "big.txt"
        big.write_text("\n".join(f"line{i}" for i in range(1, 41)) + "\n", encoding="utf-8")
        r, cid = self.ready("replace_in_file", {"path": str(big), "line_start": 1, "line_end": 40, "new_text": "x"})
        r = self.commit(cid)
        self.check(" 大删除红灯回灌（red）", r.ok and r.data.get("host_quality", {}).get("overall") == "red")
        self.check("红灯状态置位", self.app.gate.pending_diagnose_red)
        self.app.gate.review_done()
        self.check("review 后大删除红灯解除", not self.app.gate.pending_diagnose_red)

    # ── 运行 ───────────────────────────────────────────────

    def run(self) -> int:
        print("=== 验收：写路径 6 件（headless / id 制）===")
        self.scenario_1()
        self.scenario_2()
        self.scenario_3()
        print()
        if self.failures:
            print(f"验收未通过：{len(self.failures)} 项失败")
            for name in self.failures:
                print(f"  - {name}")
            return 1
        print("验收通过：全部检查项 PASS。")
        return 0


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        return Acceptance(Path(tmp)).run()


if __name__ == "__main__":
    raise SystemExit(main())
