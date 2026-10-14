# -*- coding: utf-8 -*-
"""装配点：全工程唯一"知道一切"的文件。

装配纪律：工具 → 注册表，门控 → 管道，提供者 / 存储 / 上下文工厂 → 会话；事件总线 → 引擎旁路与插件订阅。
会话入口：`App.session(...)` 产出 `TurnEngine`（内核三面：开始回合 / 事件流 /
工具调用协议）；`App.run_turn(...)` 保留便捷单回合入口。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Optional

from agent.capabilities.builtin import (
    archive_tool,
    command_tools,
    commit_write,
    echo,
    edit_tools,
    fs_tools,
    geo_weather_tools,
    github_tools,
    glob_files,
    grep_files,
    locate_tools,
    ocr_tool,
    read_file,
    review_conclusion,
    session_tools,
    system_tools,
    task_tools,
    text_data_tools,
    web_tools,
    write_file,
)
from agent.capabilities.contributions import ContributionRegistry
from agent.capabilities.plugins import PluginHost
from agent.capabilities.registry import ToolRegistry
from agent.config import (
    PROJECT_ROOT,
    default_data_root,
    get_backup_retention_days,
    get_context,
    get_model_pricing,
    get_model_reasoning,
    get_plugins,
    get_reasoning_effort,
)
from agent.core.context import (
    SERVICE_CLASSIC_ADAPTER,
    SERVICE_COMPACTOR_FACTORY,
    SERVICE_CONTEXT_SOURCES,
    SERVICE_EVENT_BUS,
    SERVICE_LIVE_STATE,
    SERVICE_MESH,
    SERVICE_MODEL_PRICING,
    SERVICE_PIPELINE,
    SERVICE_PLUGIN_HOST,
    SERVICE_PROVIDER,
    SERVICE_REGISTRY,
    SERVICE_RUNNER,
    SERVICE_SESSION_CONTEXTS,
    SERVICE_SESSION_FACTORY,
    SERVICE_STORE,
    AppContext,
)
from agent.core.event_bus import EventBus
from agent.core.events import Event
from agent.core.image_embed import KEEP_IMAGE_TURNS, MAX_EMBED_IMAGES
from agent.core.session_context import SessionContexts
from agent.core.session_log import SessionLog
from agent.core.tool_call import ToolPipeline
from agent.mechanisms.context_compactor import ContextCompactor, make_provider_summarizer
from agent.mechanisms.context_pipeline import ContextPipeline, ContextSources
from agent.mechanisms.executors import ExecutorRegistry
from agent.mechanisms.file_safety import (
    FileBackups,
    Recycle,
)
from agent.mechanisms.live_state import LiveState
from agent.mechanisms.mesh import MeshState
from agent.mechanisms.model_pricing import ModelPricing
from agent.mechanisms.model_provider import EchoProvider
from agent.mechanisms.quality_gate import QualityGate, build_pipeline_gate
from agent.shell.classic_adapter import ClassicAdapter
from agent.shell.session_runner import SessionRunner


class App:
    """组装完成的底座实例（App 属性即 `context.get(name)` 的快捷方式）。

    服务一律由进程级 `AppContext` 持有与解析——本类不重复保存任何服务引用
    （避免"注册表一份、App 属性一份"的双份状态）。`dispose()` 按注册逆序清理。
    """

    def __init__(
        self,
        context: AppContext,
        *,
        context_defaults: Optional[Dict[str, Any]] = None,
        image_turns: int = KEEP_IMAGE_TURNS,
        image_max: int = MAX_EMBED_IMAGES,
    ) -> None:
        self.context = context
        self.context_defaults = dict(context_defaults or {})
        self._fallback_gate: Optional[QualityGate] = None
        #: 可选的模型 id 列表（装配时由配置注入；空 = 未配置，不做白名单校验）。
        #: 该字段只保存模型 id；凭据由 provider 持有，不下发到浏览器。
        self._available_models: list = []
        #: 只把**最近这么多轮**用户发言里的图带进请求（负数 = 不限）。
        self.image_turns = int(image_turns)
        #: 这些轮里最多带几张图（负数 = 不限）；最近一轮优先保。
        self.image_max = int(image_max)

    # ── 服务解析（进程级上下文）──

    def _svc(self, name: str) -> Any:
        """解析进程级服务；缺失服务给出装配提示（而非裸 KeyError）。"""
        try:
            return self.context.get(name)
        except KeyError as exc:
            raise KeyError(
                f"服务未注册：{name}（装配点 app.build_app 未登记该服务）"
            ) from exc

    def available_models(self) -> list:
        """可选的模型 id 列表（会话选模型只能从中挑）。

        清单为空表示"未配置多模型"，此时不做白名单校验 ——
        单模型部署不该因为没配清单就不能用。
        """
        return list(self._available_models)

    @property
    def registry(self) -> ToolRegistry:
        return self._svc(SERVICE_REGISTRY)

    @property
    def pipeline(self) -> ToolPipeline:
        return self._svc(SERVICE_PIPELINE)

    @property
    def provider(self) -> Any:
        return self._svc(SERVICE_PROVIDER)

    @property
    def store(self) -> Any:
        return self.context.get(SERVICE_STORE) if self.context.has(SERVICE_STORE) else None

    @property
    def context_factory(self) -> Optional[Callable[[str], Any]]:
        return (
            self.context.get(SERVICE_SESSION_FACTORY)
            if self.context.has(SERVICE_SESSION_FACTORY)
            else None
        )

    @property
    def live_state(self) -> Any:
        return self._svc(SERVICE_LIVE_STATE)

    @property
    def mesh(self) -> Any:
        return self._svc(SERVICE_MESH)

    @property
    def model_pricing(self) -> Any:
        """模型计价表（用量底栏的费用换算）；未注册时为 None。"""
        return self._svc(SERVICE_MODEL_PRICING)

    @property
    def plugin_host(self) -> Any:
        return self.context.get(SERVICE_PLUGIN_HOST) if self.context.has(SERVICE_PLUGIN_HOST) else None

    @property
    def event_bus(self) -> Any:
        return self.context.get(SERVICE_EVENT_BUS) if self.context.has(SERVICE_EVENT_BUS) else None

    @property
    def context_sources(self) -> Any:
        return (
            self.context.get(SERVICE_CONTEXT_SOURCES)
            if self.context.has(SERVICE_CONTEXT_SOURCES)
            else None
        )

    @property
    def compactor_factory(self) -> Optional[Callable[[str], Any]]:
        return (
            self.context.get(SERVICE_COMPACTOR_FACTORY)
            if self.context.has(SERVICE_COMPACTOR_FACTORY)
            else None
        )

    @property
    def session_contexts(self) -> Optional[SessionContexts]:
        return (
            self.context.get(SERVICE_SESSION_CONTEXTS)
            if self.context.has(SERVICE_SESSION_CONTEXTS)
            else None
        )

    @property
    def runner(self) -> Any:
        return self.context.get(SERVICE_RUNNER) if self.context.has(SERVICE_RUNNER) else None

    # ── 生命周期（进程级服务的注销通路）──

    def dispose(self) -> None:
        """进程停机：释放会话运行态，再按注册逆序注销全部服务。

        顺序要点：先释放会话上下文（否则默认桶门控在容器清空后才被取出、
        永远漏掉释放）；再 `dispose_all()` 逆序清理各注册 disposer。
        """
        # 停机补投：待落盘事实只在内存里，停机后再也不会有人触发下一批写入 ——
        # 不补这一下，关页 / 关进程就会丢掉那批。
        store = self.store
        flusher = getattr(store, "flush_all", None)
        if callable(flusher):
            try:
                written = flusher()
                if written:
                    print(f"[app] 停机补投了 {written} 条先前未落盘的事实",
                          file=sys.stderr, flush=True)
            except Exception as exc:
                # **旁路，刻意吞掉**：停机路径不能让补投失败阻断释放流程。
                print(f"[app] 停机补投失败：{type(exc).__name__}: {exc}",
                      file=sys.stderr, flush=True)
        session_contexts = self.session_contexts
        if session_contexts is not None:
            session_contexts.close_all()
        self.context.dispose_all()

    # ── 会话级门控 ──

    @property
    def gate(self) -> QualityGate:
        """默认会话桶的写盘门控（无会话作用域直调场景；每会话门控经 `gate_for` 解析）。

        读属性：容器缺失时按需求值，不缓存于实例——门控状态一律由会话注册表持有，
        避免"注册表一份、App 属性一份"的双份状态。
        """
        return self.gate_for("")

    def gate_for(self, conversation_id: str) -> QualityGate:
        """解析某会话的写盘门控；无会话装配时退化为默认桶门控（`self.gate`）。"""
        session_contexts = self.session_contexts
        if session_contexts is None:
            if self._fallback_gate is None:
                self._fallback_gate = QualityGate()
            return self._fallback_gate
        return session_contexts.resolve_sync(conversation_id).gate

    # ── 会话入口（内核三面：开始回合 / 事件流 / 工具调用协议）──

    def session(
        self,
        conversation_id: str,
        *,
        system_prompt: str = "",
        cancel: Optional[Callable[[], bool]] = None,
        inbox: Any = None,
        mode_note: str = "",
    ) -> Any:
        """创建会话引擎：装载既有记录（store 可用时）、装配上下文与持久化旁路。

        cancel：协作式取消谓词——壳层传入，内核只认"是否要求停止"。
        inbox：取队首消息的可调用对象 `(cid) -> dict | None`；缺省时用会话消息队列，
        这样"别的会话投进来的消息"不必每次由壳层显式接线。
        """
        store = self.store
        log = SessionLog()
        if store is not None and conversation_id:
            log = SessionLog(events=store.load(conversation_id))
        context = None
        context_factory = self.context_factory
        if context_factory is not None:
            context = context_factory(conversation_id)
        elif system_prompt:
            context = ContextPipeline(
                conversation_id, sources=self.context_sources, **self.context_defaults
            )
        if context is not None and system_prompt:
            context.append_system(system_prompt)
        compactor = None
        compactor_factory = self.compactor_factory
        if compactor_factory is not None:
            compactor = compactor_factory(conversation_id)
            if compactor is not None:
                compactor.restore_from_events(list(log.events))
        fact_sink = None
        if store is not None and conversation_id:
            cid = conversation_id
            fact_sink = lambda events, _cid=cid: store.append(_cid, events)

        # 入站消息出口：默认取协作网格（`MeshState`）的 inbox 队列 ——
        # 它就是 `session_send` 投递的目标队列（持久化在 `mesh/inbox/<cid>.jsonl`）。
        # 装配方显式传 `inbox` 时以传入的为准（便于替换存储）。
        try:
            mesh = self.mesh
        except Exception:
            # 判据：没装配协作网格的部署（单会话/嵌入式）不该因为"取不到 mesh"而
            # 建不出会话 —— 没有网格就是没有入站消息。
            mesh = None
        if inbox is None and mesh is not None:
            inbox = mesh.pop

        # 推理档位解析器：按会话从 live_state 取，缺省全局默认。
        state = self.live_state
        effort_resolver = (
            (lambda cid: state.get_reasoning_effort(cid)) if state is not None else None
        )
        # 本回合事件的存储坐标**按需分配**（全局单调，跨会话唯一）。
        # 坐标按需分配（回调）：工具进度事件的条数取决于工具输出长度
        # （不可预知），预留多少都可能不够，不够就会与后续回合撞号。
        # 坐标必须在 `emit` 产出瞬间就标好（事件一产出即发布到总线，落盘在其后），
        # 但 core 不感知 store，所以这里把"分配一个号"的能力注入进去。
        seq_allocator = None
        if store is not None and conversation_id:
            seq_allocator = lambda: store.allocate_seq(1)
        # 三级上下文的显式引用：上下文是数据结构，直接持有引用（不引入关系对象）。
        # 会话级：待确认状态等跨回合态的归属地；进程级：全局服务注册表。
        session_ctx = None
        if conversation_id and self.session_contexts is not None:
            session_ctx = self.session_contexts.resolve_sync(conversation_id)
        # 引擎只有一个：`Engine`，没有可选的第二条路径。
        return _build_engine(
            conversation_id=conversation_id,
            log=log,
            provider=self.provider,
            registry=self.registry,
            pipeline=self.pipeline,
            context=context,
            compactor=compactor,
            inbox=inbox,
            fact_sink=fact_sink,
            system_prompt=system_prompt,
            cancel=cancel,
            effort=str(effort_resolver(conversation_id)) if effort_resolver else "high",
            model=str(self.live_state.get_model(conversation_id) or "") if self.live_state else "",
            image_turns=self.image_turns,
            image_max=self.image_max,
            mode_note=str(mode_note or ""),
            event_sink=self.event_bus.publish if self.event_bus is not None else None,
            session_context=session_ctx,
            seq_allocator=seq_allocator,
        )

    def run_turn(self, user_text: str, conversation_id: str = "default") -> Iterator[Event]:
        """便捷入口：单回合（新建会话引擎；无 store / 上下文时按无状态路径运行）。"""
        yield from self.session(conversation_id).start_turn(user_text)



def _build_engine(
    *,
    conversation_id: str,
    log: Any,
    provider: Any = None,
    registry: Any = None,
    pipeline: Any = None,
    context: Any = None,
    compactor: Any = None,
    inbox: Any = None,
    fact_sink: Any = None,
    system_prompt: str = "",
    cancel: Any = None,
    effort: str = "high",
    model: str = "",
    image_turns: int = KEEP_IMAGE_TURNS,
    image_max: int = MAX_EMBED_IMAGES,
    mode_note: str = "",
    event_sink: Any = None,
    session_context: Any = None,
    seq_allocator: Any = None,
) -> Any:
    """引擎工厂：把装配参数翻成模块链引擎。

    `system_prompt` 在这里注入上下文管线。

    `cancel` **一路透传到宿主与端口**：宿主在每趟开始前问一次、模型模块逐帧问、
    工具模块逐调用问（见 `core/host.py` 与 `core/modules.py`）。取消时发出
    `turn_ended{stopped: true}`，适配层据此翻成经典界面的 `stopped` 帧。
    """
    from agent.core.engine import Engine

    # `system_prompt` 由 `App.session()` 注入一次。这里再注入一次就会**每个请求
    # 把系统提示发两遍** —— 真实身份块上千 token，等于每请求双付。
    return Engine(
        conversation_id=conversation_id,
        log=log,
        provider=provider,
        registry=registry,
        pipeline=pipeline,
        context=context,
        compactor=compactor,
        inbox=inbox,
        effort=effort,
        model=model,
        image_turns=image_turns,
        image_max=image_max,
        mode_note=mode_note,
        fact_sink=fact_sink,
        event_sink=event_sink,
        session_context=session_context,
        cancel=cancel,
        # **这一行不能少**：本函数签名收了 `seq_allocator`，漏传则「事件带存储坐标」
        # 在真实装配链路上完全失效 —— 内核层 `Ports`/`Host` 的盖章逻辑照常工作、
        # 单元测试直接构造 `Host(...)` 也能过，但真实运行里帧 `id:` 行为 0 条，
        # 浏览器 `Last-Event-ID` 恒空 → **断线期间的事件静默丢失**（不重放、不报错）。
        # 存储侧的兜底补号会掩盖它（存储行有坐标、总线上的没有）。
        seq_allocator=seq_allocator,
    )


def build_app(
    *,
    provider: Any = None,
    store: Any = None,
    context_factory: Optional[Callable[[str], Any]] = None,
    backup_root: Optional[Path] = None,
    recycle_root: Optional[Path] = None,
    live_state: Optional[LiveState] = None,
    mesh: Optional[MeshState] = None,
    backup_retention_days: Optional[int] = None,
    plugins_dir: Optional[Path] = None,
    compactor_factory: Optional[Callable[[str], Any]] = None,
) -> App:
    """组装底座：默认 Echo 假模型；可选真实 provider / 存储 / 上下文工厂。

    backup_root / recycle_root：版本化备份与回收目录根（默认 PROJECT_ROOT/data 下；
    写类工具覆盖前留备份供 file_undo 回滚，删除类操作移入回收目录可恢复）。
    live_state：会话实时状态（模式 / todo 清单）；默认落 PROJECT_ROOT/data/todo_lists。
    mesh：会话协作网格（Agent 注册表 / inbox）；默认落 PROJECT_ROOT/data/mesh。
    plugins_dir：插件根目录；默认 PROJECT_ROOT/plugins。装载哪些取工程根 plugins.ini 清单。
    compactor_factory：上下文压缩器工厂；默认为对话提供 provider 摘要 + config [context] 阈值。"""
    # 默认数据根：认 `AI_AGENT_DATA_ROOT`（只给测试/CI 的落盘隔离口）——
    # 见 `config.default_data_root` 的说明。
    data_root = default_data_root()
    backup_dir = data_root / "temp" / "file_backup"
    recycle_dir = data_root / "recycle"
    backups = FileBackups(Path(backup_root) if backup_root is not None else backup_dir)
    recycle = Recycle(Path(recycle_root) if recycle_root is not None else recycle_dir)
    # 启动清账：删掉保留期之前的版本化备份。回滚能力的价值随时间衰减，
    # 而备份只增不减 —— 不清的话它会一直涨。年龄取自 mod_id 里的日期段，
    # 所以这一步不需要任何外部记账。失败只留痕，不阻断启动。
    _retention_days = (get_backup_retention_days()
                       if backup_retention_days is None else int(backup_retention_days))
    if _retention_days > 0:
        try:
            _removed, _kept = backups.prune(_retention_days)
            if _removed:
                print(f"[core] 已清理 {_removed} 份过期文件备份（保留 {_kept} 份，"
                      f"保留期 {_retention_days} 天）", file=sys.stderr, flush=True)
        except Exception as exc:
            print(f"[core] 文件备份清理失败（不影响启动）："
                  f"{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
    model_cfg = get_model_reasoning()
    # 多模型：`[model_reasoning] models` 是**同一个网关下的可选模型名**，
    # 逗号分隔；未配置时清单只有当前模型（单模型部署照常工作）。
    # 只支持"同网关多模型"：provider 实例绑定一个 base_url / key，
    # 而模型名是请求级的 —— 换网关需要按 id 建多个 provider。
    # `get_model_reasoning` 已经把 `models` 解析成列表；这里只做去空与去重，
    # 它已是列表，**不要再 `str()`**（那样会得到 "['a', 'b']" 再被逗号切开，切成一堆带引号的碎片）。
    _cfg_models = [str(m).strip() for m in (model_cfg.get("models") or []) if str(m).strip()]
    _default_model = str(model_cfg.get("model") or "")
    _available = _cfg_models or ([_default_model] if _default_model else [])
    state = live_state if live_state is not None else LiveState(
        storage_dir=data_root / "todo_lists",
        default_effort=get_reasoning_effort(),
        default_model=_default_model,
    )
    mesh_state = mesh if mesh is not None else MeshState(storage_dir=data_root / "mesh")

    registry = ToolRegistry()
    registry.register(echo.build())
    registry.register(read_file.build())
    registry.register(grep_files.build())
    registry.register(glob_files.build())
    registry.register(write_file.build())
    for plugin in edit_tools.build_plugins():
        registry.register(plugin)
    for plugin in fs_tools.build_plugins(backups):
        registry.register(plugin)
    for plugin in command_tools.build_plugins(state):
        registry.register(plugin)
    for plugin in task_tools.build_plugins(state):
        registry.register(plugin)
    for plugin in session_tools.build_plugins(mesh_state):
        registry.register(plugin)
    for plugin in locate_tools.build_plugins():
        registry.register(plugin)
    for plugin in text_data_tools.build_plugins():
        registry.register(plugin)
    for plugin in system_tools.build_plugins():
        registry.register(plugin)
    for plugin in web_tools.build_plugins():
        registry.register(plugin)
    for plugin in ocr_tool.build_plugins():
        registry.register(plugin)
    for plugin in archive_tool.build_plugins():
        registry.register(plugin)
    for plugin in geo_weather_tools.build_plugins():
        registry.register(plugin)
    registry.register(github_tools.build())
    gate = QualityGate()
    contexts = SessionContexts(lambda cid: QualityGate(), live=state, inbox=mesh_state)

    def _gate_resolver() -> QualityGate:
        """当前会话门控（管道执行期内经会话作用域解析）。"""
        return contexts.resolve().gate

    registry.register(review_conclusion.build(_gate_resolver))
    executors: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
    # 插件贡献的写类工具执行器登记在这里：提交那一刻才查，装配顺序无关。
    executor_registry = ExecutorRegistry()
    executors.update(write_file.build_executors(backups))
    executors.update(edit_tools.build_executors(backups))
    executors.update(fs_tools.build_executors(backups, recycle))
    executors.update(archive_tool.build_executors())
    registry.register(commit_write.build(_gate_resolver, executors, executor_registry))
    pipeline = ToolPipeline()
    pre, post = build_pipeline_gate(
        gate, live_state=state, gate_resolver=_gate_resolver
    )
    pipeline.add_pre(pre)
    pipeline.add_post(post)
    event_bus = EventBus()
    # 上下文注入源：插件按段注册（宿主不认具体插件，段名与数量由插件给）。
    context_sources = ContextSources()
    # 插件贡献注册表：面板（界面）与插件命名空间端点（HTTP）都记在这里，
    # 壳层只按数据枚举，不必为每个插件加分支。
    contributions = ContributionRegistry()
    _plugins_root = Path(plugins_dir) if plugins_dir is not None else PROJECT_ROOT / "plugins"
    plugin_host = PluginHost(
        _plugins_root,
        registry,
        event_bus=event_bus,
        context_sources=context_sources,
        pipeline=pipeline,
        # 插件贡献（右栏面板 / 输入区动作 / 插件命名空间端点）：壳层从这里枚举与转发
        contributions=contributions,
        # 插件专属存储根：各插件拿到 `<数据根>/plugin/<插件名>/`，互相隔离
        plugin_data_root=data_root / "plugin",
        executors=executor_registry,
    )
    provider_inst = provider if provider is not None else EchoProvider()
    ctx_cfg = get_context()
    if context_factory is None:
        # 默认装配上下文管线：
        # 没有它，回合里 `ctx.context` 恒为 None，请求只是"记录 derive 出来的扁平消息"，
        # 上下文分段也无从谈起——只能退化成单段兜底。
        def _default_context_factory(conversation_id: str) -> ContextPipeline:
            return ContextPipeline(
                conversation_id,
                full_user_rounds=int(ctx_cfg["full_user_rounds"]),
                summary_token_threshold=int(ctx_cfg["summary_token_threshold"]),
                sources=context_sources,
            )

        context_factory = _default_context_factory
    if compactor_factory is None:
        summarizer = make_provider_summarizer(
            provider_inst,
            max_chars=int(ctx_cfg["summary_output_max_chars"]),
            prefix_reuse=bool(ctx_cfg["summary_prefix_reuse"]),
        )

        def _default_compactor_factory(conversation_id: str) -> ContextCompactor:
            return ContextCompactor(
                summarizer,
                summary_token_threshold=int(ctx_cfg["summary_token_threshold"]),
                full_user_rounds=int(ctx_cfg["full_user_rounds"]),
            )

        compactor_factory = _default_compactor_factory

    # ── 进程级服务登记（AppContext 是唯一持有者）──
    context = AppContext()
    # 逆序即清理序（后注册先清理）：先会话注册表与运行器，再各机制，最后管道与注册表。
    context.register(SERVICE_REGISTRY, registry)
    context.register(SERVICE_PIPELINE, pipeline)
    context.register(SERVICE_PROVIDER, provider_inst)
    context.register(SERVICE_EVENT_BUS, event_bus)
    context.register(SERVICE_PLUGIN_HOST, plugin_host)
    context.register(SERVICE_CONTEXT_SOURCES, context_sources)
    context.register(SERVICE_LIVE_STATE, state)
    context.register(SERVICE_MESH, mesh_state)
    context.register(SERVICE_SESSION_CONTEXTS, contexts)
    # 模型计价：配置覆盖 + 官方默认表；查不到即"未查到计价信息"，不编数
    context.register(SERVICE_MODEL_PRICING, ModelPricing(get_model_pricing()))
    if store is not None:
        context.register(SERVICE_STORE, store)
    if context_factory is not None:
        context.register(SERVICE_SESSION_FACTORY, context_factory)
    if compactor_factory is not None:
        context.register(SERVICE_COMPACTOR_FACTORY, compactor_factory)

    app = App(
        context,
        context_defaults={
            "full_user_rounds": int(ctx_cfg["full_user_rounds"]),
            "summary_token_threshold": int(ctx_cfg["summary_token_threshold"]),
        },
        image_turns=int(ctx_cfg["image_turns"]),
        image_max=int(ctx_cfg["image_max"]),
    )
    app._available_models = list(_available)
    runner = SessionRunner(
        app=app,
        mesh=mesh_state,
        # 自主模式：回合结束后按会话决定是否再续一轮
        auto_continue=lambda cid: bool(state.get_autonomy(cid).get("enabled")),
        # 目标（Goal）：有目标时续跑与否由目标状态决定，发的是**目标文案**
        goal_row=state.get_goal,
    )
    mesh_state.set_activator(runner.start)
    if store is not None:
        mesh_state.set_session_exists(lambda cid: bool(store.load(cid)))
    context.register(SERVICE_RUNNER, runner)
    # 经典界面适配层：观察内核事件总线做**出站翻译**（内核零改动，只加观察者）。
    # 订阅是**按需**的（有 SSE 连接才订阅，最后一个断开就摘掉）——见 ClassicAdapter.bind_bus。
    classic = ClassicAdapter(app)
    classic.bind_bus(event_bus)
    context.register(SERVICE_CLASSIC_ADAPTER, classic)
    # 插件加载放在**装配末尾**：插件的端点处理器要在调用时取内核服务
    # （`ctx.app.registry` 之类），服务没注册完就加载会让它们全都取到 None。
    # 注册贡献（面板 / 端点）本身是纯记账，放这里不影响工具与管道的装配顺序。
    plugin_host.app = app
    plugin_host.load_manifest(get_plugins())
    return app
