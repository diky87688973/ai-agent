# -*- coding: utf-8 -*-
"""四个真实模块：输入 / 压缩 / 模型 / 工具。

每个模块的 `execute` 是**生成器**：**`yield` 事实，`return` 控制信号**
（`execute` 为生成器的契约见 `module.py` 顶部）。

模块**只经端口访问外界**（`Ports`），**数据走事件**，模块之间不互相 import、
不共享字段——它们共享的是**事实日志**与**端口接口**。
"""
from __future__ import annotations

import sys
from typing import Any, Dict, Iterator, List, Optional, Sequence

#: 事实名统一从 `event_name.py` 取——那是**事实词汇的唯一出处**。
#: 事件名常量取自 `event_name.py`；手写字符串拼错会静默丢事件（拼错就是静默丢事件）。
from agent.core.event_name import (
    ASSISTANT_DELTA,
    COMPRESS_ENDED,
    COMPRESS_STARTED,
    CONTEXT_COMPACTED,
    CONTEXT_SEGMENTS,
    ERROR,
    INBOX_DEQUEUED,
    INPUT_CLAIMED,
    INPUT_ENDED,
    INPUT_STARTED,
    LLM_DONE,
    LLM_ENDED,
    LLM_FAILED,
    LLM_STARTED,
    MODEL_MESSAGE,
    REASONING_DELTA,
    TOOL_CANCELED,
    TOOL_DONE,
    TOOL_ENDED,
    TOOL_FAILED,
    TOOL_PROGRESS,
    TOOL_STARTED,
    TOOL_SUSPENDED,
    USAGE,
)
from agent.core.image_embed import (
    KEEP_IMAGE_TURNS,
    MAX_EMBED_IMAGES,
    strip_old_images,
)
from agent.core.module import ModuleBase
from agent.core.outcome import Outcome
from agent.core.ports import LogicalRequest, Ports
from agent.core.session_log import SessionLog
from agent.core.tool_call import ToolCallRequest

#: 判定"这次调用结束了没有"统一用终态事实（是否结束以终态事实 `tool_ended` 为唯一判据）
_TOOL_ENDED = TOOL_ENDED

# ══════════════════════════════════════════════════════════════════════
# 一、输入模块
# ══════════════════════════════════════════════════════════════════════


class InputModule(ModuleBase):
    """把本轮的**新用户输入**认领成事实。

    - 有输入：发 `input_claimed`，返回 `ok`（链上后面的模型模块自己会看到"末端是新输入"）；
    - **无输入**：什么都不发，返回 `ok`。

    第二点是硬要求：接口确认触发的恢复轮**没有用户发言**，此时上下文末端
    就该是那次工具调用——凭空发一条空的 `input_claimed` 会让消息序列变成
    `…assistant(tool_calls) → user("") → tool`，模型 API 直接拒绝（400）。

    **不要求续行**：这条链的模型模块在同**趟**里就会跑（它看事实末端）。若这里返回
    `next`，宿主会多跑一整趟空链（`passes` 从 1 变 2）。
    """

    name = "input"

    def __init__(self, text: str = "",
                 attachments: Optional[Sequence[Dict[str, Any]]] = None) -> None:
        self._text = str(text or "")
        self._attachments = list(attachments or [])

    def feed(self, text: str, attachments: Optional[Sequence[Dict[str, Any]]] = None) -> None:
        """投喂一轮新输入（壳层在每轮开始前调用）。"""
        self._text = str(text or "")
        self._attachments = list(attachments or [])

    def execute(self, ports: Ports) -> Iterator[Any]:
        if not self._text and not self._attachments:
            # 无输入 = 无用户消息（不是"跳过"，是"没有"）。**仍发终态**：
            # 监听者要能配对上"这次调用结束了"，而不是猜"它到底跑没跑"。
            yield ports.emit(INPUT_ENDED, claimed=False)
            return Outcome.ok()
        text, attachments = self._text, self._attachments
        self._text, self._attachments = "", []      # 消费掉，本趟之后就没有新输入了
        from time import perf_counter
        started = perf_counter()
        yield ports.emit(INPUT_STARTED, length=len(text),
                         attachments=len(attachments))
        if attachments:
            yield ports.emit(INPUT_CLAIMED, content=text, attachments=attachments)
        else:
            yield ports.emit(INPUT_CLAIMED, content=text)
        yield ports.emit(INPUT_ENDED, claimed=True,
                         elapsed_ms=int((perf_counter() - started) * 1000))
        return Outcome.ok()


