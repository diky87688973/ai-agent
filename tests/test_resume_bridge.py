# -*- coding: utf-8 -*-
"""挂起是终态、恢复是新一轮、衔接靠事实（含"重启后恢复"）。

要证明的三件事：
  ① 挂起后宿主循环已退出（无内存游标）；恢复是新一轮循环，不是回到旧循环。
  ② 衔接靠事实：挂起与外部结果都落盘；工具模块在新一轮里从上下文看到
     "已解决但未回灌"的调用，回灌成一次普通的 `tool_result` 并要求续行。
  ③ 重启后仍能恢复：丢掉宿主与全部模块对象，只从事实重建，恢复照样成立。
"""
from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Protocol, Sequence

# 控制流四态

@dataclass(frozen=True)
class Outcome:
    status: str
    reason: str = ""

    @staticmethod
    def ok() -> "Outcome":
        return Outcome("ok")

    @staticmethod
    def next() -> "Outcome":
        return Outcome("next")

    @staticmethod
    def halt(reason: str = "") -> "Outcome":
        return Outcome("halt", reason)

    @staticmethod
    def suspend(reason: str = "") -> "Outcome":
        return Outcome("suspend", reason)

@dataclass(frozen=True)
class Event:
    type: str
    data: Dict[str, Any] = field(default_factory=dict)

# 端口：一次模块执行能拿到的全部入口（只读集合，无可写字段）

class FactStore(Protocol):
    """规则接口：事实源（落盘）。挂起与恢复都经它，所以重启不失忆。"""

    def append(self, type_: str, **data: Any) -> str: ...
    def scan(self, type_: str) -> List[Dict[str, Any]]: ...

class Ports:
    def __init__(self, *, emit: Callable[[Event], None], facts: FactStore) -> None:
        self._emit = emit
        self._facts = facts

    def emit(self, type_: str, **data: Any) -> None:
        self._emit(Event(type_, dict(data)))

    @property
    def facts(self) -> FactStore:
        return self._facts

# 模块与宿主

class ModuleBase:
    name = "module"

    def execute(self, ports: Ports) -> Outcome:  # pragma: no cover
        raise NotImplementedError

class Host:
    """宿主：只遍历、读四态、看"这趟有没有人要求续行"。不保存任何挂起游标。"""

    def __init__(self, modules: Sequence[ModuleBase], sink: Callable[[Event], None]) -> None:
        self._modules = list(modules)
        self._sink = sink
        self.max_passes = 8
        self.passes = 0

    def run(self, facts: FactStore) -> str:
        while self.passes < self.max_passes:
            self.passes += 1
            wants_another = False
            for module in self._modules:
                outcome = module.execute(Ports(emit=self._sink, facts=facts))
                if outcome.status == "halt":
                    return "halted"
                if outcome.status == "suspend":
                    # 终态：直接退出。不留游标——恢复时另起一轮。
                    return "suspended"
                if outcome.status == "next":
                    wants_another = True
            if not wants_another:
                return "done"
        return "max_passes"

# 具体模块

class ModelModule(ModuleBase):
    """模型模块：上下文里有未消费的新事实（新用户输入 / 新工具结果）才调模型。"""

    name = "model"

    def __init__(self, replies: List[str]) -> None:
        self._replies = list(replies)
        self.calls = 0

    def execute(self, ports: Ports) -> Outcome:
        pending = ports.facts.scan("_pending_for_model")
        if not pending:
            return Outcome.ok()          # 没有新东西就不打扰模型
        for row in pending:
            ports.facts.append("_consumed", token=row["token"])
        text = self._replies.pop(0) if self._replies else "（无更多回复）"
        self.calls += 1
        ports.emit("assistant_delta", text=text)
        return Outcome.ok()

class ToolModule(ModuleBase):
    """工具模块 = 收尾模块。两个职责：

    ① 处理模型这轮请求的工具调用；
    ② 回灌已解决但还没交回模型的外部结果（用户确认走这条）。

    它不认识"确认"——它只知道"某个挂起的调用现在有结果了"。
    """

    name = "tool"

    def __init__(self, *, need_input_on_first_call: bool) -> None:
        self.need_input = need_input_on_first_call
        self.resumed: List[str] = []

    def execute(self, ports: Ports) -> Outcome:
        # ── ② 回灌：先看有没有"已解决但未回灌"的挂起调用 ──
        suspended = {r["call_id"]: r for r in ports.facts.scan("tool_suspended")}
        resolved = {r["call_id"]: r for r in ports.facts.scan("extern_result")}
        delivered = {r["call_id"] for r in ports.facts.scan("tool_result")}
        for call_id, res in resolved.items():
            if call_id in suspended and call_id not in delivered:
                ports.emit("tool_result", call_id=call_id, ok=True, payload=res["payload"])
                ports.facts.append("tool_result", call_id=call_id, ok=True)
                ports.facts.append("_pending_for_model", token=f"resume-{call_id}")
                self.resumed.append(call_id)
                return Outcome.next()    # 给模型留了新东西 → 宿主再跑一趟

        # ── ① 若首轮需要外部输入，且还没请求过 ──
        if self.need_input and not suspended:
            self.need_input = False
            call_id = "call-1"
            ports.emit("tool_suspended", call_id=call_id, question="选一个")
            ports.facts.append("tool_suspended", call_id=call_id, question="选一个")
            return Outcome.suspend("等用户作答")
        return Outcome.ok()

