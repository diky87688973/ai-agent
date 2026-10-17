# -*- coding: utf-8 -*-
"""工具模块（收尾）：执行未消费的工具调用。"""
from __future__ import annotations

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
from agent.core.modules.support import (
    _clip_tool_result,
    _pending_tool_calls,
    _progress_emitter,
    _safe,
)
from agent.core.outcome import Outcome
from agent.core.ports import Ports

# ══════════════════════════════════════════════════════════════════════
# 四、工具模块（= 收尾模块）
# ══════════════════════════════════════════════════════════════════════

#: 工具生命周期事实。
#:
#: 每个工具调用必须发 **`tool_started` → 恰好一个结果事实 → `tool_ended`**：
#:
#:   tool_started   开始调用（监听者可在此起 RT、修剪参数、起卡片=「进行中」）
#:   tool_done      成功完成（卡片=绿色 Done）
#:   tool_failed    失败（卡片=红色 Fail）
#:   tool_canceled  被取消（卡片=Stoped；目前尚未接线，先预留）
#:   tool_suspended 需要外部输入，交回控制权（卡片=「待确认」）
#:   tool_ended     **终态**：结果事实之后紧随补发，与 `tool_started` 配对，
#:                  并携带把工具调度 RT 算出来所需的一切
#:
#: `tool_ended` 是独立终态事实，单独补一个："用结果事实当终态"：
#:   ① 与 `tool_started` **配对**，监控不必猜"哪个事件算结束"；
#:   ② 把"发生了什么"（done/failed/suspended）与"结束了"分开——
#:      前者是结果，后者是生命周期；
#:   ③ 加新的终止路径（取消、超时）时，**配对关系不用改**。
#:
#: 事件名从 `event_name.py` 导入：在这里重写字面量会把导入的名字覆盖回去，
#: "唯一出处"随之失效。


