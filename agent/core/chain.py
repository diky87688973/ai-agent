# -*- coding: utf-8 -*-
"""模块链执行器（`run_chain` / `_Pass`）：**一趟**怎么跑。

本文件服务"驱动链的人"（一趟怎么跑、终态怎么收、要不要再跑）；
`module.py` 服务"写模块的人"（我要实现什么）。两处职责不同，分开各自读全。

## `_Pass` 是对象而不是普通函数

`execute` 是生成器（契约见 `module.py` 顶部），所以"跑一趟"必须**边跑边让出事件**
才能保住流式。于是这里只能给一个**可迭代对象**：

    pass_ = run_chain_iter(modules, ports)
    for event in pass_:         # 事件在产出那一刻就让出去
        yield event
    result = pass_.result       # 迭代完读本趟结论

结论**按趟隔离**（存在实例上而不是模块全局）：多个会话可能在不同线程里同时跑，
放全局会互相踩。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, List, Optional, Sequence, Tuple

from agent.core.module import ModuleBase
from agent.core.outcome import Outcome
from agent.core.ports import Ports


@dataclass(frozen=True)
class PassResult:
    """**一趟**模块链的结论：终态（若有）+ 是否有人要求续行。

    两者必须一起报——宿主判"要不要再跑一趟"时，既要看有没有人叫停，
    也要看有没有人要求续行。分成两次调用就会有两个真相。

    （事件不在这里：它们在迭代 `_Pass` 时被**逐个让出**。）
    """

    terminal: Optional[Outcome] = None
    wants_another: bool = False

    @property
    def stopped(self) -> bool:
        return self.terminal is not None


def _require_outcome(module: ModuleBase, outcome: Any) -> None:
    """控制信号必须是 `Outcome`——否则静默错位的代价太大（会被当成"没有终态"）。"""
    if outcome is None:
        raise TypeError(f"{module.describe()} 的 execute 必须 return Outcome，而不是 None")
    if not isinstance(outcome, Outcome):
        raise TypeError(
            f"{module.describe()} 的 execute 必须 return Outcome，"
            f"实际是 {type(outcome).__name__}"
        )


class _Pass:
    """跑一趟模块链：**迭代它得到事件**，迭代完读 `.result` 得到本趟结论。"""

    def __init__(self, modules: Sequence[ModuleBase], ports: Ports) -> None:
        self._modules = list(modules)
        self._ports = ports
        self.result: Optional[PassResult] = None

    def __iter__(self) -> Iterator[Any]:
        # 一趟开始就收集注入源，结束就丢掉。
        # 收集放在模块跑起来之前：这一趟里压缩和模型多次装配，共用这一份。
        # 丢掉放在 finally：收集失败、中途停、抛错、消费方关掉生成器，
        # 都不能把快照留在会话上。
        try:
            self._begin_source_pass()
            wants_another = False
            for module in self._modules:
                it = module.execute(self._ports)
                # 常见写法错误：`execute` 里没有 `yield`，于是它是**普通函数**、
                # 直接返回 `Outcome`。这时 `next(it)` 会给出一个很难懂的
                # `'Outcome' object is not an iterator`——这里换成能照着改的提示。
                if isinstance(it, (Outcome, type(None))):
                    raise TypeError(
                        f"{module.describe()} 的 execute 不是生成器（返回了 "
                        f"{type(it).__name__}）。契约是：**`yield` 事实、`return` 控制信号**；"
                        f"请至少写一个 `yield`（没有事实可产出时写 `if False: yield`）"
                        f"——见 core/module.py 顶部说明。"
                    )
                outcome: Optional[Outcome] = None
                try:
                    while True:
                        yield next(it)              # 立刻转给消费者（流式的关键）
                except StopIteration as stop:
                    outcome = stop.value
                _require_outcome(module, outcome)
                assert isinstance(outcome, Outcome)
                if outcome.is_terminal:
                    self.result = PassResult(terminal=outcome, wants_another=wants_another)
                    return
                if outcome.wants_another_pass:
                    wants_another = True
            self.result = PassResult(terminal=None, wants_another=wants_another)
        finally:
            self._end_source_pass()

    def _source_contexts(self) -> List[Any]:
        """本趟模块持有的上下文，同一份只出现一次。"""
        seen: set = set()
        out: List[Any] = []
        for module in self._modules:
            ctx = getattr(module, "_context", None)
            if ctx is None:
                continue
            key = id(ctx)
            if key in seen:
                continue
            seen.add(key)
            out.append(ctx)
        return out

    def _begin_source_pass(self) -> None:
        """本趟链开始：收集注入源快照。"""
        for ctx in self._source_contexts():
            begin = getattr(ctx, "begin_pass", None)
            if callable(begin):
                begin()

    def _end_source_pass(self) -> None:
        """本趟链结束：丢掉注入源快照。"""
        for ctx in self._source_contexts():
            end = getattr(ctx, "end_pass", None)
            if callable(end):
                end()

    def drain(self) -> PassResult:
        """跑完本趟（丢弃事件），返回结论。非流式场合用。"""
        for _event in self:
            pass
        assert self.result is not None
        return self.result


def run_chain_iter(modules: Sequence[ModuleBase], ports: Ports) -> _Pass:
    """跑**一趟**模块链（流式）：迭代返回值拿到事件，迭代完读 `.result`。"""
    return _Pass(modules, ports)


def run_chain(modules: Sequence[ModuleBase], ports: Ports) -> PassResult:
    """跑**一趟**模块链（非流式）：返回本趟结论，事件被丢弃。"""
    return _Pass(modules, ports).drain()


def step(module: ModuleBase, ports: Ports) -> Tuple[List[Any], Outcome]:
    """跑**一个模块**：返回（产出的事实，控制信号）。

    单模块的窄入口（测试、装配校验用）。流式场合请直接迭代
    `module.execute(ports)` 并把每个 `yield` 出来的事件**立刻**转给消费者。
    """
    events: List[Any] = []
    it = module.execute(ports)
    if isinstance(it, (Outcome, type(None))):
        raise TypeError(
            f"{module.describe()} 的 execute 不是生成器（返回了 {type(it).__name__}）"
        )
    try:
        while True:
            events.append(next(it))
    except StopIteration as stop:
        outcome = stop.value
    _require_outcome(module, outcome)
    return events, outcome
