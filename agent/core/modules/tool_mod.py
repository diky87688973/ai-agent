# -*- coding: utf-8 -*-
"""工具模块（收尾）：执行未消费的工具调用。"""
from __future__ import annotations

from time import perf_counter
from typing import Any, Iterator

from agent.core.event_name import (
    ERROR,
    TOOL_CANCELED,
    TOOL_DONE,
    TOOL_ENDED,
    TOOL_FAILED,
    TOOL_STARTED,
    TOOL_SUSPENDED,
)
from agent.core.module import ModuleBase
from agent.core.modules.tool_facts import (
    clip_tool_result,
    pending_tool_calls,
    progress_emitter,
    safe_value,
)
from agent.core.outcome import Outcome
from agent.core.ports import Ports

# ══════════════════════════════════════════════════════════════════════
# 四、工具模块（= 收尾模块）
# ══════════════════════════════════════════════════════════════════════

#: 工具生命周期事实。
#:
#: 每个工具调用必须发 `tool_started` → 恰好一个结果事实 → `tool_ended`：
#:
#:   tool_started   开始调用（监听者可在此起 RT、修剪参数、起卡片=「进行中」）
#:   tool_done      成功完成（卡片=绿色 Done）
#:   tool_failed    失败（卡片=红色 Fail）
#:   tool_canceled  被取消（卡片=Stoped；目前尚未接线，先预留）
#:   tool_suspended 需要外部输入，交回控制权（卡片=「待确认」）
#:   tool_ended     终态：结果事实之后紧随补发，与 `tool_started` 配对，
#:                  并携带把工具调度 RT 算出来所需的一切
#:
#: `tool_ended` 是独立终态事实，单独补一个："用结果事实当终态"：
#:   ① 与 `tool_started` 配对，监控不必猜"哪个事件算结束"；
#:   ② 把"发生了什么"（done/failed/suspended）与"结束了"分开——
#:      前者是结果，后者是生命周期；
#:   ③ 加新的终止路径（取消、超时）时，配对关系不用改。
#:
#: 事件名从 `event_name.py` 导入：在这里重写字面量会把导入的名字覆盖回去，
#: "唯一出处"随之失效。


class ToolModule(ModuleBase):
    """执行模型要求、但尚未执行的工具调用；它是本链的收尾模块。

    职责三条：
      ① 找到"最新一条模型消息里要求了、但还没有结果"的调用并执行；
      ② 发工具生命周期事实：`tool_started` →（结果）→ `tool_ended`；
         需要外部输入则发 `tool_suspended` 并 `return Outcome.suspend(...)`
         （终态，交回控制权，不阻塞）；
      ③ 执行过调用就要求续行（`next`）——刚产生的结果还没被模型看过。

    第③条是"多趟往返"的驱动力：没有它，宿主会在工具执行完那一趟收尾，
    模型永远看不到工具结果（整轮只调一次模型、工具结果被吞）。
    而最后一轮工具执行完，模型在下一趟会给出不带 `tool_calls` 的答复；
    那一趟工具模块无调用可执行、返回 `ok`，宿主自然收尾——不需要谁判断"该结束了"。
    """

    name = "tool"
    requires = ("tool_port",)

    def _cancel_rest(self, ports: Ports, pending, start: int,
                     reason: str) -> Iterator[Any]:
        for rest in pending[start:]:
            yield ports.emit(TOOL_CANCELED, call_id=rest.call_id,
                             name=rest.name, reason=reason)
            yield ports.emit(TOOL_ENDED, call_id=rest.call_id, name=rest.name,
                             status="canceled", elapsed_ms=0)

    def _result_events(self, ports: Ports, call, result, elapsed: int,
                       ok: bool) -> Iterator[Any]:
        if ok:
            images = getattr(result, "attachments", None)
            yield ports.emit(
                TOOL_DONE, call_id=call.call_id, name=call.name,
                data=clip_tool_result(safe_value(getattr(result, "data", None))),
                attachments=(list(images)
                             if isinstance(images, list) and images else None),
                elapsed_ms=elapsed)
        else:
            raw = getattr(result, "data", None)
            data = clip_tool_result(safe_value(raw)) if raw is not None else None
            yield ports.emit(
                TOOL_FAILED, call_id=call.call_id, name=call.name,
                error=str(getattr(result, "error", "") or ""),
                data=data, elapsed_ms=elapsed)
        yield ports.emit(TOOL_ENDED, call_id=call.call_id, name=call.name,
                         status=("done" if ok else "failed"), elapsed_ms=elapsed)

    def execute(self, ports: Ports) -> Iterator[Any]:
        pending = pending_tool_calls(ports.log)
        if not pending:
            return Outcome.ok()
        tools = ports.tool_port
        if tools is None:
            yield ports.emit(ERROR, where="tool", detail="未装配工具端口")
            return Outcome.halt("未装配工具端口")
        on_progress = progress_emitter(ports)
        for index, call in enumerate(pending):
            if index > 0 and ports.canceled():
                yield from self._cancel_rest(ports, pending, index, "user_stop")
                return Outcome.stopped("用户请求停止")
            started = perf_counter()
            yield ports.emit(TOOL_STARTED, call_id=call.call_id, name=call.name,
                             arguments=dict(call.arguments))
            result = tools.execute(
                call, conversation_id=ports.conversation_id,
                progress=on_progress, canceled=ports.canceled,
                tool_call_id=str(call.call_id or ""))
            elapsed = int((perf_counter() - started) * 1000)
            deferred = (bool(getattr(result, "deferred", False))
                        or bool(getattr(result, "await_user", False)))
            if deferred:
                yield ports.emit(
                    TOOL_SUSPENDED, call_id=call.call_id, name=call.name,
                    envelope=safe_value(getattr(result, "data", None)))
                yield ports.emit(TOOL_ENDED, call_id=call.call_id, name=call.name,
                                 status="suspended", elapsed_ms=elapsed)
                yield from self._cancel_rest(
                    ports, pending, index + 1, "suspended_batch")
                return Outcome.suspend(f"工具 {call.name} 需要外部输入")
            ok = bool(getattr(result, "ok", False))
            yield from self._result_events(ports, call, result, elapsed, ok)
        return Outcome.next()
