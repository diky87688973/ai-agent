# -*- coding: utf-8 -*-
"""内核骨架原型：**委托式模块链 + 宿主循环**。

这份文件是**内核形状的可执行定义**——用最小代码把架构落成能跑的东西：

    主体（宿主循环）只发号施令；能力全部委托给模块；
    模块只经**有类型的端口**读写上下文；数据（流式）经**事件**跨模块传播；
    控制流经**返回值**回到宿主；循环是宿主的职责，续行信号是模块给的。

四条设计约束与它们在此的落点：

1. **接口编程**：`ModuleBase.execute(ports)` 是唯一行为面；不同规则接口 = 不同模块。
   `Ports` 是个只读集合，模块**不能** `ports.xxx = ...`，只能调端口方法。
2. **控制流走返回值**：`Outcome` 三态（`CONTINUE` / `HALT` / `SUSPEND`），
   它**不携带数据**；模型的增量、用量、进度都经 `ports.emit(...)`。
3. **数据流走事件**：`Ports.emit(event)` 是模块唯一的产出通道；宿主转交 `sink`。
4. **端口锁行为**：`ContextPort` 的子接口就是"规则接口"，实现类给逻辑；
   模块依赖接口而非上下文字段名，所以换实现不影响别人。

**本趟 / 续行**：宿主反复跑**整条模块链**，直到某一趟**没有任何模块请求续行**。
宿主因此**永远不需要知道"模型有没有要求调工具"**——它只知道"有没有人让我再来一趟"。
"""
from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence

# ══════════════════════════════════════════════════════════════════════
# 一、控制流：返回值三态（**不携带数据**）
# ══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Outcome:
    """模块执行结果：只是**控制信号**。

    - `OK`：我这一步做完了，**不要求**下一趟
    - `NEXT`：我这一步做完了，但**请宿主再跑一趟**（"我还需要下一轮"）
    - `HALT`：立刻停止整条链（错误、或被拒绝）
    - `SUSPEND`：挂起，把控制权交回宿主（等外部输入），恢复后从本模块继续

    数据通道是 `Ports.emit`，不从返回值里带。

    "成功"与"请求续行"分成两个值：两者合一为"继续"时，每条链都会永远要求续行，
    宿主只能跑到护栏上限（`max_passes`）。能不能"就这样结束"与"要不要下一轮"是两件事。
    """

    status: str
    reason: str = ""

    @staticmethod
    def ok() -> "Outcome":
        """做完了，不要求下一趟。"""
        return Outcome("ok")

    @staticmethod
    def next() -> "Outcome":
        """做完了，但请宿主再跑一趟。"""
        return Outcome("next")

    @staticmethod
    def halt(reason: str = "") -> "Outcome":
        return Outcome("halt", reason)

    @staticmethod
    def suspend(reason: str = "") -> "Outcome":
        return Outcome("suspend", reason)

OK = Outcome("ok")

# ══════════════════════════════════════════════════════════════════════
# 数据流：事件（**不可变事实**，跨模块传播的唯一数据通道）
# ══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Event:
    type: str
    data: Dict[str, Any] = field(default_factory=dict)

# ══════════════════════════════════════════════════════════════════════
# 端口：模块操作上下文的**唯一**通路（接口编程）
# ══════════════════════════════════════════════════════════════════════
#
# 模块**不允许**直接碰上下文对象（`ctx.xxx = ...`）。它只能调用端口方法，
# 而端口是**有类型的规则接口**：A 模块读 `HistoryView.read()`，B 模块写
# `ContextStore.write()`——两边依赖同一个接口，而不是某个字段名。
# 换实现时接口不变就换得动。

class ContextStore(Protocol):
    """规则接口：往上下文里写（只有需要写权的模块拿到它）。"""

    def write(self, slot: str, value: Any) -> None: ...

class HistoryView(Protocol):
    """规则接口：读对话历史（只读，模块拿不到写权）。"""

    def read(self) -> List[Dict[str, Any]]: ...

