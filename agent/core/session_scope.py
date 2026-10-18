# -*- coding: utf-8 -*-
"""会话 / 轮次作用域 — 工具取上下文的唯一通路，以及进度上报通道。

`ToolPipeline.execute` 在调用期把该轮次的上下文摆进 contextvar：
- `current_session_id()`：会话 id；
- `current_context()`：完整的 `ToolTurnContext`——进程级 AppContext + 会话级
  SessionContext + 回合级上下文 + 本次调用。

两条通路并存：cid 是最常用的一个字段，单独留一条最简通路省掉到处 `getattr`；
而完整上下文让工具显式拿到会话态（`session.gate` / `session.live` /
`session.pending_confirm`）与全局服务（`ctx.service(NAME)`），不必再在构造期注入
"能摸到会话态的函数"。调用结束还原，不跨调用泄漏。

进度通道（`tool_progress` 事实）：工具不能直接发事件——那会绕开
事件流的唯一时序。它只能"报告一段输出"，由管道决定是否转成事件。所以这里是
一个单向回调：`emit_progress` 报告，`set_progress_reporter` 装配，未装配时静默丢弃。
"""
from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any, Callable, Optional

_CURRENT: ContextVar[str] = ContextVar("fan_agent_session_id", default="")
_REPORTER: ContextVar[Optional[Callable[[dict], None]]] = ContextVar(
    "fan_agent_progress_reporter", default=None
)
_CONTEXT: ContextVar[Any] = ContextVar("fan_agent_tool_turn_context", default=None)


def set_session_scope(conversation_id: str) -> Token:
    """进入会话作用域（返回还原 token）；由 ToolPipeline.execute 调用。"""
    return _CURRENT.set(str(conversation_id or ""))


def reset_session_scope(token: Token) -> None:
    """退出会话作用域（还原到进入前）。"""
    _CURRENT.reset(token)


def current_session_id() -> str:
    """当前会话 ID；无作用域时返回空串。"""
    return _CURRENT.get()


def set_tool_turn_context(ctx: Any) -> Token:
    """装配本工具轮次的上下文（返回还原 token）；由 ToolPipeline.execute 调用。"""
    return _CONTEXT.set(ctx)


def reset_tool_turn_context(token: Token) -> None:
    """退出工具轮次作用域。"""
    _CONTEXT.reset(token)


def current_context() -> Any:
    """当前工具轮次的 `ToolTurnContext`；不在工具轮次内时返回 None。

    工具用它拿会话态与全局服务，例如：::

        ctx = current_context()
        gate = ctx.session.gate if ctx is not None and ctx.session else None
    """
    return _CONTEXT.get()


def set_progress_reporter(reporter: Optional[Callable[[dict], None]]) -> Token:
    """装配进度上报器（返回还原 token）；由 ToolPipeline.execute 调用。"""
    return _REPORTER.set(reporter)


def reset_progress_reporter(token: Token) -> None:
    """退出进度上报作用域。"""
    _REPORTER.reset(token)


def current_progress_reporter() -> Optional[Callable[[dict], None]]:
    """取出当前上报器（可为 None）。

    给子线程用：`contextvars` 不会自动传进 `threading.Thread`，线程里调
    `emit_progress` 会拿到默认值（None）而静默丢弃。所以开线程前先在当前上下文取出
    上报器，把它作为参数传进去，由线程显式调用。
    """
    return _REPORTER.get()


def emit_progress(
    *,
    stream: str = "stdout",
    text: str = "",
    done: bool = False,
    **extra: Any,
) -> None:
    """报告一段工具输出（工具侧唯一的进度出口）。

    未装配上报器时静默丢弃——工具不该关心有没有人在看。
    上报器异常同样吞掉：进度是增强项，不得让工具执行失败。
    """
    reporter = _REPORTER.get()
    if reporter is None:
        return
    payload = {"stream": str(stream or "stdout"), "text": str(text or ""), "done": bool(done)}
    payload.update(extra)
    try:
        reporter(payload)
    except Exception:
        # 旁路，刻意吞掉：`reporter` 是会话级事件的观察者回调，
        # 与上面同一条判据——失败只丢"过程显示"，不丢回合结果。
        pass
