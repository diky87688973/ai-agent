# -*- coding: utf-8 -*-
"""端口（`Ports`）：模块操作外界的**唯一**通路。

**模块不直接碰上下文**（不许 `ctx.xxx = xxx`），
只能调**有类型的规则接口**；**接口编程锁行为，实现交给实现类**。
模块之间因此依赖**同一个接口**而不是某个字段名——耦合从隐式变显式，换实现时
接口不变就换得动。

三件事在这里收口：

1. **事实出口**：`ports.log`——读事实（派生成模型消息）、追加事实。
   追加即"落到事实源"，宿主不需要额外的落盘步骤。
2. **事件出口**：`ports.emit(...)`——模块**唯一**的数据产出通道。
   返回值只带控制信号，数据一律走这里（"控制流走返回值，数据流走事件"）。
3. **能力入口**：`ports.model()` / `ports.tools()`——按**类型**取能力。
   **不提供** `get("某个字符串名")` 那种服务定位器：那会把具体机制名写进内核。
   能用端口表达的一律走端口。

**`Ports` 没有可写字段**：模块拿不到上下文对象本身，也就无法绕过端口去读写。
"接口编程锁定业务行为"落在这条上。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterator, List, Optional, Protocol

from agent.core.error_report import report_error
from agent.core.events import Event
from agent.core.model_call import StreamDelta
from agent.core.session_log import SessionLog
from agent.core.tool_call import ToolCallRequest, ToolResult

#: 进度上报出口：`(tool_call_id, tool_name, payload)`。
ProgressSink = Callable[[str, str, Dict[str, Any]], None]
#: 协作式取消检查：返回 True 表示宿主已请求停止。
CancelCheck = Callable[[], bool]


class ProviderPort(Protocol):
    """模型提供者的**结构契约**（装配侧注入，内核只按这个形状用）。

    不 import 具体 provider：`mechanisms` 可以换实现，内核的端口签名不变。
    """

    model: str

    def stream(self, request: "LogicalRequest") -> Iterator[StreamDelta]:
        ...


class RegistryPort(Protocol):
    """工具注册表的结构契约：本轮可用的工具声明。"""

    def schemas(self) -> List[Dict[str, Any]]:
        ...


class PipelinePort(Protocol):
    """工具管道的结构契约：唯一执行入口。"""

    def execute(self, registry: RegistryPort, call: ToolCallRequest,
                ctx: "_ToolCallScope") -> ToolResult:
        ...


class SessionsPort(Protocol):
    """会话注册表的结构契约：按会话 id 解析运行态。"""

    def resolve_sync(self, conversation_id: str) -> Any:
        ...



class ModelPort:
    """模型能力的**规则接口**：发起一次流式请求。

    实现类负责：把逻辑请求交给具体供应商、把流帧归一化后交回。
    模块**不关心**供应商是谁、线格式长什么样。
    """

    def __init__(self, provider: ProviderPort) -> None:
        self._provider = provider

    @property
    def provider(self) -> ProviderPort:
        """底层提供者（诊断 / 装配期查询用；模块逻辑不该依赖它）。"""
        return self._provider

    def name(self) -> str:
        """当前模型名（供展示与日志；取不到时空串）。"""
        return str(getattr(self._provider, "model", "") or "")

    def name_for(self, request: "LogicalRequest") -> str:
        """**本次请求实际会用的**模型名：请求里指定了就报它，否则报实例默认。"""
        want = str(getattr(request, "model", "") or "").strip()
        return want or self.name()

    def stream(self, request: "LogicalRequest") -> Iterator[StreamDelta]:
        """发起流式请求，逐个产出归一化的流帧。"""
        return self._provider.stream(request)


class ToolPort:
    """工具能力的**规则接口**：执行一次工具调用。

    实现类保证"工具调用唯一入口"（所有调用都经管道），模块只管要结果。
    装配时注入进程级 `app` 与会话注册表 `sessions`，执行期写入管道上下文，
    工具经 `current_context().session.gate` 取会话门控。
    """

    def __init__(
        self,
        *,
        registry: Optional[RegistryPort],
        pipeline: Optional[PipelinePort],
        app: Any = None,
        sessions: Optional[SessionsPort] = None,
    ) -> None:
        self._registry = registry
        self._pipeline = pipeline
        self._app = app
        self._sessions = sessions

    @property
    def registry(self) -> Optional[RegistryPort]:
        return self._registry

    def schemas(self) -> List[Dict[str, Any]]:
        """本轮可用的工具声明（交给模型）。"""
        if self._registry is None:
            return []
        return list(self._registry.schemas())

    def execute(self, call: ToolCallRequest, *, conversation_id: str = "",
                progress: Optional[ProgressSink] = None,
                canceled: Optional[CancelCheck] = None,
                tool_call_id: str = "") -> ToolResult:
        """执行一次调用，返回 `ToolResult`。

        `conversation_id` / `progress` / `canceled` 由模块从端口带过来；
        `app` / `session` 由本端口在执行期填入管道上下文。
        """
        if self._pipeline is None or self._registry is None:
            raise RuntimeError("未装配工具管道")
        cid = str(conversation_id or "")
        session = None
        if self._sessions is not None:
            resolve = getattr(self._sessions, "resolve_sync", None)
            if callable(resolve):
                session = resolve(cid)
        holder = _ToolCallScope(
            conversation_id=cid,
            progress_sink=progress,
            canceled=canceled,
            tool_call_id=tool_call_id or str(getattr(call, "call_id", "") or ""),
            app=self._app,
            session=session,
        )
        return self._pipeline.execute(self._registry, call, holder)


class _ToolCallScope:
    """管道执行期上下文：会话 id、进度出口、停止检查、进程级 app、会话桶。

    管道只读这些字段；`app` / `session` 由 `ToolPort` 在 `execute` 时填入，
    供 `ToolTurnContext` 与 `current_context()` 使用。

    `canceled`：长时间跑的工具在执行中途查询（见 `command_tools._pump`）。
    """

    def __init__(
        self,
        *,
        conversation_id: str = "",
        progress_sink: Optional[ProgressSink] = None,
        canceled: Optional[CancelCheck] = None,
        tool_call_id: str = "",
        app: Any = None,
        session: Any = None,
    ) -> None:
        self.conversation_id = str(conversation_id or "")
        #: 本次调用的 id。交互式命令拼进 stdin 通道键（`cid:tool_call_id`）。
        self.tool_call_id = str(tool_call_id or "")
        self.progress_sink = progress_sink
        self._canceled = canceled
        self.app = app
        self.session = session

    def canceled(self) -> bool:
        """是否已请求停止（没传入检查函数时恒为 False）。"""
        if self._canceled is None:
            return False
        return bool(self._canceled())


class Ports:
    """一次模块执行能拿到的**全部**入口。

    刻意设计成"只能调，不能改"：模块拿不到上下文对象本身，也就无法绕过端口读写。
    """

    def __init__(
        self,
        *,
        emit: Callable[[Event], None],
        log: SessionLog,
        conversation_id: str = "",
        model: Optional[ModelPort] = None,
        tools: Optional[ToolPort] = None,
        cancel: Optional[Callable[[], bool]] = None,
        seq_allocator: Optional[Callable[[], int]] = None,
    ) -> None:
        self._emit = emit
        self._log = log
        self._cid = str(conversation_id or "")
        self._model = model
        self._tools = tools
        self._cancel = cancel
        #: 分配**全局存储坐标**（`store.allocate_seq`）。core 不感知 store，
        #: 所以由装配方注入"分配一个号"的能力。坐标必须在 **emit 产出瞬间**标好
        #: ——事件一产出即发布到总线，落盘在其后；后补坐标会让订阅者拿到的帧
        #: 没有 `id:`，浏览器就不会回传 `Last-Event-ID`，**断线续传静默失效**
        #: （全部帧无坐标）。
        self._seq_allocator = seq_allocator

    # ── 事实（读 + 追加）──────────────────────────────────

    @property
    def log(self) -> SessionLog:
        """会话事实日志的**只读视图**：读它派生成模型消息。

        要落事实请用 `self.emit(...)` —— 那条路**同时**入日志与通知观察面。
        直接追加会造成"模型看得见、观察面看不见"的秘密事实。
        """
        return self._log.readonly() if hasattr(self._log, "readonly") else self._log

    @property
    def conversation_id(self) -> str:
        return self._cid

    def emit(self, type_: str, **data: Any) -> Event:
        """产出一件事实：**先入日志，再出事件**（模型可见 ⟺ 已记录）。

        顺序不可颠倒——实时订阅者看到的事实，已经能被"重新读取"还原出来，
        否则断线重连就会看到历史里没有的东西。
        """
        payload = dict(data)
        if self._cid:
            payload.setdefault("conversation_id", self._cid)
        self._stamp_seq(payload)
        event = Event(type_, payload)
        self._log.append([event])
        self._emit(event)
        return event

    def _stamp_seq(self, payload: Dict[str, Any]) -> None:
        """给事实标上全局存储坐标（`_seq`）。分配失败不阻断——坐标是增强项。"""
        if self._seq_allocator is None or "_seq" in payload:
            return
        try:
            payload["_seq"] = int(self._seq_allocator())
        except Exception as exc:
            # 不阻断回合，但**必须留痕**：没有坐标意味着这个事件的续传能力丢了。
            report_error("core.seq_alloc", exc)

    # ── 能力（按类型，不按字符串名）───────────────────────

    @property
    def model_port(self) -> Optional[ModelPort]:
        return self._model

    @property
    def tool_port(self) -> Optional[ToolPort]:
        return self._tools

    def canceled(self) -> bool:
        """宿主是否已请求停止（**协作式取消**）。

        模块在自认为合适的粒度问它：模型模块逐帧问（长回答能被立刻打断），
        工具模块逐调用问（不启动新调用）。检查函数自身出错必须把异常抛出去。
        """
        if self._cancel is None:
            return False
        return bool(self._cancel())


@dataclass(slots=True)
class LogicalRequest:
    """与模型无关的请求—— **端口契约**，provider 侧消费它。

    它是"内核 → provider"的端口契约：消费者只有 `modules.py`（构造）与 provider（消费），
    不属于任何一段回合循环。

    `effort`：推理档位（"high" | "max"），由会话级设置解析而来。
    provider 侧把它放进请求体的 `reasoning_effort`；不支持该参数的 provider 自行剥离。

    `model`：**本次请求要用哪个模型**，由会话级设置解析而来。空串表示"用 provider
    自己的默认模型"（不传即沿用实例默认，行为不变）。
    模型是**请求级**的：一个 provider 实例绑定一个
    base_url / key，但同一个网关下往往有多个模型名可选；把它放进请求，provider 便可复用，不必按模型各建一个实例。
    """

    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    effort: str = "high"
    model: str = ""
    #: 本轮在 `messages` 里的起始下标（含）：该下标之前的消息属于**已结束的轮次**，
    #: provider 可以据此丢掉它们的 `reasoning_content`（见 model_provider 的同名处理）。
    #: None = 不知道边界，按原样下发。
    turn_start: Optional[int] = None
    #: 会话身份：provider 侧把它过滤成官方 `user` 字段下发。
    conversation_id: str = ""
