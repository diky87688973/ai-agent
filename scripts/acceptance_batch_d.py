# -*- coding: utf-8 -*-
"""验收：会话协作五工具（session_send / session_multisend / session_broadcast / session_create / session_list）headless 演示。

场景：① 建网与列表——批量创建 / 别名 / 命名 / 标签 / 状态派生；
② 互发与触发——直启目标回合、"忙"窗口排队、解锁后队列抽干；
③ 群发与广播——部分失败信封 / tag+role 筛选 / 校验令牌。
运行：python scripts/acceptance_batch_d.py（全部通过退出码 0）
"""
from __future__ import annotations

import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.app import build_app  # noqa: E402
from agent.core.model_call import StreamDelta  # noqa: E402
from agent.core.tool_call import ToolCallRequest, ToolResult  # noqa: E402
from agent.mechanisms.mesh import MeshState  # noqa: E402

CID_DRIVER = "accept-driver1"


class _GatedProbe:
    """首个请求挂起的记录型假模型：制造"忙"窗口，验证排队与抽干。"""

    def __init__(self) -> None:
        self.seen = []
        self.gate = threading.Event()
        self._count = 0
        self._lock = threading.Lock()

    def stream(self, request):
        with self._lock:
            self.seen.append([dict(m) for m in request.messages])
            self._count += 1
            idx = self._count
        if idx == 1:
            self.gate.wait(timeout=15)
        yield StreamDelta(kind="text", text=f"处理完成（第 {idx} 回合）")


