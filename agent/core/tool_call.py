# -*- coding: utf-8 -*-
"""工具调用协议：数据结构 + 唯一执行管道。

纪律：任何工具调用（模型发起、脚本发起、协作触发）必须经 ToolPipeline.execute，
没有第二条路径；门控与观察者以有序链挂在管道内。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from agent.core.context import ToolTurnContext
from agent.core.session_scope import (
    reset_progress_reporter,
    reset_session_scope,
    reset_tool_turn_context,
    set_progress_reporter,
    set_session_scope,
    set_tool_turn_context,
)


@dataclass(slots=True)
class ToolCallRequest:
    """单次工具调用（模型发起 → 执行管道）。"""

    call_id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    parallel_safe: bool = False


@dataclass(slots=True)
class ToolResult:
    """结果信封（管道 → 回合循环），沿用 ok/data/error 习惯。"""

    call_id: str
    ok: bool
    data: Any = None
    error: str = ""
    # 工具随结果附带的图片附件（`[{"mime":…, "data_base64":…}]`）。
    #
    # 独立字段，不并入 `data`：`data` 会落到事件流并 `json.dumps`，
    # base64 计入每次事件序列化的体积。派生对话时由 `SessionLogView`
    # 把它翻成 `image_url` 块。
    #
    # 由 `ToolResult.attach(...)` 构造，见该方法。
    attachments: list = field(default_factory=list)

    @staticmethod
    def attach(data: Any, attachments: Any) -> "ToolResult":
        """带附件的成功结果。

        管道读取返回值上的 `attachments` 属性并搬进结果信封，
        所以工具无须提供 `call_id`。
        """
        result = ToolResult(call_id="", ok=True, data=data)
        result.attachments = list(attachments or [])
        return result

    # 允许以元组 `(ToolResult, attachments)` 回传（旧式工具少改一处）
    # 由管道统一归一化，工具侧只认 `attach`。
    # 工具声明"这一轮必须停下等用户在宿主界面作答"（如 `user_confirm` 首段）。
    # 由工具异常上的 `await_user` 属性带上（`tasks.confirm.UserConfirmRequired` 即此类异常），
    # 回合循环据此暂停——否则模型会把 `ok=False` 读成失败并反复重试。
    await_user: bool = False
    # 这次调用还没有返回（两段式首段：等用户在宿主界面作答）。
    # 与 `await_user` 的区别：`await_user` 是"回合要停下"，
    # `deferred` 标记调用尚未返回，结果不写入事实流——一个还没返回的调用不该有结果记录，
    # 否则同一个 `tool_call_id` 会先后出现两条 `tool_result`（待定的 + 用户作答后的），
    # 模型 API 直接拒绝：`Messages with role 'tool' must be a response to a preceding
    # message with 'tool_calls'`（400）。
    deferred: bool = False


@dataclass(slots=True)
class GateDecision:
    """门控决策：放行 / 拒绝（附结构化原因，可直接指导修复）。"""

    allow: bool = True
    reason: str = ""


PreGate = Callable[[ToolCallRequest, Any], Optional[GateDecision]]
PostObserver = Callable[[ToolCallRequest, ToolResult, Any], None]


class ToolPipeline:
    """工具执行唯一入口：pre 门控（有序）→ 执行 → post 观察（有序）。"""

    def __init__(self) -> None:
        self._pre: list[PreGate] = []
        self._post: list[PostObserver] = []

    def add_pre(self, gate: PreGate) -> Callable[[], None]:
        """注册前置门控；返回注销句柄。"""
        self._pre.append(gate)
        return lambda: self._pre.remove(gate)

    def add_post(self, observer: PostObserver) -> Callable[[], None]:
        """注册后置观察者；返回注销句柄。"""
        self._post.append(observer)
        return lambda: self._post.remove(observer)

    def _pre_result(self, call: ToolCallRequest, ctx: Any) -> ToolResult | None:
        for gate in list(self._pre):
            decision = gate(call, ctx)
            if decision is not None and not decision.allow:
                return ToolResult(
                    call_id=call.call_id, ok=False,
                    error=decision.reason or "被门控拒绝")
        return None

    def _binding_result(self, registry: Any, call: ToolCallRequest) -> ToolResult:
        binding = registry.get(call.name)
        if binding is None:
            return ToolResult(
                call_id=call.call_id, ok=False, error=f"未知工具：{call.name}")
        try:
            data = binding.execute(dict(call.arguments))
            carried = getattr(data, "attachments", None)
            if isinstance(data, ToolResult):
                inner = data
                result = ToolResult(
                    call_id=call.call_id, ok=bool(inner.ok), data=inner.data,
                    error=str(inner.error or ""))
                carried = inner.attachments
            else:
                result = ToolResult(call_id=call.call_id, ok=True, data=data)
            if isinstance(carried, list) and carried:
                result.attachments = list(carried)
            return result
        except Exception as exc:
            awaiting = bool(getattr(exc, "await_user", False))
            result = ToolResult(
                call_id=call.call_id, ok=False,
                data=getattr(exc, "data", None),
                error=f"{type(exc).__name__}: {exc}",
                await_user=awaiting, deferred=awaiting)
            return result

    def _post_observe(self, call: ToolCallRequest, result: ToolResult, ctx: Any) -> None:
        for observer in list(self._post):
            observer(call, result, ctx)

    def execute(self, registry: Any, call: ToolCallRequest, ctx: Any) -> ToolResult:
        """唯一执行入口；上下文、门控、执行、观察按顺序收口。"""
        cid = str(getattr(ctx, "conversation_id", "") or "") if ctx is not None else ""
        token = set_session_scope(cid)
        sink = getattr(ctx, "progress_sink", None) if ctx is not None else None
        reporter = None
        if callable(sink):
            call_id, name = call.call_id, call.name
            def reporter(payload: dict) -> None:
                sink(call_id, name, payload)
        progress_token = set_progress_reporter(reporter)
        turn_ctx = ToolTurnContext(
            app=getattr(ctx, "app", None), session=getattr(ctx, "session", None),
            turn=ctx, call=call, progress=reporter)
        context_token = set_tool_turn_context(turn_ctx)
        try:
            blocked = self._pre_result(call, ctx)
            if blocked is not None:
                return blocked
            result = self._binding_result(registry, call)
            self._post_observe(call, result, ctx)
            return result
        finally:
            reset_tool_turn_context(context_token)
            reset_progress_reporter(progress_token)
            reset_session_scope(token)