class ToolModule(ModuleBase):
    """执行模型要求、但**尚未执行**的工具调用；它是本链的**收尾模块**。

    职责三条：
      ① 找到"最新一条模型消息里要求了、但还没有结果"的调用并执行；
      ② 发**工具生命周期事实**：`tool_started` →（结果）→ `tool_ended`；
         需要外部输入则发 `tool_suspended` 并 **`return Outcome.suspend(...)`**
         （终态，交回控制权，**不阻塞**）；
      ③ **执行过调用就要求续行**（`next`）——刚产生的结果还没被模型看过。

    第③条是"多趟往返"的驱动力：没有它，宿主会在工具执行完那一趟收尾，
    模型永远看不到工具结果（整轮只调一次模型、工具结果被吞）。
    而**最后一轮工具执行完**，模型在下一趟会给出不带 `tool_calls` 的答复；
    那一趟工具模块无调用可执行、返回 `ok`，宿主自然收尾——不需要谁判断"该结束了"。
    """

    name = "tool"
    requires = ("tool_port",)

    def execute(self, ports: Ports) -> Iterator[Any]:
        pending = _pending_tool_calls(ports.log)
        if not pending:
            return Outcome.ok()
        tools = ports.tool_port
        if tools is None:
            yield ports.emit(ERROR, where="tool", detail="未装配工具端口")
            return Outcome.halt("未装配工具端口")

        on_progress = _progress_emitter(ports)
        for index, call in enumerate(pending):
            if index > 0 and ports.canceled():
                # 取消检查点（"每个工具执行前"）：不再启动新调用，
                # 但**必须给剩余调用补终态**——否则
                #   ① 卡片永远停在「进行中」（用户看不到"它被取消了"）；
                #   ② 模型历史里 `assistant(tool_calls)` 缺少对应的 tool 响应，
                #      下一轮请求会被模型 API 拒绝
                #      （模型 API 会因缺 tool 消息拒掉整个请求）。
                for rest in pending[index:]:
                    yield ports.emit(TOOL_CANCELED, call_id=rest.call_id,
                                     name=rest.name, reason="user_stop")
                    yield ports.emit(TOOL_ENDED, call_id=rest.call_id, name=rest.name,
                                     status="canceled", elapsed_ms=0)
                return Outcome.stopped("用户请求停止")
            from time import perf_counter
            started = perf_counter()
            yield ports.emit(TOOL_STARTED, call_id=call.call_id, name=call.name,
                             arguments=dict(call.arguments))
            result = tools.execute(call, conversation_id=ports.conversation_id,
                                   progress=on_progress, canceled=ports.canceled,
                                   tool_call_id=str(call.call_id or ""))
            elapsed = int((perf_counter() - started) * 1000)
            deferred = (bool(getattr(result, "deferred", False))
                        or bool(getattr(result, "await_user", False)))
            if deferred:
                # 需要外部输入：本次调用**还没返回**，所以没有 done/failed，
                # 但生命周期到此为止（控制权交回）——仍补 `tool_ended`，
                # 状态标 `suspended`，好与 `tool_started` 配对。
                yield ports.emit(TOOL_SUSPENDED, call_id=call.call_id, name=call.name,
                                 envelope=_safe(getattr(result, "data", None)))
                yield ports.emit(TOOL_ENDED, call_id=call.call_id, name=call.name,
                                 status="suspended", elapsed_ms=elapsed)
                # **本批剩下的调用必须补终态**：模型一条消息要求
                # [ask_user(c1), echo(c2)] 时，c1 挂起后 c2 既没执行、也没有任何事实。
                #
                # 两个后果都很严重：
                #   ① 历史里 `assistant(tool_calls=[c1,c2])` 永远缺 c2 的响应 →
                #      **此后每个请求都非法**（模型 API 400），会话彻底打不开；
                #   ② 用户看不出 c2 被跳过了（卡片永远停在「进行中」或根本不出现）。
                #
                # 剩余调用标 `canceled`：：**挂起是终态**
                # （`Outcome.suspend` 交出控制权，恢复是**新回合**）。新回合里
                # 模型可能已经换了意图，替它执行一条旧指令更危险。
                # 标 `canceled` 让模型**看得见"这两个没做"**，由它决定要不要重发
                # ——这比静默丢弃安全，也比擅自补跑安全。
                for rest in pending[index + 1:]:
                    yield ports.emit(TOOL_CANCELED, call_id=rest.call_id,
                                     name=rest.name, reason="suspended_batch")
                    yield ports.emit(TOOL_ENDED, call_id=rest.call_id, name=rest.name,
                                     status="canceled", elapsed_ms=0)
                return Outcome.suspend(f"工具 {call.name} 需要外部输入")
            ok = bool(getattr(result, "ok", False))
            if ok:
                # 进上下文前统一裁一刀：工具自己的 `max_chars` 是**默认值**不是上限，
                # 一次读 20 万字符的结果会永久留在上下文里，把每轮请求都撑大。
                #
                # 附件不过裁刀：`_clip_tool_result` 按字符截断，图片是 base64，
                # 截断即损坏；其体积由 `build_tool_parts` 的预算单独约束。
                result_images = getattr(result, "attachments", None)
                yield ports.emit(TOOL_DONE, call_id=call.call_id, name=call.name,
                                 data=_clip_tool_result(_safe(getattr(result, "data", None))),
                                 attachments=(list(result_images)
                                              if isinstance(result_images, list) and result_images
                                              else None),
                                 elapsed_ms=elapsed)
            else:
                # 失败也要带 data：工具可在异常上挂结构化 status（如
                # old_text_not_found），回灌模型信封为 {ok:false,error,data}。
                fail_raw = getattr(result, "data", None)
                fail_data = (
                    _clip_tool_result(_safe(fail_raw))
                    if fail_raw is not None else None
                )
                yield ports.emit(TOOL_FAILED, call_id=call.call_id, name=call.name,
                                 error=str(getattr(result, "error", "") or ""),
                                 data=fail_data,
                                 elapsed_ms=elapsed)
            yield ports.emit(TOOL_ENDED, call_id=call.call_id, name=call.name,
                             status=("done" if ok else "failed"), elapsed_ms=elapsed)
        return Outcome.next()            # 刚产生了工具结果 → 让模型看
