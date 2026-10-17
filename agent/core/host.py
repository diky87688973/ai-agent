# -*- coding: utf-8 -*-
"""宿主（`Host`）：**循环在这里，回合边界也在这里**。

循环归宿主：遍历模块链是宿主的能力，模块内部只有自己那一段；
`turn_start` 与 `turn_ended` 也由宿主发出，各个模块内部管理自己的事件。

所以职责这样切：

| 谁 | 管什么 |
|---|---|
| **宿主** | 遍历模块链、读四态、决定要不要再跑一趟、**回合边界（`turn_started` / `turn_ended`）** |
| **模块** | 自己那一段的细粒度事件（如模型模块的 `llm_call_start` / `llm_call_end`，可算调用 RT） |

宿主**不理解任何模块的语义**：它不知道什么是压缩、什么是模型、什么是工具，
连"模型返回长什么样"都不用知道——这正是"主体只发号施令，不关心腿是轮子还是机械腿"。

**宿主不保存挂起游标**：`suspend` 是终态，循环直接退出；恢复靠**新一轮** +
从事实重建。所以宿主对象可以在两次运行之间被完全丢弃。

**事件是边跑边出的**：`run_iter` 是惰性生成器，事件在产出那一刻就让给消费者。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterator, List, Optional, Sequence

from agent.core.chain import run_chain_iter
from agent.core.error_report import report_error
from agent.core.event_name import TURN_ENDED, TURN_STARTED
from agent.core.events import Event
from agent.core.module import ModuleBase
from agent.core.ports import ModelPort, Ports, ToolPort
from agent.core.session_log import SessionLog

#: 一个回合最多跑多少趟（模型往返）。
#:
#: 一趟 = 模型说一次话（可带多个工具调用）+ 这些工具全部执行完。
#: 撞上限有两种成因，护栏本身分不出来：
#:   ① 有模块永远返回 `next`（bug）；
#:   ② 这轮任务确实长 —— GUI 自动化每步都要"看 → 想 → 动"，往返天然多。
#: 所以这里只做**预算**，不做判罪；要更大的预算就调 `[agent] max_passes`。
MAX_PASSES_DEFAULT = 64

# 回合边界事实（`TURN_STARTED` / `TURN_ENDED`）**取自 `event_name.py`**，
# 不在这里重写一遍字面量——那是事实词汇的**唯一出处**；多一个定义点，
# 就多一处"改了这头忘那头"的地方。


def _asked_to_stop(cancel: Callable[[], bool]) -> bool:
    """问一次「是否已请求停止」；这个函数自己出错必须把异常抛出去（不得装成「未取消」）。"""
    return bool(cancel())


@dataclass
class TurnResult:
    """一次运行的结论（宿主对外的唯一交付）。"""

    reason: str                     # done / halted / suspended / max_passes / abandoned
    passes: int = 0
    detail: str = ""                # 终态原因（halt / suspend 的 reason）

    @property
    def ok(self) -> bool:
        return self.reason == "done"

    @property
    def paused(self) -> bool:
        """是否停在"等外部输入"（挂起是终态，不是阻塞态）。"""
        return self.reason == "suspended"


class Host:
    """宿主：装配好的模块链 + 循环 + 回合边界。"""

    def __init__(
        self,
        modules: Sequence[ModuleBase],
        *,
        sink: Callable[[Event], None],
        max_passes: int = MAX_PASSES_DEFAULT,
        on_pass_end: Optional[Callable[[], None]] = None,
        seq_allocator: Optional[Callable[[], int]] = None,
    ) -> None:
        self._modules: List[ModuleBase] = list(modules)
        self._sink = sink
        self.max_passes = int(max_passes)
        self.last_result: Optional[TurnResult] = None
        #: **一趟跑完**时回调（由引擎用来增量落盘）。
        #:
        #: 落盘时机由宿主报点：宿主控制循环、知道一趟到哪结束：宿主**才知道
        #: 一趟到哪结束**（它控制循环）。按趟落盘把"批量"与"崩溃安全"都保住：
        #: 单次写盘摊到一整趟的事实上，而中途异常最多丢**当前这一趟**。
        #: （攒到回合末尾落盘，门控在工具执行时抛异常 → 界面已渲染
        #: 完整对话，存储里一个字都没有、刷新即消失，**连用户发言一起丢**。）
        self._on_pass_end = on_pass_end
        #: 全局存储坐标分配器（同 `Ports`）。**回合边界事实也要有坐标**，
        #: 否则 `turn_started` / `turn_ended` 收不到 `id:`，续传时首尾会缺。
        self._seq_allocator = seq_allocator

    # ── 只读观察 ──────────────────────────────────────────

    @property
    def modules(self) -> List[ModuleBase]:
        return list(self._modules)

    def describe(self) -> List[str]:
        """模块链的一行描述（`/health` 与日志用）。"""
        return [m.describe() for m in self._modules]

    # ── 主循环 ────────────────────────────────────────────

    def run_iter(
        self,
        *,
        log: SessionLog,
        conversation_id: str = "",
        model: Optional[ModelPort] = None,
        tools: Optional[ToolPort] = None,
        cancel: Optional[Callable[[], bool]] = None,
    ) -> Iterator[Event]:
        """跑一个回合，**边跑边产出**事实。跑完后读 `self.last_result`。

        产出顺序：`turn_started` → 模块链产出的事实（可能多趟）→ `turn_ended`。
        边界由宿主发，因为它就是"控制循环的那一方"——只有它知道回合从哪到哪。

        `cancel`：壳层传入的停止检查（无参函数，返回是否已请求停止）。
        宿主在每趟开始前问一次，模块在自认为合适的粒度问（模型模块逐帧、
        工具模块逐调用）。各方自己来问，不是被强行打断。取消时发
        `turn_ended{stopped: true}` 并结束——**与 `paused` 是两件事**
        （用户主动停止 ≠ 等外部输入）。
        """
        self.last_result = None
        passes = 0
        # 整个生成器体必须在 `try` 里：`turn_started` 的 `yield` 是**第一个让出点**，
        # 消费者若在第一帧后就放弃（`close()`），异常会在那个 yield 处抛出——
        # 若它落在 try 之外，`finally` 根本不会进入，`last_result` 就永远是 None
        # （`it.close()` 后结论仍为空）。
        try:
            yield self._append(log, TURN_STARTED, conversation_id=conversation_id)
            while passes < self.max_passes:
                if cancel is not None and _asked_to_stop(cancel):
                    self.last_result = TurnResult(reason="stopped", passes=passes,
                                                  detail="用户请求停止")
                    yield self._append(log, TURN_ENDED, conversation_id=conversation_id,
                                       paused=False, halted=False, stopped=True,
                                       passes=passes, detail="用户请求停止")
                    return
                passes += 1
                ports = Ports(
                    emit=self._sink,
                    log=log,
                    conversation_id=conversation_id,
                    model=model,
                    tools=tools,
                    cancel=cancel,
                    seq_allocator=self._seq_allocator,
                )
                chain = run_chain_iter(self._modules, ports)
                # 模块 `yield` 出来的事件在此**立刻**转给消费者——流式的关键。
                # 任何"先收集再转发"的写法都会让流式名存实亡。
                for event in chain:
                    yield event
                result = chain.result
                assert result is not None
                self._report_pass_end()
                if result.terminal is not None:
                    status = result.terminal.status
                    suspended = status == "suspend"
                    stopped = status == "stopped"
                    self.last_result = TurnResult(
                        reason=("suspended" if suspended
                                else ("stopped" if stopped else "halted")),
                        passes=passes,
                        detail=result.terminal.reason,
                    )
                    # `paused` **只对挂起为真**：`halt` 是失败/被拒的中断，
                    # `stopped` 是用户主动停止——都不是"在等外部输入"，
                    # 把它们也标成 paused，观察面会以为要弹确认、作答就能继续。
                    yield self._append(log, TURN_ENDED, conversation_id=conversation_id,
                                       paused=suspended,
                                       halted=(not suspended and not stopped),
                                       stopped=stopped, passes=passes,
                                       detail=self.last_result.detail)
                    return
                if not result.wants_another:
                    self.last_result = TurnResult(reason="done", passes=passes)
                    yield self._append(log, TURN_ENDED, conversation_id=conversation_id,
                                     paused=False, passes=passes)
                    return
            self.last_result = TurnResult(
                reason="max_passes",
                passes=passes,
                detail=f"本回合已达操作 {self.max_passes} 次上限"
                       f"（每次 = 模型一次往返 + 其工具调用），"
                       f"可通过 `[agent] max_passes` 配置调整每回合上限",
            )
            # **三条中止路径都必须显式带全三态**。
            # 这里若只给 `paused`，适配层拿不到 `halted` → 发 `done{ok:true}`
            # → **护栏触顶被 UI 报成"正常完成"**。
            # 对照：`halt` → `error` + `done.ok=False`；
            # `stopped` → `stopped` 帧 + `done.ok=False`。
            yield self._append(log, TURN_ENDED, conversation_id=conversation_id,
                               paused=False, halted=True, stopped=False,
                               passes=passes, detail=self.last_result.detail)
        finally:
            if self.last_result is None:      # 消费者中途放弃迭代
                self.last_result = TurnResult(reason="abandoned", passes=passes)
                self._append(log, TURN_ENDED, conversation_id=conversation_id,
                             paused=False, passes=passes, detail="abandoned")

    # ── 主循环（一次性跑完；便于测试与非流式场合）──────────

    def run(
        self,
        *,
        log: SessionLog,
        conversation_id: str = "",
        model: Optional[ModelPort] = None,
        tools: Optional[ToolPort] = None,
        cancel: Optional[Callable[[], bool]] = None,
    ) -> TurnResult:
        """跑完整个回合，返回结论（事件照常经 `sink` 发出）。

        参数里不带"挂起游标"：宿主不持有跨回合状态。
        要恢复一轮挂起，由调用方（壳层）从**事实源**重建 `log` 后再调一次。
        """
        for _event in self.run_iter(log=log, conversation_id=conversation_id,
                                    model=model, tools=tools,
                                    cancel=cancel):
            pass
        assert self.last_result is not None
        return self.last_result

    def _report_pass_end(self) -> None:
        """一趟跑完：通知增量落盘。回调异常**不得**影响回合（落盘是副作用）。"""
        if self._on_pass_end is None:
            return
        try:
            self._on_pass_end()
        except Exception as exc:
            report_error("core.pass_end", exc)

    # ── 记事实（与 `Ports.emit` 同一纪律：先入日志；由生成器让给消费者）──

    def _emit(self, log: SessionLog, type_: str, **data: Any) -> Event:
        payload = dict(data)
        if self._seq_allocator is not None and "_seq" not in payload:
            try:
                payload["_seq"] = int(self._seq_allocator())
            except Exception as exc:
                # 不阻断回合，但留痕（这个事件将无法断线续传）。
                report_error("core.seq_alloc", exc)
        event = Event(type_, payload)
        log.append([event])
        return event

    def _append(self, log: SessionLog, type_: str, **data: Any) -> Event:
        """记事实**并且**经 `sink` 发出（给生成器已经结束的路径用，如 abandoned）。"""
        event = self._emit(log, type_, **data)
        self._sink(event)
        return event