# ══════════════════════════════════════════════════════════════════════
# 二、压缩模块
# ══════════════════════════════════════════════════════════════════════


class InboxModule(ModuleBase):
    """会话消息队列：把别的会话投进来的消息，**在本轮开始前**收进上下文。

    位置在压缩之前：入站消息会变成新的用户轮次，压缩得看得见它们，
    否则"刚收到消息就按旧预算压缩"会把新消息挤掉。

    **从不要求续行**：这一模块只负责"把排队的消息搬进事实"，
    搬完就结束；要不要再问一次模型由链上的后续模块决定。
    队列为空是常态，此时不产生任何事件。
    """

    name = "inbox"
    requires = ("inbox",)

    def __init__(self, *, inbox: Any = None) -> None:
        #: 一个可调用对象：`(cid) -> Optional[dict]`，返回队首消息或 None。
        #: 由装配方注入（内核不认某个具体存储实现）。
        self._inbox = inbox

    def execute(self, ports: Ports) -> Iterator[Any]:
        if self._inbox is None:
            return Outcome.ok()
        cid = str(getattr(ports, "conversation_id", "") or "")
        if not cid:
            return Outcome.ok()
        received = 0
        while True:
            try:
                msg = self._inbox(cid)
            except Exception:
                # 判据：队列读失败不该打断回合 —— 消息还在（或已丢），
                # 但用户当前这一轮必须照常跑完。
                break
            if not isinstance(msg, dict):
                break
            text = str(msg.get("content") or "").strip()
            if not text:
                # 空消息（只有空白）没有可读内容：**直接丢弃并留痕**，
                # 不能既 pop 掉又装作收进来了 —— 那样队列少了消息却什么都没发生。
                yield ports.emit(INBOX_DEQUEUED, batch_count=0, dropped=1)
                continue
            # 入站消息就是**一条用户输入事实**：这样它自然进入模型可见消息序列，
            # 与用户手打的输入走同一条读规则。
            # 发送者字段由 `session_send` 写入，键名是 `_sender` / `_sender_name`
            # （下划线开头，与事实字段一致）。
            sender = str(msg.get("_sender") or msg.get("sender") or "").strip()
            payload: Dict[str, Any] = {"content": text}
            if sender:
                payload["_sender"] = sender
                name = str(msg.get("_sender_name") or "").strip()
                if name:
                    payload["_sender_name"] = name
            yield ports.emit(INPUT_CLAIMED, **payload)
            received += 1
        if received:
            yield ports.emit(INBOX_DEQUEUED, batch_count=received)
        return Outcome.ok()