class Acceptance:
    """headless 验收运行器：经管道唯一入口驱动，逐项打印 PASS/FAIL。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.mesh = MeshState(storage_dir=root / "mesh")
        self.provider = _GatedProbe()
        self.app = build_app(provider=self.provider, mesh=self.mesh)
        self.seq = 0
        self.failures: list = []
        self.worker = ""
        self.worker2 = ""
        self.captain = ""

    def call(self, name, arguments=None, cid=CID_DRIVER) -> ToolResult:
        self.seq += 1
        call = ToolCallRequest(call_id=f"c{self.seq}", name=name, arguments=arguments or {})
        ctx = SimpleNamespace(conversation_id=cid) if cid else None
        return self.app.pipeline.execute(self.app.registry, call, ctx)

    def check(self, label, cond, detail=""):
        status = "PASS" if cond else "FAIL"
        line = f"  [{status}] {label}"
        if detail and not cond:
            line += f" — {detail}"
        print(line)
        if not cond:
            self.failures.append(label)

    def wait_until(self, cond, timeout: float = 15.0, interval: float = 0.05) -> bool:
        """轮询等条件成立。跨线程推进的中间态（如队列抽干）不能用一次判定。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if cond():
                return True
            time.sleep(interval)
        return bool(cond())

    # ── 场景 ① 建网与列表 ──────────────────────────────

    def scenario_1(self):
        print("\n场景① 建网与列表")
        r = self.call("session_create", {"count": 2, "name_prefix": "队员", "role": "worker", "tags": "grp"})
        self.check(
            "批量创建：prefix+序号 / 别名映射",
            r.ok and [a["name"] for a in r.data["agents"]] == ["队员1", "队员2"] and r.data["agents"][0]["role"] == "全栈开发",
            str(r.data),
        )
        self.worker = r.data["agents"][0]["cid"]
        self.worker2 = r.data["agents"][1]["cid"]
        r2 = self.call("session_create", {"name": "队长", "role": "QA", "tags": ["grp"]})
        self.check(
            "单条创建：命名 / 标签 / 注册",
            r2.ok and r2.data["agents"][0]["name"] == "队长" and "【Agent 身份】" in r2.data["meta"]["system"],
            str(r2.data),
        )
        self.captain = r2.data["agents"][0]["cid"]
        r3 = self.call("session_list", {})
        names = [a["name"] for a in r3.data["agents"]]
        self.check(
            "列表：数量 / 状态 idle / queueSize",
            r3.ok and r3.data["count"] == 3 and names == ["队员1", "队员2", "队长"] and all(a["status"] == "idle" and a["queueSize"] == 0 for a in r3.data["agents"]),
            str(r3.data),
        )
        self.check("注册表持久化文件", (self.root / "mesh" / "agents.json").is_file())

    # ── 场景 ② 互发与触发 ──────────────────────────────

    def scenario_2(self):
        print("\n场景② 互发与触发")
        r1 = self.call("session_send", {"target_id": self.worker, "message": "第一条：请开工", "requires_reply": True})
        self.check("直启：目标空闲 → 触发回合（run_id）", r1.ok and r1.data["queued"] is False and bool(r1.data["run_id"]), str(r1.data))
        self.check("运行中：活跃集登记", self.mesh.is_running(self.worker))
        # 占位成功还没进模型：一趟开始先收集注入源，这期间后到的消息
        # 会被收件箱并进当前回合。排队窗口从首个请求挂起之后起算。
        entered = self.wait_until(lambda: len(self.provider.seen) == 1, timeout=15)
        self.check(
            "忙窗口：首个请求已挂起",
            entered,
            f"已见请求 {len(self.provider.seen)} 次（期望 1）",
        )
        r2 = self.call("session_send", {"target_id": self.worker, "message": "第二条：追加任务", "requires_reply": False})
        self.check("忙时排队：queued + 计数", r2.ok and r2.data["queued"] is True and r2.data["queued_count"] == 1, str(r2.data))
        row = [a for a in self.call("session_list", {}).data["agents"] if a["cid"] == self.worker][0]
        self.check("列表派生状态：running / queueSize", row["status"] == "running" and row["queueSize"] == 1, str(row))
        self.provider.gate.set()
        # 抽干是"排队的那轮随后被取走执行"，与"当前轮结束"不是同一时刻：慢机器上
        # `wait_idle` 先返回、第二轮的请求还没发出。这里等条件成立，不再一次判定。
        drained = self.wait_until(lambda: len(self.provider.seen) == 2, timeout=15)
        self.check(
            "队列抽干：两回合顺序执行后归闲",
            drained and self.app.runner.wait_idle(self.worker, timeout=15)
            and not self.mesh.is_running(self.worker),
            f"已见请求 {len(self.provider.seen)} 次（期望 2）",
        )
        self.check(
            "身份块注入（system prompt 通道）",
            any("【Agent 身份】" in str(m.get("content", "")) and m.get("role") == "system" for m in self.provider.seen[0]),
        )
        self.check(
            "包装与元数据抵达目标回合",
            any("第一条" in str(m.get("content", "")) and str(m.get("content", "")).startswith("[from=") for m in self.provider.seen[0])
            and any("第二条" in str(m.get("content", "")) for m in self.provider.seen[1]),
        )

    # ── 场景 ③ 群发与广播 ──────────────────────────────

    def scenario_3(self):
        print("\n场景③ 群发与广播")
        r1 = self.call("session_multisend", {"target_ids": [self.captain, "ghost0000000"], "message": "点名", "requires_reply": True})
        self.check(
            "多播：部分失败（partial / skipped / count）",
            r1.ok and r1.data["partial"] is True and r1.data["count"] == 1 and "target_not_found" in r1.data["skipped"][0]["error"],
            str(r1.data),
        )
        r2 = self.call("session_broadcast", {"tag": "grp", "message": "全体注意", "requires_reply": False, "exclude_self": False})
        self.check("广播：tag 筛选 / 排除自身开关", r2.ok and r2.data["count"] == 3, str(r2.data))
        r3 = self.call("session_broadcast", {"message": "x", "requires_reply": False})
        self.check("广播：tag 必填拒绝", (not r3.ok) and ("missing_tag" in r3.error), str(r3.error))
        r4 = self.call("session_send", {"target_id": self.worker, "message": "x"})
        self.check("发送：requires_reply 必填拒绝", (not r4.ok) and ("missing_requires_reply" in r4.error), str(r4.error))
        r5 = self.call("session_send", {"target_id": "ghost0000000", "message": "x", "requires_reply": True})
        self.check("发送：目标不存在拒绝", (not r5.ok) and ("target_not_found" in r5.error), str(r5.error))
        r6 = self.call("session_multisend", {"target_ids": ["ghost0000000"], "message": "x", "requires_reply": True})
        self.check("多播：全部失败信封（数据随附）", (not r6.ok) and ("all_targets_failed" in r6.error) and r6.data["count"] == 0, str(r6.error))
        ok_idle = all(self.app.runner.wait_idle(cid, timeout=15) for cid in (self.captain, self.worker2, self.worker))
        self.check("收尾：全部会话归闲", ok_idle)

    # ── 运行 ───────────────────────────────────────────

    def run(self) -> int:
        print("=== 验收：会话协作五工具（headless）===")
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
        acc = Acceptance(Path(tmp))
        try:
            return acc.run()
        finally:
            acc.provider.gate.set()  # 兜底放行，防线程悬挂


if __name__ == "__main__":
    raise SystemExit(main())
