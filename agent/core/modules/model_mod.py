# -*- coding: utf-8 -*-
"""模型模块：流式调用模型并落 model_message。"""
from __future__ import annotations

from typing import Any, Dict, Iterator, List

from agent.core.error_report import report_error
from agent.core.event_name import (
    ASSISTANT_DELTA,
    CONTEXT_SEGMENTS,
    ERROR,
    LLM_DONE,
    LLM_ENDED,
    LLM_FAILED,
    LLM_STARTED,
    MODEL_MESSAGE,
    REASONING_DELTA,
    USAGE,
)
from agent.core.image_embed import KEEP_IMAGE_TURNS, MAX_EMBED_IMAGES
from agent.core.module import ModuleBase
from agent.core.modules.support import (
    _assemble_with,
    _prepare_dialogue,
    _segment_snapshot,
    _serialize_call,
    _tail_expects_model,
    _with_mode_note,
)
from agent.core.outcome import Outcome
from agent.core.ports import LogicalRequest, Ports
from agent.core.tool_call import ToolCallRequest


class ModelModule(ModuleBase):
    """调用模型；增量**边到边出**（`yield`），本步结论落成 `model_message` 事实。

    **什么时候该跑**：只看事实末端——
      - 末端是新用户输入（`input_claimed`）→ 该跑；
      - 末端是未消费的工具结果（`tool_result`）→ 该跑（模型得看结果）；
      - 末端已是模型自己的消息 → 不跑，返回 `ok`。

    模型与工具轮替推进，每次推进都把新事实追加到末端，
    所以看**末端是谁**就能判断该不该跑，不需要额外的记账。

    **不要求续行**：模型只负责"说话"；"还要不要再调一轮工具"是工具模块的语义
    （它是收尾模块）。
    """

    name = "model"
    requires = ("model_port",)

    def __init__(self, *, context: Any = None, compactor: Any = None,
                 effort: str = "high", model: str = "",
                 image_turns: int = KEEP_IMAGE_TURNS,
                 image_max: int = MAX_EMBED_IMAGES,
                 mode_note: str = "") -> None:
        self.context_pass = context
        self._compactor = compactor
        self._effort = str(effort or "high")
        #: 本次请求要用哪个模型（空串 = 用 provider 的默认）。
        #: 与 `effort` 同源：都在**每个回合装配引擎时**由会话级设置解析而来。
        self._model = str(model or "")
        #: 只把**最近这么多轮**用户发言里的图带进请求；负数 = 不限。
        #: 缺省 999999 = 不剥（前缀稳定、缓存可复用）。
        self._image_turns = int(image_turns)
        #: 这些轮里最多带几张图；负数 = 不限。最近一轮优先保。
        self._image_max = int(image_max)
        #: 执行模式说明：**只加在发给模型的这一份请求尾部**，不落记录、不发事件。
        #: 放在最后一项是为了让切模式只影响尾部这一条，前面的前缀缓存照旧命中。
        self._mode_note = str(mode_note or "")

    def _covered_end(self) -> int:
        """已覆盖前缀长度（压缩器维护）；没有压缩器就是 0。"""
        value = getattr(self._compactor, "covered_end", 0)
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    def execute(self, ports: Ports) -> Iterator[Any]:
        if not _tail_expects_model(ports.log):
            return Outcome.ok()
        model = ports.model_port
        if model is None:
            yield ports.emit(ERROR, where="model", detail="未装配模型端口")
            return Outcome.halt("未装配模型端口")

        # 请求前补齐悬空的 tool_calls。挂起的终态不产生 tool 消息；
        # 取消若没到达服务器，事实里就一直缺配对，此后每次请求都会被拒绝。
        dialogue = _prepare_dialogue(ports.log.derive_request_messages(),
                                     self._image_turns, self._image_max)
        # 本轮起点 = 对话里最后一条用户消息的下标（含）。它之前的思维链一律不回传
        # （provider 侧按这个下标裁）：思维链是模型的中间产物，回传只是让每轮输入
        # 凭空多几万 token，而那几万必然未命中缓存；不回传时**同一轮内每次请求的
        # 前缀逐字节相同**，缓存能吃满。工具结果与模型自己的回答照旧带着。
        # 没有用户消息（理论上到不了这里）就退回 0，等于不裁剪。
        turn_start = 0
        for index in range(len(dialogue) - 1, -1, -1):
            if str(dialogue[index].get("role") or "") == "user":
                turn_start = index
                break

        # ── 装配：头部 + 对话 + 尾部（唯一入口，不重建）──
        #
        # 头部 = 系统提示 / Skills / 知识库 / 摘要（管线持有）
        # 对话 = 事实折叠出来的对话
        # 尾部 = 执行模式（本轮新输入已在对话末尾，由事实带来）
        if self.context_pass is not None:
            assembled = _assemble_with(self.context_pass, dialogue, self._mode_note,
                                       self._covered_end())
            if assembled is None:
                # 上下文缺装配能力 → 退回只有对话（不阻断回合），但必须留痕：
                # 这种请求缺头部，模型看不到系统提示，属于异常状态。
                report_error("core.model", "上下文缺装配能力（本轮请求可能缺系统前缀）")
                messages = _with_mode_note(dialogue, self._mode_note)
            else:
                messages = assembled
        else:
            messages = _with_mode_note(dialogue, self._mode_note)

        request = LogicalRequest(
            messages=messages,
            tools=(ports.tool_port.schemas() if ports.tool_port is not None else []),
            effort=self._effort,
            model=self._model,
            # 头部条数（系统提示 / 插件段 / 摘要）+ 本轮起点 = 整份 messages 里的本轮起点。
            turn_start=len(messages) - len(dialogue) + turn_start,
            conversation_id=str(getattr(ports, "conversation_id", "") or ""),
        )
        # 装配完成 → 发一条**分段快照**（上下文示意图的数据源）。
        # 分段统计走把装配结果拆开的方式：模式与工具结果的内部注入只在这份
        # 装配里，落记录里没有，所以只能在这里算。
        #
        # 预算（= 压缩阈值）必须显式传：不传就只能拿"已用"当归一化基准，
        # 剩余容量恒为 0，界面那条永远显示 0%。
        budget = 0
        try:
            budget = int(getattr(self._compactor, "summary_token_threshold", 0) or 0)
        except (TypeError, ValueError):
            budget = 0
        segments = _segment_snapshot(self.context_pass, messages, budget_tokens=budget)
        if segments is not None:
            yield ports.emit(CONTEXT_SEGMENTS, **segments)
        # 模型模块**自己的**细粒度事件：调用边界。有了它，监控能算出调用 RT
        # （以及首帧时延），而不必去猜"哪两个事件之间算一次调用"。
        # 这是"各个模块内部管理自己的事件"的落点——宿主不掺和。
        from time import perf_counter
        started = perf_counter()
        first_chunk_ms = None
        chunks = 0
        yield ports.emit(LLM_STARTED, model=model.name_for(request) or "",
                         effort=self._effort, messages=len(messages),
                         tools=len(request.tools or []))
        text_parts: List[str] = []
        reasoning_parts: List[str] = []
        tool_calls: List[ToolCallRequest] = []
        usage: Dict[str, Any] = {}
        failure = ""
        try:
            for delta in model.stream(request):
                if ports.canceled():
                    # 取消检查点（流式消费中每帧）：长回答能被立刻打断，
                    # 不必等它说完。已产出的增量**保留**（那是已发生的事实）。
                    yield ports.emit(LLM_FAILED, model=model.name() or "",
                                     error="CanceledByUser", elapsed_ms=int((perf_counter() - started) * 1000),
                                     chunks=chunks)
                    yield ports.emit(LLM_ENDED, model=model.name() or "",
                                     status="canceled", elapsed_ms=int((perf_counter() - started) * 1000),
                                     chunks=chunks)
                    # **返回 `stopped`**：同一次用户动作在工具路径
                    # 已经被归一成 `stopped`（见下面的工具取消分支与 `host.py` 的
                    # `_asked_to_stop`）。模型路径若返回 `halt`，宿主就报
                    # `turn_ended{halted:true}` → 适配层只认 `paused`/`stopped`
                    # → 发出 `done{ok:true}`、**不发 `stopped`** —— 于是
                    # "用户停止"在**最常见的打断路径（流式生成中）**上到不了观察面：
                    # 步骤卡被收成绿色 `Done`/"思考完毕"，别的标签页/API 客户端
                    # 永远以为"正常完成"。同一个动作两种终态，也违反
                    # `outcome.py` 自己写的"stopped ≠ halt，观察面要能分辨"。
                    return Outcome.stopped("用户请求停止")
                chunks += 1
                if first_chunk_ms is None:
                    first_chunk_ms = int((perf_counter() - started) * 1000)
                kind = str(getattr(delta, "kind", "") or "")
                if kind == "text":
                    text_parts.append(str(delta.text or ""))
                    yield ports.emit(ASSISTANT_DELTA, text=str(delta.text or ""))
                elif kind == "reasoning":
                    reasoning_parts.append(str(delta.text or ""))
                    yield ports.emit(REASONING_DELTA, text=str(delta.text or ""))
                elif kind == "tool_call" and getattr(delta, "tool_call", None) is not None:
                    tool_calls.append(delta.tool_call)
                elif kind == "usage" and getattr(delta, "usage", None):
                    usage = dict(delta.usage)
        except Exception as exc:
            # 模型调用失败：**结构化上报**（结果 + 终态都发），然后让回合停。
            # 交给模型模块是因为只有它知道"这次调用失败了"；
            # 重试是**策略**，属于钩子（尚未接线），不在这里偷偷重试。
            failure = f"{type(exc).__name__}: {exc}"
            report_error("core.model", exc)
        elapsed = int((perf_counter() - started) * 1000)
        if failure:
            yield ports.emit(LLM_FAILED, model=model.name() or "", error=failure,
                             elapsed_ms=elapsed, chunks=chunks)
            yield ports.emit(LLM_ENDED, model=model.name() or "", status="failed",
                             elapsed_ms=elapsed, chunks=chunks)
            yield ports.emit(ERROR, where="model", detail=failure)
            return Outcome.halt(f"模型调用失败：{failure}")
        yield ports.emit(LLM_DONE, model=model.name() or "",
                         elapsed_ms=elapsed,
                         first_chunk_ms=(first_chunk_ms if first_chunk_ms is not None else -1),
                         chunks=chunks, tool_calls=len(tool_calls))
        yield ports.emit(LLM_ENDED, model=model.name() or "", status="done",
                         elapsed_ms=elapsed, chunks=chunks,
                         tool_calls=len(tool_calls))

        if usage:
            yield ports.emit(USAGE, **usage)
        message_data: Dict[str, Any] = {
            "content": "".join(text_parts),
            "tool_calls": [_serialize_call(c) for c in tool_calls],
        }
        reasoning = "".join(reasoning_parts)
        if reasoning:
            message_data["reasoning_content"] = reasoning
        yield ports.emit(MODEL_MESSAGE, **message_data)
        return Outcome.ok()
