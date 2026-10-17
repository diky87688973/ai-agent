# -*- coding: utf-8 -*-
"""验收：质量门控闭环 headless 演示（三场景 / id 制）。

场景：① 正向——真实文件走通完整四步（预览 → 确认 → 凭 ID 提交 → 重读）；
② 反向——违规被拒（无预览直提交 / 未确认提交 / 重复提交 / 跨文件未 review）；
③ 回灌——写坏语法 → 诊断红灯回灌 → 修复转绿。
覆盖：预览强制 / 红灯限面 / 跨文件 review / 连改重读 / ID 绑定 / 写中记账 / review 语义 / 报告 / 本地检查。
运行：python scripts/acceptance_mvp2.py（全部通过退出码 0）
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.app import build_app  # noqa: E402
from agent.core.tool_call import ToolResult  # noqa: E402


class Acceptance:
    """headless 验收运行器：经管道唯一入口驱动，逐项打印 PASS/FAIL。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.app = build_app()
        self.seq = 0
        self.failures: list = []

    # ── 基础操作 ────────────────────────────────────────────

    def call(self, name: str, arguments: dict) -> ToolResult:
        self.seq += 1
        return self.app.execute_tool(
            name, arguments, call_id=f"c{self.seq}"
        )

    def preview(self, path: Path, content: str) -> ToolResult:
        return self.call("write_file", {"path": str(path), "content": content})

    def commit(self, confirm_id: str) -> ToolResult:
        return self.call("commit_write", {"confirm_id": confirm_id})

    def ready(self, path: Path, content: str) -> str:
        """预览 + 确认（四步前两步），返回 confirm_id。"""
        r = self.preview(path, content)
        cid = str(r.data.get("confirm_id") or "") if (r.ok and isinstance(r.data, dict)) else ""
        if cid:
            self.app.gate.confirm(cid)
        return cid

    def norm(self, path: Path) -> str:
        return str(path).replace("\\", "/")

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
        print("\n场景① 正向：真实文件走通完整四步（预览 → 确认 → 凭 ID 提交 → 重读）")
        f = self.root / "s1.txt"
        r = self.preview(f, "hello")
        self.check(" 预览：不落盘且发出 confirm_id", r.ok and not f.exists() and bool(r.data.get("confirm_id")))
        cid = str(r.data.get("confirm_id") or "")
        self.app.gate.confirm(cid)
        r = self.commit(cid)
        self.check("提交：落盘且内容正确", r.ok and f.read_text(encoding="utf-8") == "hello")
        self.check(" 报告回灌（green）", r.data.get("host_quality", {}).get("overall") == "green")
        self.check(" 记账：进入待重读", self.norm(f) in self.app.gate.needs_reread)
        r = self.call("read_file", {"path": str(f)})
        self.check(" 重读：标记清除", r.ok and self.norm(f) not in self.app.gate.needs_reread)
        self.app.gate.review_done()
        self.check(" 写后 review 关闭", not self.app.gate.pending_review)

    # ── 场景 ② 反向 ────────────────────────────────────────

    def scenario_2(self) -> None:
        print("\n场景② 反向：违规被拒（无预览 / 未确认 / 重复提交 / 跨文件未 review）")
        a = self.root / "s2a.txt"
        b = self.root / "s2b.txt"
        c = self.root / "s2c.txt"
        r = self.commit("forged-id-0000")
        self.check("违规① 无预览直提交被拒", (not r.ok) and ("无效" in r.error) and (not c.exists()))
        rp = self.preview(c, "v1")
        cid_c = str(rp.data.get("confirm_id") or "")
        r = self.commit(cid_c)
        self.check("附检：预览后未确认提交被拒",
                   (not r.ok)
                   and ("未解锁" in r.error)
                   and ("review_conclusion" in r.error))
        self.app.gate.confirm(cid_c)
        r = self.commit(cid_c)
        self.check("附检：确认后凭 ID 提交成功", r.ok and c.read_text(encoding="utf-8") == "v1")
        r = self.commit(cid_c)
        self.check("违规② 同一 ID 重复提交被拒（一次性）", (not r.ok) and ("无效" in r.error))
        self.app.gate.review_done()
        cid_a = self.ready(a, "va")
        r = self.commit(cid_a)
        self.check("对照：首文件提交成功", r.ok)
        cid_b = self.ready(b, "vb")
        r = self.commit(cid_b)
        self.check("违规③ 写后未 review 跨文件被拒", (not r.ok) and ("review" in r.error))
        self.app.gate.review_done()
        r = self.commit(cid_b)
        self.check("review_done 后跨文件放行", r.ok)
        self.app.gate.review_done()

    # ── 场景 ③ 回灌 ────────────────────────────────────────

    def scenario_3(self) -> None:
        print("\n场景③ 回灌：写坏语法 → 诊断红灯 → 修复转绿")
        f = self.root / "s3.py"
        cid = self.ready(f, "def broken(:\n")
        r = self.commit(cid)
        self.check(" 写后诊断红灯回灌（red）", r.ok and r.data.get("host_quality", {}).get("overall") == "red")
        self.check("红灯状态置位", self.app.gate.pending_diagnose_red)
        self.call("read_file", {"path": str(f)})
        good = "def fixed():\n    return 1\n"
        cid = self.ready(f, good)
        r = self.commit(cid)
        self.check(" 修复提交后转绿（green）", r.ok and r.data.get("host_quality", {}).get("overall") == "green")
        self.check("红灯解除", not self.app.gate.pending_diagnose_red)

    # ── 运行 ───────────────────────────────────────────────

    def run(self) -> int:
        print("=== MVP-2 验收：质量门控闭环（headless / id 制）===")
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