class CompressModule(ModuleBase):
    """上下文预算与压缩：把循环里的三处检查收拢成一个模块。

    **从不要求续行**：压缩是准备动作，不产生"该跑模型了"的意图。
    压缩器缺省或出错一律放行——压缩是增强项，绝不阻断回合。
    """

    name = "compress"
    requires = ("context", "compactor")

    def __init__(self, *, context: Any = None, compactor: Any = None,
                 mode_note: str = "") -> None:
        self._context = context
        self._compactor = compactor
        #: 执行模式说明 —— 摘要复用前缀时要照平常请求补在末尾。
        #: 与 `ModelModule` 各持一份：两个模块各自组装各自的请求，互相不读对方状态。
        self._mode_note = str(mode_note or "")

    def _covered_end(self) -> int:
        """已覆盖前缀长度（压缩器维护）；没有压缩器就是 0。"""
        value = getattr(self._compactor, "covered_end", 0)
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    def execute(self, ports: Ports) -> Iterator[Any]:
        if self._context is None and self._compactor is None:
            # 没装压缩能力：仍发终态（`skipped`），监听者据此知道"这轮没压"，
            # 而不是以为"事件丢了"。
            yield ports.emit(COMPRESS_ENDED, compacted=False, skipped=True)
            return Outcome.ok()
        from time import perf_counter
        started = perf_counter()
        # 发给模型的请求序列：**必须成对**（`derive_request_messages`
        # 会为悬空的 tool_calls 补说明性占位，否则模型 API 硬拒绝 400）。
        # 请求序列取自 derive_request_messages()；derive_messages() 保留悬空——那是日志的忠实折叠，会保留悬空。
        dialogue = ports.log.derive_request_messages()
        # 工具定义照平常请求取同一份：摘要复用前缀时它是前缀的一部分，
        # 少一项或换一份就整段缓存作废。
        schemas = ports.tool_port.schemas() if getattr(ports, "tool_port", None) is not None else []
        yield ports.emit(COMPRESS_STARTED, messages=len(dialogue))
        report: Any = None
        if self._compactor is not None:
            try:
                # 压缩走**同一条装配入口**：头部 + 对话（+ 尾部仅执行模式，随后剔除）。
                # 压缩器拿到的这份与随后模型请求的前缀是同一份装配结果。
                whole = _assemble_with(self._context, dialogue, self._mode_note,
                                       self._covered_end())
                report = self._compactor.ensure_before_append(
                    self._context, dialogue, pending=None, tools=schemas,
                    mode_note=self._mode_note, assembled=whole)
            except Exception as exc:
                # 压缩异常 → 放行，不阻断回合；但**必须留痕**：静默吞掉会让
                # "压缩从未生效"看起来像"没超阈值"，排查时会往完全错的方向找。
                report = None
                print(f"[core] 压缩检查失败（已放行，本轮不压缩）："
                      f"{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        elif self._context is not None:
            # 没有压缩能力：至少把对话装进上下文，后续模块才看得到。
            _assemble_with(self._context, dialogue, self._mode_note, 0)
        compacted = isinstance(report, dict) and bool(report)
        if compacted:
            yield ports.emit(CONTEXT_COMPACTED, **report)
        yield ports.emit(COMPRESS_ENDED, compacted=compacted,
                         elapsed_ms=int((perf_counter() - started) * 1000))
        return Outcome.ok()        # ← 控制信号经 StopIteration.value 传出；缺 return 时该值为 None


# ══════════════════════════════════════════════════════════════════════
# 三、模型模块
# ══════════════════════════════════════════════════════════════════════


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
        self._context = context
        self._compactor = compactor
        self._effort = str(effort or "high")
        #: 本次请求要用哪个模型（空串 = 用 provider 的默认）。
        #: 与 `effort` 同源：都在**每个回合装配引擎时**由会话级设置解析而来。
        self._model = str(model or "")
        #: 只把**最近这么多轮**用户发言里的图带进请求；负数 = 不限。
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

        dialogue = ports.log.derive_messages()
        # 老图不重复塞进请求体：图片按**最近几轮用户发言**保留、总数再设一道闸，
        # 更早/超量的转文本占位。只改这一份，事实流里的字节一个都不动。
        dialogue, _stripped = strip_old_images(
            dialogue, keep_turns=self._image_turns, max_images=self._image_max)

        # ── 装配：头部 + 对话 + 尾部（唯一入口，不重建）──
        #
        # 头部 = 系统提示 / Skills / 知识库 / 摘要（管线持有）
        # 对话 = 事实折叠出来的对话
        # 尾部 = 执行模式（本轮新输入已在对话末尾，由事实带来）
        if self._context is not None:
            assembled = _assemble_with(self._context, dialogue, self._mode_note,
                                       self._covered_end())
            if assembled is None:
                # 上下文缺装配能力 → 退回只有对话（不阻断回合），但必须留痕：
                # 这种请求缺头部，模型看不到系统提示，属于异常状态。
                print("[core] 上下文缺装配能力（本轮请求可能缺系统前缀）",
                      file=sys.stderr, flush=True)
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
            conversation_id=str(getattr(ports, "conversation_id", "") or ""),
            system=(self._context.system_text()
                    if self._context is not None and hasattr(self._context, "system_text")
                    else ""),
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
        segments = _segment_snapshot(self._context, messages, budget_tokens=budget)
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
                yield ports.emit(TOOL_DONE, call_id=call.call_id, name=call.name,
                                 data=_safe(getattr(result, "data", None)),
                                 elapsed_ms=elapsed)
            else:
                yield ports.emit(TOOL_FAILED, call_id=call.call_id, name=call.name,
                                 error=str(getattr(result, "error", "") or ""),
                                 elapsed_ms=elapsed)
            yield ports.emit(TOOL_ENDED, call_id=call.call_id, name=call.name,
                             status=("done" if ok else "failed"), elapsed_ms=elapsed)
        return Outcome.next()            # 刚产生了工具结果 → 让模型看


# ══════════════════════════════════════════════════════════════════════
# 五、默认链装配
# ══════════════════════════════════════════════════════════════════════


def _with_mode_note(messages: Any, mode_note: str) -> List[Dict[str, Any]]:
    """把执行模式说明附加到请求消息的**最末尾**（不动原列表、不动事实流）。

    模式说明是宿主附加的指令，不是用户发言 —— 用 `role=system`。
    非用户发起的请求一律走 system：用户消息的位置只放用户真正发的东西。

    追加一条独立消息而不是拼进最后一条的正文：最后一条可能是多模态数组
    或工具结果，拼接会改坏它的结构；独立成条也保证"改动只落在尾部"这件事一眼可见。
    """
    note = str(mode_note or "").strip()
    if not note:
        return list(messages or [])
    return list(messages or []) + [{"role": "system", "content": note}]


def build_default_chain(
    *,
    input_module: Optional[ModuleBase] = None,
    context: Any = None,
    compactor: Any = None,
    inbox: Any = None,
    effort: str = "high",
    model: str = "",
    image_turns: int = KEEP_IMAGE_TURNS,
    image_max: int = MAX_EMBED_IMAGES,
    mode_note: str = "",
) -> List[ModuleBase]:
    """默认模块链：输入 → 收件箱 → 压缩 → 模型 → 工具。

    顺序即语义：先认领输入、再收别的会话投进来的消息、再管预算、
    再问模型、最后执行工具（收尾）。收件箱必须在压缩之前 —— 它会产生新的
    用户轮次，压缩要看得见这些轮次。
    装配方可以换掉任意一环或插入自己的模块——宿主不关心链上有什么。
    """
    return [
        input_module if input_module is not None else InputModule(),
        InboxModule(inbox=inbox),
        CompressModule(context=context, compactor=compactor, mode_note=mode_note),
        ModelModule(context=context, compactor=compactor, effort=effort, model=model,
                    image_turns=image_turns, image_max=image_max,
                    mode_note=mode_note),
        ToolModule(),
    ]


# ══════════════════════════════════════════════════════════════════════
# 六、事实读法（模块共用的**读规则**，不是模块间依赖）
# ══════════════════════════════════════════════════════════════════════





def _assemble_with(context: Any, dialogue: Any, mode_note: str,
                   covered_end: int) -> Optional[List[Dict[str, Any]]]:
    """把对话装进上下文并装配出整份请求消息（头部 + 对话 + 尾部）。

    上下文缺能力（没实现 `set_dialogue` / `assembles`）时返回 None ——
    调用方据此退回"只有对话"的降级路径，而不是崩掉。
    """
    if context is None:
        return None
    if not (hasattr(context, "set_dialogue") and hasattr(context, "assembles")):
        return None
    context.set_dialogue(dialogue, covered_end=covered_end)
    note = str(mode_note or "").strip()
    tail = [{"role": "system", "content": note}] if note else []
    return list(context.assembles(tail))


def _segment_snapshot(context: Any, messages: Any,
                      budget_tokens: int = 0) -> Optional[Dict[str, Any]]:
    """把装配好的请求拆成分段快照（段名 + 各段估算 token）。

    口径与真正发出去的请求一致（同一份装配、同一个估算器）：
    头部各块（系统提示词 / 插件各段 / 记忆摘要）+ 对话
    + 尾部（本轮新输入 / 工具结果 / 执行模式）。

    `budget_tokens` 是各段 `pct` 的归一化基准（= 压缩阈值）。不传就只能拿"已用"
    当基准，剩余容量恒为 0 —— 界面那条永远显示 0%，所以调用方必须给。

    上下文缺分段能力（或算不出来）→ `None`，调用方不发这条事件。
    """
    if context is None or not hasattr(context, "layout_payload"):
        return None
    mode = _mode_tail(messages)
    try:
        payload = context.layout_payload(tail_messages=mode,
                                         budget_tokens=int(budget_tokens or 0))
    except Exception:
        return None
    if not payload or not payload.get("segments"):
        return None
    return payload


def _mode_tail(messages: Any) -> List[Dict[str, Any]]:
    """请求尾部的执行模式说明（正文以 `## 当前模式：` 开头）。

    位置不固定：用户输入轮末尾是 `[本轮新输入][执行模式]`，工具轮里是
    `[执行模式][工具结果]`。所以倒序按内容认，不按位置猜。
    """
    for m in reversed(list(messages or [])):
        if not isinstance(m, dict):
            continue
        if str(m.get("role") or "") == "system" \
                and str(m.get("content") or "").startswith("## 当前模式"):
            return [m]
    return []


def _tail_expects_model(log: SessionLog) -> bool:
    """上下文末端是否**在等模型说话**。

    倒着扫事实，先撞到这两个之一就是要跑模型：
      - `input_claimed`：新用户发言；
      - `tool_result`：工具结果回来了，模型得看。
    撞到 `model_message` 说明模型已经答过、且其后没有新东西 → 不用跑。

    **只看末端即可判定**：一轮里模型与工具交替推进，每次推进都会把新事实追加到
    末端，所以不需要额外的记账。
    """
    for event in reversed(list(getattr(log, "events", ()))):
        kind = str(getattr(event, "type", "") or "")
        if kind in (INPUT_CLAIMED, _TOOL_ENDED):
            return True
        if kind == MODEL_MESSAGE:
            return False
    return False


def _pending_tool_calls(log: SessionLog) -> List[ToolCallRequest]:
    """最新一条模型消息要求、但**还没有任何结果**的调用（保持原顺序）。

    判据只看事实：模型消息里要求了，且没有对应的 `tool_result`。
    **已被挂起的调用不再重复执行**——它等的是外部输入，不是再来一次。
    """
    events = list(getattr(log, "events", ()))
    newest: List[Dict[str, Any]] = []
    for event in reversed(events):
        if str(getattr(event, "type", "")) == MODEL_MESSAGE:
            newest = list((event.data or {}).get("tool_calls") or [])
            break
    if not newest:
        return []
    done = {str((e.data or {}).get("call_id") or "")
            for e in events if str(getattr(e, "type", "")) == _TOOL_ENDED}
    suspended = {str((e.data or {}).get("call_id") or "")
                 for e in events if str(getattr(e, "type", "")) == TOOL_SUSPENDED}
    out: List[ToolCallRequest] = []
    for raw in newest:
        call_id = str(raw.get("id") or "")
        if not call_id or call_id in done or call_id in suspended:
            continue
        args = raw.get("arguments")
        out.append(ToolCallRequest(
            call_id=call_id,
            name=str(raw.get("name") or ""),
            arguments=dict(args) if isinstance(args, dict) else {},
        ))
    return out


def _serialize_call(call: ToolCallRequest) -> Dict[str, Any]:
    """工具调用 → 事实里的形状（保证历史事实可混装）。"""
    return {"id": call.call_id, "name": call.name, "arguments": dict(call.arguments)}


def _safe(value: Any) -> Any:
    """落事实前把不可序列化的东西换成可读文本（事实必须能写进 JSONL）。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    return str(value)


def _progress_emitter(ports: Ports):
    """把工具的进度上报转成 `tool_progress` 事实（进度是**副作用**，不是内核特办）。"""
    def _report(call_id: str, name: str, payload: Dict[str, Any]) -> None:
        event_payload: Dict[str, Any] = {
            "call_id": str(call_id),
            "name": str(name),
            "stream": str(payload.get("stream") or "stdout"),
            "text": str(payload.get("text") or ""),
            "done": bool(payload.get("done")),
        }
        # 交互式命令在问人时，把提示一并带出去：UI 靠它弹输入条，
        # 人答完经 `/api/chat/command-input` 回到命令的 stdin。
        awaiting = payload.get("awaiting_input")
        if isinstance(awaiting, dict) and awaiting:
            event_payload["awaiting_input"] = awaiting
        ports.emit(TOOL_PROGRESS, **event_payload)

    return _report
