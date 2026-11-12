# -*- coding: utf-8 -*-
"""模型模块：流式调用模型并落 model_message。"""
from __future__ import annotations

from http.client import RemoteDisconnected
from time import perf_counter, sleep
from typing import Any, Dict, Iterator, List, Optional

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
from agent.core.model_call import PROVIDER_META_KEY
from agent.core.module import ModuleBase
from agent.core.modules.assemble import assemble_with, reasoning_budget_for, segment_snapshot
from agent.core.modules.dialogue import prepare_dialogue
from agent.core.modules.mode_note import (
    resolve_runtime_note,
    strip_mode_tail,
    with_mode_note,
)
from agent.core.modules.queued_input_mod import insertion_waiting
from agent.core.modules.tool_facts import serialize_call, tail_expects_model
from agent.core.outcome import Outcome
from agent.core.ports import LogicalRequest, Ports
from agent.core.session_log import ensure_tool_pairs
from agent.core.state_values import (
    LLM_CANCELED as LLM_STATUS_CANCELED,
)
from agent.core.state_values import (
    LLM_DONE as LLM_STATUS_DONE,
)
from agent.core.state_values import (
    LLM_FAILED as LLM_STATUS_FAILED,
)
from agent.core.tool_call import ToolCallRequest

#: `RemoteDisconnected` 只会在 HTTP 状态行之前出现；流开始后断流不能重放。
REMOTE_DISCONNECTED_MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = (0.1, 0.2, 0.4, 0.8, 1.6)


def _reasoning_ms(started: float, last_at: Optional[float]) -> int:
    """推理流最后一个增量的时间点；没有推理增量时返回 -1。"""
    if last_at is None:
        return -1
    return max(0, int((last_at - started) * 1000))


def _turn_start_index(messages: list[dict], anchor: dict | None) -> int:
    """Locate the original user message after hooks and tool pairing move messages."""
    if anchor is None:
        return 0
    for index, message in enumerate(messages):
        if message is anchor:
            return index
    # A hook can copy messages. Prefer the first matching copy to avoid dropping
    # the current tool turn's reasoning if equal user messages are present.
    return next((index for index, message in enumerate(messages) if message == anchor), 0)


