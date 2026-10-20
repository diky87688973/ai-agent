# -*- coding: utf-8 -*-
"""内核：模块链 + 宿主循环 + 数据契约。

四样东西：

- 数据契约：`Outcome`（模块结果的唯一形状）、`Event`（事实的形状）、
  `StreamDelta`（模型流帧）、`ToolCallRequest` / `ToolResult` / `GateDecision`；
- 端口：`Ports` / `ModelPort` / `ToolPort` / `LogicalRequest`——模块操作外界的唯一通路；
- 模块链：`ModuleBase` + 五个内置模块（输入 / 待发送队列 / 压缩 / 模型 / 工具），
  由 `build_default_chain()` 组装；`chain.py` 与 `host.py` 负责执行与回合边界；
- 会话作用域：`session_scope.py` 用 contextvar 承载"当前在哪条会话"，
  供工具与管道钩子在深层调用里解析会话级状态。

四条设计约束：

1. 控制流与数据流分离：`Outcome` 只带控制信号，数据经 `ports.emit()` 发出；
2. 模块之间零共享可变状态：模块只能通过 `Ports` 拿外部能力，拿不到别的模块；
3. 一切工具调用经唯一管道：循环本体不直接调用工具函数；
4. 事实只追加：`SessionLog` 派生历史只从已记录的事实投影（模型可见 ⟺ 已记录）。

本层不依赖 mechanisms / capabilities / shell 任何一层，反向依赖由
`scripts/check_imports.py` 扫描 AST 拦下。
"""
from __future__ import annotations

from agent.core import event_name, events, session_scope
from agent.core.chain import PassResult, run_chain, run_chain_iter, step
from agent.core.context import AppContext, ToolTurnContext
from agent.core.engine import Engine
from agent.core.event_bus import EventBus
from agent.core.events import Event, make_event
from agent.core.host import Host, TurnResult
from agent.core.model_call import StreamDelta
from agent.core.module import ModuleBase
from agent.core.modules import (
    CompressModule,
    InputModule,
    ModelModule,
    QueuedInputModule,
    ToolModule,
    build_default_chain,
)
from agent.core.outcome import Outcome
from agent.core.ports import LogicalRequest, ModelPort, Ports, ToolPort
from agent.core.session_context import SessionContext, SessionContexts
from agent.core.session_log import SessionLog, SessionLogView
from agent.core.tool_call import GateDecision, ToolCallRequest, ToolPipeline, ToolResult

__all__ = [
    "AppContext",
    "CompressModule",
    "Engine",
    "Event",
    "EventBus",
    "GateDecision",
    "Host",
    "InputModule",
    "LogicalRequest",
    "ModelModule",
    "ModelPort",
    "ModuleBase",
    "Outcome",
    "PassResult",
    "Ports",
    "QueuedInputModule",
    "SessionContext",
    "SessionContexts",
    "SessionLog",
    "SessionLogView",
    "StreamDelta",
    "ToolCallRequest",
    "ToolModule",
    "ToolPipeline",
    "ToolPort",
    "ToolResult",
    "ToolTurnContext",
    "TurnResult",
    "build_default_chain",
    "event_name",
    "events",
    "make_event",
    "run_chain",
    "run_chain_iter",
    "session_scope",
    "step",
]