class InputModule(ModuleBase):
    """输入模块：有新用户输入时，把它标成"给模型的新事实"。"""

    name = "input"

    def __init__(self, text: str = "") -> None:
        self._text = text

    def execute(self, ports: Ports) -> Outcome:
        if self._text:
            ports.facts.append("_pending_for_model", token="user-input")
            ports.emit("input_claimed", content=self._text)
            self._text = ""
        return Outcome.ok()

# 事实源替身（进程内；真实实现是落盘）

class _Facts:
    def __init__(self) -> None:
        self.rows: List[Dict[str, Any]] = []

    def append(self, type_: str, **data: Any) -> str:
        self.rows.append({"type": type_, **data})
        return str(len(self.rows))

    def scan(self, type_: str) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.rows if r["type"] == type_]

# 端到端

class ResumeBridgeTest(unittest.TestCase):
    """挂起 → 恢复的衔接。"""

    def setUp(self) -> None:
        self.facts = _Facts()
        self.events: List[Event] = []

    def _modules(self, replies: List[str]) -> List[ModuleBase]:
        return [InputModule(), ModelModule(replies), ToolModule(need_input_on_first_call=True)]

    def test_suspend_is_terminal_and_resume_is_a_new_run(self) -> None:
        """① 挂起即终态；恢复是新一轮宿主循环，不是回到旧循环。"""
        host = Host(self._modules(["我先问你"]), self.events.append)
        self.assertEqual(host.run(self.facts), "suspended")
        first_passes = host.passes
        self.assertTrue(any(e.type == "tool_suspended" for e in self.events))

        # 用户确认 → API 把答案写成事实
        self.facts.append("extern_result", call_id="call-1", payload="甲")

        # 恢复：新建宿主与模块（挂起那趟的循环已退出，没有游标可回）
        resumed_host = Host(self._modules(["收到：甲"]), self.events.append)
        self.assertEqual(resumed_host.run(self.facts), "done")
        self.assertGreater(resumed_host.passes, 0)
        # 两趟运行各自独立：恢复那趟从趟数 0 起算
        self.assertNotEqual(first_passes, 0)

    def test_resume_delivers_the_result_as_an_ordinary_tool_result(self) -> None:
        """② 回灌就是一次普通的 tool_result，没有特殊规则。"""
        Host(self._modules(["问"]), self.events.append).run(self.facts)
        self.facts.append("extern_result", call_id="call-1", payload="甲")

        Host(self._modules(["收到：甲"]), self.events.append).run(self.facts)
        delivered = [e for e in self.events if e.type == "tool_result"]
        self.assertEqual(len(delivered), 1, msg="恰好回灌一次")
        self.assertEqual(delivered[0].data["call_id"], "call-1")
        self.assertEqual(delivered[0].data["payload"], "甲")

    def test_model_sees_the_result_on_the_next_pass(self) -> None:
        """回灌后工具模块返回 `next`，宿主再跑一趟 → 模型才看得到结果。"""
        Host(self._modules(["问"]), self.events.append).run(self.facts)
        self.facts.append("extern_result", call_id="call-1", payload="甲")

        model = ModelModule(["收到：甲"])
        host = Host([InputModule(), model, ToolModule(need_input_on_first_call=False)],
                    self.events.append)
        host.run(self.facts)
        self.assertEqual(model.calls, 1, msg="模型恰好被叫一次：为了消费那个工具结果")

    def test_result_is_not_delivered_twice(self) -> None:
        """回灌不会重复：`tool_result` 已存在就不再发（同一调用只交一次）。"""
        Host(self._modules(["问"]), self.events.append).run(self.facts)
        self.facts.append("extern_result", call_id="call-1", payload="甲")
        Host(self._modules(["收到"]), self.events.append).run(self.facts)
        n = len([e for e in self.events if e.type == "tool_result"])

        Host(self._modules(["再来"]), self.events.append).run(self.facts)
        self.assertEqual(len([e for e in self.events if e.type == "tool_result"]), n,
                         msg="已回灌过的调用不得再交一次")

    def test_recovers_after_restart(self) -> None:
        """③ 重启后仍能恢复：丢掉宿主与全部模块对象，只从事实重建。

        恢复只依赖事实源：丢掉宿主与全部模块对象后，仍能从事实重建出恢复流程。
        """
        Host(self._modules(["问"]), self.events.append).run(self.facts)
        # 模拟重启：宿主、模块、事件缓冲全部丢弃；只留事实
        del_host = None
        restarted_events: List[Event] = []
        self.facts.append("extern_result", call_id="call-1", payload="乙")

        model = ModelModule(["收到：乙"])
        host = Host([InputModule(), model, ToolModule(need_input_on_first_call=False)],
                    restarted_events.append)
        self.assertEqual(host.run(self.facts), "done")
        delivered = [e for e in restarted_events if e.type == "tool_result"]
        self.assertEqual(len(delivered), 1)
        self.assertEqual(delivered[0].data["payload"], "乙")
        self.assertEqual(model.calls, 1)

    def test_host_holds_no_suspend_state(self) -> None:
        """宿主不保存挂起游标：它的实例字段里没有"停在哪"这类信息。"""
        host = Host(self._modules(["问"]), self.events.append)
        host.run(self.facts)
        fields = {k for k in vars(host) if not k.startswith("__")}
        self.assertEqual(fields, {"_modules", "_sink", "max_passes", "passes"},
                         msg="宿主只该有模块表、出口、护栏与趟数——挂起状态归事实源")

if __name__ == "__main__":
    unittest.main()