class Ports:
    """一次模块执行能拿到的**全部**能力与数据入口。

    刻意设计成"只能调，不能改"：模块拿不到上下文对象本身，也就无法
    绕过端口去读写字段——这是"接口编程锁定业务行为"的落点。
    """

    def __init__(
        self,
        *,
        emit: Callable[[Event], None],
        history: Optional[HistoryView] = None,
        store: Optional[ContextStore] = None,
        services: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._emit = emit
        self._history = history
        self._store = store
        self._services = dict(services or {})

    # ── 数据出口（唯一）──────────────────────────────────
    def emit(self, type_: str, **data: Any) -> None:
        self._emit(Event(type_, dict(data)))

    # ── 能力入口（按类型，**不按字符串名**）──────────────
    def service(self, name: str) -> Any:
        """取一个已注入的能力；没有则 None。

        这是给"确实无法静态声明"的能力留的口子。能用端口表达的一律走端口
        ——按字符串找能力会把具体机制名写进内核。
        """
        return self._services.get(name)

    @property
    def history(self) -> Optional[HistoryView]:
        return self._history

    @property
    def store(self) -> Optional[ContextStore]:
        return self._store

# ══════════════════════════════════════════════════════════════════════
# 模块：抽象父类锁行为，实现类给逻辑
# ══════════════════════════════════════════════════════════════════════

class ModuleBase:
    """模块抽象父类：**行为面只有 `execute`**。

    子类只实现这个方法；宿主只知道这个方法。换实现 = 换一个子类，
    循环与其它模块零改动。
    """

    #: 诊断用；不参与调度
    name: str = "module"

    def execute(self, ports: Ports) -> Outcome:  # pragma: no cover - 抽象
        raise NotImplementedError

# ══════════════════════════════════════════════════════════════════════
# 宿主：循环在这里
# ══════════════════════════════════════════════════════════════════════

class Host:
    """宿主：只做"分派 + 循环"，**不理解任何模块的语义**。

    它不知道什么是压缩、什么是模型、什么是工具；它只知道三件事：
    怎么调一个模块、结果三态各是什么意思、以及"这一趟有没有人要我再来一趟"。
    """

    def __init__(self, modules: Sequence[ModuleBase], sink: Callable[[Event], None]) -> None:
        self._modules = list(modules)
        self._sink = sink
        self.max_passes = 8            # 护栏：防止模块永远要求续行（等价于步数上限）
        self.passes = 0
        self.suspended: Optional[Dict[str, Any]] = None

    def run(self, *, services: Optional[Dict[str, Any]] = None,
            history: Optional[HistoryView] = None,
            store: Optional[ContextStore] = None) -> str:
        """反复跑整条链，直到没有人要求续行。返回结束原因。"""
        while self.passes < self.max_passes:
            self.passes += 1
            wants_another = False
            for module in self._modules:
                ports = Ports(emit=self._sink, history=history, store=store, services=services)
                outcome = module.execute(ports)
                if outcome.status == "halt":
                    return "halted"
                if outcome.status == "suspend":
                    # 挂起：把"恢复点"记下来，控制权交回宿主。
                    # 恢复时从**这个模块**继续，不是从链头重跑。
                    self.suspended = {
                        "module": module.name,
                        "reason": outcome.reason,
                        "resume_at": self._modules.index(module),
                    }
                    return "suspended"
                if outcome.status == "next":
                    wants_another = True
            if not wants_another:
                return "done"
        return "max_passes"

# ══════════════════════════════════════════════════════════════════════
# 具体模块：只经端口拿数据；续行意图由**收尾模块**（工具）给出
# ══════════════════════════════════════════════════════════════════════

class CompressModule(ModuleBase):
    """压缩模块：只读历史，决定要不要压。**从不要求续行**。"""

    name = "compress"

    def __init__(self, limit: int = 3) -> None:
        self.limit = limit
        self.compressed_once = False

    def execute(self, ports: Ports) -> Outcome:
        history = ports.history.read() if ports.history is not None else []
        if len(history) > self.limit and not self.compressed_once:
            self.compressed_once = True
            ports.emit("context_compacted", dropped=len(history) - self.limit)
        return Outcome.ok()          # 压缩从不要求续行

class ModelModuleBase(ModuleBase):
    """模型模块的**规则接口**（供替换的实现类继承）。

    两个实现：一个真的"流式产出"，一个是脚本替身。宿主与其它模块对二者无感——
    这就是可替换性的判据。
    """

    name = "model"

class StreamingModelModule(ModelModuleBase):
    """真形态：增量经事件出去，返回值只是控制信号。"""

    def __init__(self, script: List[str]) -> None:
        self._script = list(script)

    def execute(self, ports: Ports) -> Outcome:
        for chunk in self._script:
            ports.emit("assistant_delta", text=chunk)      # 数据走事件
        ports.emit("usage", prompt_tokens=10, completion_tokens=5)
        if ports.store is not None:
            ports.store.write("last_text", "".join(self._script))
        return Outcome.ok()          # 控制流走返回值（数据已走事件）

class ScriptedModelModule(ModelModuleBase):
    """另一种实现（替身）：一次性给全文，不分片。"""

    name = "model"

    def __init__(self, text: str) -> None:
        self._text = text

    def execute(self, ports: Ports) -> Outcome:
        ports.emit("model_message", content=self._text)
        return Outcome.ok()

class ToolModule(ModuleBase):
    """工具模块 = **收尾模块**：由它给出"让宿主是否继续循环"的结果。

    它自己知道"模型还要不要调工具"（那是工具的语义），宿主不知道。
    """

    name = "tool"

    def __init__(self, rounds: int) -> None:
        # rounds>1 表示"还要再来一趟"；最后一趟为 1
        self.rounds = rounds
        self.calls = 0

    def execute(self, ports: Ports) -> Outcome:
        self.calls += 1
        ports.emit("tool_call", name="echo", round=self.calls)
        ports.emit("tool_result", ok=True)
        if self.calls < self.rounds:
            # 模型还要调工具 → **收尾模块**给出续行信号 → 宿主把整条链再跑一遍
            return Outcome.next()
        return Outcome.ok()          # 不再要求续行：宿主跑完本趟自然收尾

class SuspendToolModule(ModuleBase):
    """需要外部作答的模块：返回 `SUSPEND` 交回控制权（挂起）。"""

    name = "tool"

    def __init__(self) -> None:
        self.asked = False

    def execute(self, ports: Ports) -> Outcome:
        self.asked = True
        ports.emit("turn_awaiting_user", title="选一个")
        return Outcome.suspend("等用户作答")

# ══════════════════════════════════════════════════════════════════════
# 三条判据
# ══════════════════════════════════════════════════════════════════════

class _History:
    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self._rows = rows

    def read(self) -> List[Dict[str, Any]]:
        return list(self._rows)

class _Store:
    def __init__(self) -> None:
        self.slots: Dict[str, Any] = {}

    def write(self, slot: str, value: Any) -> None:
        self.slots[slot] = value

class KernelSkeletonTest(unittest.TestCase):
    """骨架是否成立，由这三条判据决定。"""

    def setUp(self) -> None:
        self.events: List[Event] = []
        self.store = _Store()

    def _run(self, modules: Sequence[ModuleBase], history_rows: int = 1) -> Dict[str, Any]:
        host = Host(modules, self.events.append)
        reason = host.run(history=_History([{"role": "user"}] * history_rows),
                          store=self.store)
        return {"reason": reason, "passes": host.passes, "kinds": [e.type for e in self.events]}

    def test_judgement_1_swap_a_module_others_untouched(self) -> None:
        """判据①：换掉模型模块的实现，循环与其它模块**零改动**。"""
        a = self._run([CompressModule(), StreamingModelModule(["你", "好"]), ToolModule(1)])
        self.events.clear()
        b = self._run([CompressModule(), ScriptedModelModule("你好"), ToolModule(1)])
        # 循环的迭代次数一致，压缩与工具模块完全没被改过
        self.assertEqual(a["passes"], b["passes"])
        # 差别只体现在"模型模块自己选择怎么发事件"
        self.assertIn("assistant_delta", a["kinds"])
        self.assertIn("model_message", b["kinds"])

    def test_judgement_2_the_chain_can_ask_for_another_pass(self) -> None:
        """判据②：能表达"再来一趟"——收尾模块（工具）给续行信号，宿主重跑整条链。"""
        r = self._run([CompressModule(), StreamingModelModule(["x"]), ToolModule(3)])
        self.assertEqual(r["reason"], "done")
        self.assertEqual(r["passes"], 3, msg="工具模块要求 3 趟，宿主就该跑 3 趟")
        self.assertEqual(r["kinds"].count("tool_call"), 3)
        self.assertEqual(r["kinds"].count("assistant_delta"), 3, msg="每趟都要重新调模型")

    def test_judgement_3_suspend_returns_control_without_blocking(self) -> None:
        """判据③：挂起 = 交回控制权（返回 SUSPEND），不是阻塞等待。"""
        r = self._run([CompressModule(), StreamingModelModule(["x"]), SuspendToolModule()])
        self.assertEqual(r["reason"], "suspended")
        self.assertIn("turn_awaiting_user", r["kinds"])

    def test_host_knows_nothing_about_models_or_tools(self) -> None:
        """宿主不理解任何模块语义：换一套完全不同的模块，宿主代码不动。"""
        class _Noop(ModuleBase):
            name = "noop"

            def execute(self, ports: Ports) -> Outcome:
                ports.emit("whatever", n=1)
                return Outcome.ok()

        r = self._run([_Noop(), _Noop()])
        self.assertEqual(r["reason"], "done")
        self.assertEqual(r["passes"], 1)

    def test_halt_stops_the_whole_chain_immediately(self) -> None:
        """阻断：立刻退出（后续模块不再执行，也不再跑下一趟）。"""
        ran: List[str] = []

        class _Boom(ModuleBase):
            name = "boom"

            def execute(self, ports: Ports) -> Outcome:
                ran.append("boom")
                return Outcome.halt("被拒绝")

        class _After(ModuleBase):
            name = "after"

            def execute(self, ports: Ports) -> Outcome:
                ran.append("after")
                return Outcome.ok()

        r = self._run([_Boom(), _After()])
        self.assertEqual(r["reason"], "halted")
        self.assertEqual(ran, ["boom"], msg="阻断后不该再执行后续模块")

    def test_data_never_rides_on_the_return_value(self) -> None:
        """数据只走事件与端口：`Outcome` 里没有承载业务数据的字段。"""
        self._run([CompressModule(), StreamingModelModule(["你", "好"]), ToolModule(1)])
        # 只声明控制信号，不声明数据
        self.assertEqual(list(Outcome.__dataclass_fields__), ["status", "reason"])
        self.assertEqual(
            sorted({Outcome.ok().status, Outcome.next().status, Outcome.halt().status,
                    Outcome.suspend().status}),
            ["halt", "next", "ok", "suspend"],
            msg="控制信号必须是四态",
        )
        self.assertEqual(self.store.slots.get("last_text"), "你好",
                         msg="模型正文经**端口**写进上下文，没有混进返回值")
        self.assertTrue(all(isinstance(e, Event) for e in self.events))

    def test_ports_expose_no_raw_context_object(self) -> None:
        """端口锁行为：模块拿不到上下文对象，只能调端口方法。"""
        seen: Dict[str, Any] = {}

        class _Peek(ModuleBase):
            name = "peek"

            def execute(self, ports: Ports) -> Outcome:
                seen["has_history"] = ports.history is not None
                seen["has_store"] = ports.store is not None
                # 模块能看到的**公开面**：只有方法，没有任何可写数据字段
                seen["writable"] = [
                    k for k, v in vars(ports).items()
                    if not k.startswith("_") and not callable(v)
                ]
                return Outcome.ok()

        self._run([_Peek()])
        self.assertEqual(seen["writable"], [],
                         msg="Ports 不该有可写的公开字段——模块只能调方法")
        self.assertTrue(seen["has_history"] and seen["has_store"])

if __name__ == "__main__":
    unittest.main()
