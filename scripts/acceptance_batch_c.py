# -*- coding: utf-8 -*-
"""验收：任务与目标五工具（run_type / todo_list / user_confirm / task_sleep / goal）headless 演示。

场景：① 模式与门控链路——查询切换 → Execute 缺清单提交被拒 → 建清单放行 →
      Plan 提交 / 命令 / 代码执行被拒 → 切回 auto 同一 ID 放行；
② todo 生命周期——全动作正向 + 越界拒绝 + 落盘；
③ 确认与任务信封——两段式确认 / 休眠与自主边界与截断 / 无会话作用域拒绝。
运行：python scripts/acceptance_batch_c.py（全部通过退出码 0）
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.app import build_app  # noqa: E402
from agent.core.tool_call import ToolCallRequest, ToolResult  # noqa: E402
from agent.mechanisms.live_state import LiveState  # noqa: E402

CID = "acceptance-c-01"


class Acceptance:
    """headless 验收运行器：经管道唯一入口驱动，逐项打印 PASS/FAIL。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.state = LiveState(storage_dir=root / "todos")
        self.app = build_app(
            backup_root=root / "bk",
            recycle_root=root / "rc",
            live_state=self.state,
        )
        self.seq = 0
        self.failures: list = []

    @property
    def gate(self):
        """驱动会话的门控（写盘门控每会话独占；脚本以 CID 驱动全链路）。"""
        return self.app.gate_for(CID)

    # ── 基础操作 ────────────────────────────────────────────

    def call(self, name: str, arguments: dict = None, cid: str = CID) -> ToolResult:
        self.seq += 1
        call = ToolCallRequest(call_id=f"c{self.seq}", name=name, arguments=arguments or {})
        ctx = SimpleNamespace(conversation_id=cid) if cid else None
        return self.app.pipeline.execute(self.app.registry, call, ctx)

    def ready(self, name: str, arguments: dict):
        """预览 + 确认（四步前两步）；返回 (预览结果, confirm_id)。"""
        r = self.call(name, arguments)
        cid = str(r.data.get("confirm_id") or "") if (r.ok and isinstance(r.data, dict)) else ""
        if cid:
            self.gate.confirm(cid)
        return r, cid

    def commit(self, confirm_id: str) -> ToolResult:
        return self.call("commit_write", {"confirm_id": confirm_id})

    def check(self, label: str, cond: object, detail: str = "") -> None:
        status = "PASS" if cond else "FAIL"
        line = f"  [{status}] {label}"
        if detail and not cond:
            line += f" — {detail}"
        print(line)
        if not cond:
            self.failures.append(label)

    # ── 场景 ① 模式与门控链路 ──────────────────────────────

    def scenario_1(self) -> None:
        print("\n场景① 模式与门控链路")
        r = self.call("run_type", {})
        self.check("默认查询 auto", r.ok and r.data == {"run_type": "auto", "action": "query"}, str(r.data))
        r = self.call("run_type", {"run_type": "execute"})
        self.check("切换 execute", r.ok and r.data == {"run_type": "execute", "action": "switch"}, str(r.data))

        f1 = self.root / "a.txt"
        r, cid = self.ready("write_file", {"path": str(f1), "content": "alpha"})
        self.check("Execute 预览登记 confirm_id", r.ok and bool(cid))
        r = self.commit(cid)
        self.check("Execute 缺清单提交被拒（ModeConflict）", (not r.ok) and ("ModeConflict" in str(r.error)), str(r.error))

        r = self.call("todo_list", {"action": "create", "items": ["步骤一"]})
        self.check("建非空清单", r.ok and len(r.data["items"]) == 1, str(r.data))
        r = self.commit(cid)
        self.check("建清单后提交放行", r.ok and f1.read_text(encoding="utf-8") == "alpha", str(r.error))
        self.call("read_file", {"path": str(f1)})
        self.gate.review_done()

        self.call("run_type", {"run_type": "plan"})
        f2 = self.root / "b.txt"
        r, cid2 = self.ready("write_file", {"path": str(f2), "content": "beta"})
        self.check("Plan 下预览仍放行（不写盘）", r.ok and bool(cid2) and (not f2.exists()))
        r = self.commit(cid2)
        self.check("Plan 提交被拒（ModeConflict）", (not r.ok) and ("ModeConflict" in str(r.error)), str(r.error))
        r = self.call("run_command", {"command": "echo hi"})
        self.check("Plan 命令被拒（ModeConflict）", (not r.ok) and ("ModeConflict" in str(r.error)), str(r.error))
        r = self.call("python_inline", {"code": "print(1)"})
        self.check("Plan 代码执行被拒（ModeConflict）", (not r.ok) and ("ModeConflict" in str(r.error)), str(r.error))

        r = self.call("run_type", {"run_type": "auto"})
        self.check("切回 auto", r.ok and r.data["run_type"] == "auto", str(r.data))
        r = self.commit(cid2)
        self.check("auto 后同一 ID 提交放行（快照未消费）", r.ok and f2.read_text(encoding="utf-8") == "beta", str(r.error))
        self.call("read_file", {"path": str(f2)})
        self.gate.review_done()
        r = self.call("run_command", {"command": "echo hi"})
        self.check("auto 命令放行", r.ok and r.data.get("exit_code") == 0, str(r.data))

    # ── 场景 ② todo 生命周期 ───────────────────────────────

    def scenario_2(self) -> None:
        print("\n场景② todo 生命周期")
        r = self.call("todo_list", {"action": "create", "items": ["a", {"text": "b", "done": True}]})
        lid = str(r.data.get("list_id") or "") if r.ok else ""
        self.check("create：list_id + 归一化", r.ok and len(lid) == 12 and r.data["items"][1]["done"] is True, str(r.data))
        self.check("清单已落盘", (self.root / "todos" / f"{CID}.json").is_file())
        r = self.call("todo_list", {"action": "check", "indices": [0]})
        self.check("check", r.ok and r.data["items"][0]["done"] is True and r.data["checked"] == [0], str(r.data))
        r = self.call("todo_list", {"action": "uncheck", "indices": 0})
        self.check("uncheck（单 int 形式）", r.ok and r.data["items"][0]["done"] is False, str(r.data))
        r = self.call("todo_list", {"action": "add_item", "text": "c", "item_index": 0})
        self.check("add_item 插入首位", r.ok and [i["text"] for i in r.data["items"]] == ["c", "a", "b"], str(r.data))
        r = self.call("todo_list", {"action": "remove_item", "item_index": 0})
        self.check("remove_item", r.ok and [i["text"] for i in r.data["items"]] == ["a", "b"], str(r.data))
        r = self.call("todo_list", {"action": "replace_item", "item_index": 1, "text": "B"})
        self.check("replace_item", r.ok and r.data["items"][1]["text"] == "B", str(r.data))
        r = self.call("todo_list", {"action": "collapse"})
        self.check("collapse 翻转", r.ok and r.data["collapsed"] is True, str(r.data))
        r = self.call("todo_list", {"action": "check", "indices": [9]})
        self.check("越界整体拒绝", (not r.ok) and ("越界" in str(r.error)), str(r.error))
        r = self.call("todo_list", {"action": "query"})
        self.check("query 返回条目", r.ok and len(r.data) == 2, str(r.data))
        r = self.call("todo_list", {"action": "close"})
        self.check("close", r.ok and r.data == {"close": True}, str(r.data))
        r = self.call("todo_list", {"action": "query"})
        self.check("close 后 query 返回 None", r.ok and r.data is None, str(r.data))

    # ── 场景 ③ 确认与任务信封 ──────────────────────────────

    def scenario_3(self) -> None:
        print("\n场景③ 确认与任务信封")
        r = self.call("user_confirm", {"title": "继续吗？", "confirms": ["继续", "停止"]})
        self.check(
            "待确认信封（ok=False + data + 类型）",
            (not r.ok) and str(r.error).startswith("UserConfirmRequired") and r.data.get("title") == "继续吗？" and r.data.get("confirms") == ["继续", "停止"],
            f"{r.error} | {r.data}",
        )
        r = self.call("user_confirm", {"confirm": "继续"})
        self.check("confirm 回填", r.ok and r.data == {"confirm": "继续"}, str(r.data))
        r = self.call("task_sleep", {"seconds": 30, "reminder": "r" * 600})
        self.check("task_sleep：截断 500 + 状态记录", r.ok and len(r.data["reminder"]) == 500 and self.state.get_sleep(CID)["seconds"] == 30, str(r.data))
        r = self.call("task_sleep", {"seconds": 0})
        self.check("task_sleep：0 拒绝", (not r.ok) and ("1~86400" in str(r.error)), str(r.error))
        r = self.call("goal", {"action": "get"})
        self.check("goal：初始无目标", r.ok and r.data["goal"] is None, str(r.data))
        r = self.call("goal", {"action": "create", "text": "把 README 补全"})
        self.check("goal：创建 + 触发文案", r.ok and r.data["goal"]["status"] == "active"
                   and self.state.goal_trigger_text(CID) == "把 README 补全", str(r.data))
        r = self.call("goal", {"action": "pause"})
        self.check("goal：暂停后不再触发", r.ok and self.state.goal_trigger_text(CID) == "", str(r.data))
        r = self.call("goal", {"action": "resume"})
        self.check("goal：恢复触发", r.ok and self.state.goal_trigger_text(CID) == "把 README 补全", str(r.data))
        r = self.call("goal", {"action": "delete"})
        self.check("goal：删除", r.ok and r.data["deleted"] is True, str(r.data))
        r = self.call("run_type", {}, cid=None)
        self.check("无会话作用域拒绝", (not r.ok) and ("conversation_id" in str(r.error)), str(r.error))

    # ── 运行 ───────────────────────────────────────────────

    def run(self) -> int:
        print("=== 验收：任务与自主五工具（headless）===")
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