class ModelModule(ModuleBase):
    """调用模型；增量边到边出（`yield`），本步结论落成 `model_message` 事实。

    什么时候该跑：只看事实末端——
      - 末端是新用户输入（`input_claimed`）→ 该跑；
      - 末端是未消费的工具结果（`tool_result`）→ 该跑（模型得看结果）；
      - 末端已是模型自己的消息 → 不跑，返回 `ok`。

    模型与工具交替推进，每次推进都把新事实追加到末端，
    所以看末端是谁就能判断该不该跑，不需要额外的记账。

    不要求续行：模型只负责"说话"；"还要不要再执行一次工具往返"是工具模块的语义
    （它是收尾模块）。
    """

    name = "model"
    requires = ("model_port",)

    def __init__(self, *, context: Any = None, compactor: Any = None,
                 effort: str = "high", model: str = "",
                 image_turns: int = KEEP_IMAGE_TURNS,
                 image_max: int = MAX_EMBED_IMAGES,
                 mode_note: Any = "", context_hooks: Any = None,
                 queued_input: Any = None) -> None:
        self._queued_input = queued_input
        self.context_pass = context
        self._compactor = compactor
        self._effort = str(effort or "high")
        #: 本次请求要用哪个模型（空串 = 用 provider 的默认）。
        #: 与 `effort` 同源：都在每个回合装配引擎时由会话级设置解析而来。
        self._model = str(model or "")
        #: 只把最近这么多轮用户发言里的图带进请求；负数 = 不限。
        #: 缺省 1 轮：截图体积大，历史全带会撞上游请求体上限。
        self._image_turns = int(image_turns)
        #: 这些轮里最多带几张图；负数 = 不限。缺省 8，最近一轮优先保。
        self._image_max = int(image_max)
        #: 执行模式说明：只加在发给模型的这一份请求尾部，不落记录、不发事件。
        #: 放在最后一项是为了让切模式只影响尾部这一条，前面的前缀缓存照旧命中。
        self._mode_note = mode_note
        #: 完整上下文拼装钩子；内核在请求发出前按序调用，插件只返回新消息列表。
        self._context_hooks = context_hooks

    def _covered_end(self) -> int:
        """已覆盖前缀长度（压缩器维护）；没有压缩器就是 0。"""
        value = getattr(self._compactor, "view_start", getattr(self._compactor, "covered_end", 0))
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    def _build_request(self, ports: Ports):
        runtime_note = resolve_runtime_note(self._mode_note)
        wake_derive = getattr(
            ports.log, "derive_request_messages_from_latest_wake", None)
        wake_messages = wake_derive() if callable(wake_derive) else None
        isolated_wake = wake_messages is not None
        request_messages = (wake_messages if isolated_wake
                            else ports.log.derive_request_messages())
        dialogue = prepare_dialogue(
            request_messages, self._image_turns, self._image_max)
        tools = ports.tool_port.schemas() if ports.tool_port is not None else []
        reasoning_budget = reasoning_budget_for(ports, self._model, dialogue, tools)
        if self.context_pass is not None:
            assembled = assemble_with(self.context_pass, dialogue, runtime_note,
                                       0 if isolated_wake else self._covered_end(),
                                       include_summary=not isolated_wake,
                                       reasoning_budget=reasoning_budget)
            if assembled is None:
                report_error("core.model", "上下文缺装配能力（本回合请求可能缺系统前缀）")
                messages = with_mode_note(dialogue, runtime_note)
            else:
                messages = assembled
        else:
            messages = with_mode_note(dialogue, runtime_note)
        pre_hook = list(messages)
        turn_anchor = next((message for message in reversed(pre_hook)
                            if message.get("role") == "user"), None)
        if self._context_hooks is not None:
            messages = self._context_hooks.apply(
                messages, str(getattr(ports, "conversation_id", "") or ""))
        messages = ensure_tool_pairs(messages)
        request = LogicalRequest(
            messages=messages,
            tools=tools,
            effort=self._effort, model=self._model,
            turn_start=_turn_start_index(messages, turn_anchor),
            conversation_id=str(getattr(ports, "conversation_id", "") or ""))
        budget = 0
        try:
            budget = int(getattr(self._compactor, "summary_token_threshold", 0) or 0)
        except (TypeError, ValueError):
            budget = 0
        segments = segment_snapshot(self.context_pass, messages, budget_tokens=budget)
        remember = getattr(self._compactor, "remember_sent_request", None)
        if callable(remember) and not isolated_wake:
            prefix = strip_mode_tail(messages[:len(pre_hook)], runtime_note)
            remember(messages, prefix, request.tools)
        return request, messages, segments

    @staticmethod
    def _wait_for_retry(ports, delay: float) -> bool:
        """退避等待；以 50ms 为步长检查取消，返回是否应停止。"""
        remaining = max(0.0, float(delay))
        while remaining > 0:
            if ports.canceled():
                return True
            step = min(0.05, remaining)
            sleep(step)
            remaining -= step
        return ports.canceled()

    def _cancel_events(self, ports, model, request, started, reasoning_last_at,
                       chunks, retries, *, reason="CanceledByUser"):
        """取消时的两条终止事件。只发事件；是否停止由调用方决定。"""
        yield ports.emit(LLM_FAILED, model=model.name_for(request) or "",
                         error=reason,
                         elapsed_ms=int((perf_counter() - started) * 1000),
                         reasoning_ms=_reasoning_ms(started, reasoning_last_at),
                         chunks=chunks, retries=retries)
        yield ports.emit(LLM_ENDED, model=model.name_for(request) or "",
                         status=LLM_STATUS_CANCELED,
                         elapsed_ms=int((perf_counter() - started) * 1000),
                         reasoning_ms=_reasoning_ms(started, reasoning_last_at),
                         chunks=chunks, retries=retries)

    def _fail_events(self, ports, model, request, failure, elapsed, reasoning_ms,
                     chunks, retries):
        """失败时的两条终止事件。只发事件；返回什么由调用方决定。"""
        name = model.name_for(request) or ""
        yield ports.emit(LLM_FAILED, model=name, error=failure, elapsed_ms=elapsed,
                         reasoning_ms=reasoning_ms, chunks=chunks, retries=retries)
        yield ports.emit(LLM_ENDED, model=name, status=LLM_STATUS_FAILED,
                         elapsed_ms=elapsed, reasoning_ms=reasoning_ms,
                         chunks=chunks, retries=retries)

    def _stream(self, ports, model, request):
        started = perf_counter()
        first_chunk_ms = None
        reasoning_last_at = None
        chunks = 0
        text_parts: List[str] = []
        reasoning_parts: List[str] = []
        tool_calls: List[ToolCallRequest] = []
        usage: Dict[str, Any] = {}
        provider_meta: Dict[str, Any] = {}
        failure = ""
        retries = 0
        while True:
            if ports.canceled():
                yield from self._cancel_events(
                    ports, model, request, started, reasoning_last_at, chunks, retries)
                return {"stopped": True}
            if insertion_waiting(self._queued_input, ports.conversation_id):
                yield from self._cancel_events(
                    ports, model, request, started, reasoning_last_at,
                    chunks, retries, reason="InputInserted")
                return {"insert_pending": True}
            try:
                for delta in model.stream(request):
                    if ports.canceled():
                        yield from self._cancel_events(
                            ports, model, request, started, reasoning_last_at,
                            chunks, retries)
                        return {"stopped": True, "failure": ""}
                    chunks += 1
                    if first_chunk_ms is None:
                        first_chunk_ms = int((perf_counter() - started) * 1000)
                    kind = str(getattr(delta, "kind", "") or "")
                    if kind == "text":
                        text_parts.append(str(delta.text or ""))
                        yield ports.emit(ASSISTANT_DELTA, text=str(delta.text or ""))
                    elif kind == "reasoning":
                        reasoning_parts.append(str(delta.text or ""))
                        reasoning_last_at = perf_counter()
                        yield ports.emit(REASONING_DELTA, text=str(delta.text or ""))
                    elif kind == "tool_call" and getattr(delta, "tool_call", None) is not None:
                        tool_calls.append(delta.tool_call)
                    elif kind == "meta" and getattr(delta, "meta", None):
                        provider_meta.update(delta.meta)
                    elif kind == "usage" and getattr(delta, "usage", None):
                        usage = dict(delta.usage)
                break
            except Exception as exc:
                retryable = isinstance(exc, RemoteDisconnected) and chunks == 0
                if retryable and retries < REMOTE_DISCONNECTED_MAX_RETRIES:
                    delay = RETRY_BACKOFF_SECONDS[min(
                        retries, len(RETRY_BACKOFF_SECONDS) - 1)]
                    retries += 1
                    if self._wait_for_retry(ports, delay):
                        yield from self._cancel_events(
                            ports, model, request, started, reasoning_last_at,
                            chunks, retries)
                        return {"stopped": True, "failure": ""}
                    continue
                failure = f"{type(exc).__name__}: {exc}"
                report_error("core.model", exc, retries=retries)
                break
        elapsed = int((perf_counter() - started) * 1000)
        reasoning_ms = _reasoning_ms(started, reasoning_last_at)
        name = model.name_for(request) or ""
        if failure:
            yield from self._fail_events(ports, model, request, failure,
                                         elapsed, reasoning_ms, chunks, retries)
            return {"stopped": False, "failure": failure, "retries": retries}
        if ports.canceled():
            yield from self._cancel_events(
                ports, model, request, started, reasoning_last_at, chunks, retries)
            return {"stopped": True, "failure": ""}
        yield from self._stream_done(ports, name, elapsed, first_chunk_ms, reasoning_ms,
                                     chunks, len(tool_calls), retries, usage)
        return {"stopped": False, "failure": "", "retries": retries,
                "text_parts": text_parts,
                "reasoning_parts": reasoning_parts, "tool_calls": tool_calls,
                "provider_meta": provider_meta}

    def _stream_done(self, ports, name, elapsed, first_chunk_ms, reasoning_ms,
                     chunks, tool_count, retries, usage):
        yield ports.emit(LLM_DONE, model=name, elapsed_ms=elapsed,
                         first_chunk_ms=(first_chunk_ms if first_chunk_ms is not None else -1),
                         reasoning_ms=reasoning_ms, chunks=chunks,
                         tool_calls=tool_count, retries=retries)
        yield ports.emit(LLM_ENDED, model=name, status=LLM_STATUS_DONE,
                         elapsed_ms=elapsed, reasoning_ms=reasoning_ms,
                         chunks=chunks, tool_calls=tool_count, retries=retries)
        if usage:
            yield ports.emit(USAGE, **usage)

    def execute(self, ports: Ports) -> Iterator[Any]:
        if insertion_waiting(self._queued_input, ports.conversation_id):
            return Outcome.next()
        if not tail_expects_model(ports.log):
            return Outcome.ok()
        model = ports.model_port
        if model is None:
            yield ports.emit(ERROR, where="model", detail="未装配模型端口")
            return Outcome.halt("未装配模型端口")
        request, messages, segments = self._build_request(ports)
        if insertion_waiting(self._queued_input, ports.conversation_id):
            return Outcome.next()
        if segments is not None:
            yield ports.emit(CONTEXT_SEGMENTS, **segments)
        yield ports.emit(LLM_STARTED, model=model.name_for(request) or "",
                         effort=self._effort, messages=len(messages),
                         tools=len(request.tools or []))
        state = yield from self._stream(ports, model, request)
        if state.get("stopped"):
            return Outcome.stopped("用户请求停止")
        if state.get("insert_pending"):
            return Outcome.next()
        failure = str(state.get("failure") or "")
        if failure:
            retries = int(state.get("retries") or 0)
            detail = (f"{failure}；重试 {retries} 次" if retries else failure)
            yield ports.emit(ERROR, where="model", detail=detail)
            return Outcome.halt(f"模型调用失败：{failure}")
        message_data: Dict[str, Any] = {
            "content": "".join(state["text_parts"]),
            "tool_calls": [serialize_call(c) for c in state["tool_calls"]],
        }
        reasoning = "".join(state["reasoning_parts"])
        if reasoning:
            message_data["reasoning_content"] = reasoning
        if state["provider_meta"]:
            message_data[PROVIDER_META_KEY] = state["provider_meta"]
        yield ports.emit(MODEL_MESSAGE, **message_data)
        return Outcome.ok()
