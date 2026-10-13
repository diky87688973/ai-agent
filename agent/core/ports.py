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

import sys
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from agent.core.events import Event
from agent.core.session_log import SessionLog


class ModelPort:
    """模型能力的**规则接口**：发起一次流式请求。

    实现类负责：把逻辑请求交给具体供应商、把流帧归一化后交回。
    模块**不关心**供应商是谁、线格式长什么样。
    """

    def __init__(self, provider: Any) -> None:
        self._provider = provider

    @property
    def provider(self) -> Any:
        """底层提供者（诊断 / 装配期查询用；模块逻辑不该依赖它）。"""
        return self._provider

    def name(self) -> str:
        """当前模型名（供展示与日志；取不到时空串）。"""
        return str(getattr(self._provider, "model", "") or "")

    def name_for(self, request: Any) -> str:
        """**本次请求实际会用的**模型名：请求里指定了就报它，否则报实例默认。"""
        want = str(getattr(request, "model", "") or "").strip()
        return want or self.name()

    def stream(self, request: Any):
        """发起流式请求，逐个产出归一化的流帧。"""
        return self._provider.stream(request)


class ToolPort:
    """工具能力的**规则接口**：执行一次工具调用。

    实现类保证"工具调用唯一入口"（所有调用都经管道），模块只管要结果。
    """

    def __init__(self, *, registry: Any, pipeline: Any) -> None:
        self._registry = registry
        self._pipeline = pipeline

    @property
    def registry(self) -> Any:
        return self._registry

    def schemas(self) -> List[Dict[str, Any]]:
        """本轮可用的工具声明（交给模型）。"""
        if self._registry is None:
            return []
        return list(self._registry.schemas())

    def execute(self, call: Any, *, conversation_id: str = "", progress: Any = None,
                canceled: Any = None, tool_call_id: str = "") -> Any:
        """执行一次调用，返回 `ToolResult`。

        `conversation_id` / `progress` / `canceled` 是管道需要的上下文信息，
        由模块从端口带过来 ——模块不需要自己拼一个上下文对象。
        """
        if self._pipeline is None or self._registry is None:
            raise RuntimeError("未装配工具管道")
        holder = _ToolCallScope(conversation_id=conversation_id, progress_sink=progress,
                                canceled=canceled,
                                tool_call_id=tool_call_id or str(getattr(call, "call_id", "") or ""))
        return self._pipeline.execute(self._registry, call, holder)


class _ToolCallScope:
    """管道执行期需要的最小上下文载体（会话 id + 进度出口 + 取消谓词）。

    管道是鸭子类型的：它只读 `conversation_id` / `progress_sink` /
    `app` / `session`。这里把前两个由模块带过来；后两个在模块里不经过工具上下文
    传递（能力一律走 `ToolPort`），故留空。

    `canceled`：**长时间跑的工具要能在执行中途停下来**。只靠宿主退出循环不够 ——
    子进程会继续跑到自然结束，而界面已经显示"已停止"。所以要把它一路带给工具
    （用法见 `capabilities/builtin/command_tools._pump`）。
    """

    def __init__(self, *, conversation_id: str = "", progress_sink: Any = None,
                 canceled: Any = None, tool_call_id: str = "") -> None:
        self.conversation_id = str(conversation_id or "")
        #: 本次调用的 id。交互式命令要把它拼进 stdin 通道键
        #: （`cid:tool_call_id`），否则同一会话里的多次命令调用分不清谁在等输入。
        self.tool_call_id = str(tool_call_id or "")
        self.progress_sink = progress_sink
        self._canceled = canceled
        self.app = None
        self.session = None

    def canceled(self) -> bool:
        """是否已请求停止（没有谓词时恒为 False）。"""
        if self._canceled is None:
            return False
        try:
            return bool(self._canceled())
        except Exception:
            return False


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
        extras: Optional[Dict[str, Any]] = None,
        cancel: Optional[Callable[[], bool]] = None,
        seq_allocator: Optional[Callable[[], int]] = None,
    ) -> None:
        self._emit = emit
        self._log = log
        self._cid = str(conversation_id or "")
        self._model = model
        self._tools = tools
        self._extras = dict(extras or {})
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
            print(f"[core] 分配存储坐标失败（本事件将无法断线续传）："
                  f"{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)

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
        工具模块逐调用问（不启动新调用）。谓词异常一律当"未取消"——
        取消是增强项，不能让回合因它出错。
        """
        if self._cancel is None:
            return False
        try:
            return bool(self._cancel())
        except Exception:
            return False

    def extras(self, key: str, default: Any = None) -> Any:
        """装配期传入的附加数据（**数据**，不是能力）。

        给"确实无法静态声明"的装配参数留一个口子；能力一律走上面的端口属性。
        """
        return self._extras.get(key, default)

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
    #: 会话身份：provider 侧把它过滤成官方 `user` 字段下发。
    conversation_id: str = ""
    #: 本次请求所用的系统提示。provider 侧在"带图却被否认"时用它 + 当前用户消息
    #: 组成**最小上下文**重试：历史里"我看不到图片"的断言会像 few-shot 一样
    #: 把后续每轮都锚死在否认上，丢掉历史才能让视觉重新生效。
    system: str = ""
