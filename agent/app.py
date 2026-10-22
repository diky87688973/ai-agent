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
    image_tool,
    locate_tools,
    ocr_tool,
    present_tool,
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
from agent.capabilities.model_catalog import ModelCatalog
from agent.capabilities.plugins import PluginHost
from agent.capabilities.registry import ToolRegistry
from agent.config import (
    DEFAULT_COMPRESSION_PERCENT,
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_MAX_PASSES,
    DEFAULT_SUMMARY_TOKEN_FALLBACK,
    PROJECT_ROOT,
    compression_threshold,
    default_data_root,
    get_backup_retention_days,
    get_context,
    get_max_passes,
    get_plugins,
    get_reasoning_effort,
)
from agent.core import event_name as ev
from agent.core.context import (
    SERVICE_COMPACTOR_FACTORY,
    SERVICE_CONTEXT_SOURCES,
    SERVICE_CONVERSATION_QUEUE,
    SERVICE_ERROR_LOG,
    SERVICE_EVENT_BUS,
    SERVICE_LIVE_STATE,
    SERVICE_MESH,
    SERVICE_MODEL_CATALOG,
    SERVICE_PIPELINE,
    SERVICE_PLUGIN_EVENTS,
    SERVICE_PLUGIN_HOST,
    SERVICE_PROMPT_SECTIONS,
    SERVICE_PROMPT_TAIL,
    SERVICE_PROVIDER,
    SERVICE_REGISTRY,
    SERVICE_SESSION_CONTEXTS,
    SERVICE_SESSION_FACTORY,
    SERVICE_STORE,
    AppContext,
)
from agent.core.engine_factory import build_engine
from agent.core.error_report import bind_error_sink, report_error
from agent.core.event_bus import EventBus
from agent.core.events import Event
from agent.core.image_embed import KEEP_IMAGE_TURNS, MAX_EMBED_IMAGES
from agent.core.session_context import SessionContexts
from agent.core.session_log import SessionLog
from agent.core.tool_call import ToolPipeline
from agent.mechanisms.context_compactor import ContextCompactor, make_provider_summarizer
from agent.mechanisms.context_pipeline import ContextPipeline, ContextSources
from agent.mechanisms.conversation_queue import ConversationQueue
from agent.mechanisms.error_log import ErrorLog
from agent.mechanisms.executors import ExecutorRegistry
from agent.mechanisms.file_safety import (
    FileBackups,
    Recycle,
)
from agent.mechanisms.live_state import LiveState
from agent.mechanisms.mesh import MeshState
from agent.mechanisms.model_provider import EchoProvider, MissingProvider
from agent.mechanisms.prompt_sections import PromptSections
from agent.mechanisms.prompt_tail import PromptTail
from agent.mechanisms.provider_router import ProviderRouter
from agent.mechanisms.quality import QualityGate, build_pipeline_gate
from agent.shell.classic_adapter import ClassicAdapter
from agent.shell.classic_adapter.plugin_events import PluginEventPublisher
from agent.shell.service_keys import SERVICE_CLASSIC_ADAPTER, SERVICE_RUNNER
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
        max_passes: int = DEFAULT_MAX_PASSES,
    ) -> None:
        self.context = context
        self.context_defaults = dict(context_defaults or {})
        #: 可选的模型 id 列表（装配时由配置注入；空 = 未配置，不做白名单校验）。
        #: 该字段只保存模型 id；凭据由 provider 持有，不下发到浏览器。
        self._available_models: list = []
        #: 模型来源：catalog（插件目录权威）/ none；显式注入 provider 的测试装配为 config。
        self.model_config_state = "none"
        #: 只把最近这么多轮用户发言里的图带进请求（负数 = 不限）。
        #: 缺省 1 轮：截图体积大，历史全带会撞上游请求体上限。
        self.image_turns = int(image_turns)
        #: 这些轮里最多带几张图（负数 = 不限）；缺省 8，最近一轮优先保。
        self.image_max = int(image_max)
        #: 一回合的模型往返上限（`[agent] max_passes`）。
        self.max_passes = max(1, int(max_passes))

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

        目录权威时每次现读快照：插件配置是热读的，缓存名单会让下拉、
        白名单与配置各说各话。非权威态才用装配注入的 `_available_models`。
        """
        snapshot = self._catalog_snapshot()
        if snapshot is not None and snapshot.authoritative:
            return [item.id for item in snapshot.entries]
        return list(self._available_models)

    def _catalog_snapshot(self) -> Any:
        """当前目录快照；未接入目录或快照失败时返回 None（调用方按非权威处理）。"""
        catalog = self.model_catalog
        snapshot = getattr(catalog, "snapshot", None)
        if not callable(snapshot):
            return None
        try:
            return snapshot()
        except Exception as exc:
            # 快照失败不能把整条请求链路带崩：按无模型处理，下一轮重读。
            report_error("app.model_catalog", exc)
            return None

    @property
    def model_catalog(self) -> Any:
        """模型目录（唯一权威来源）；未接入时返回 None。"""
        return (self.context.get(SERVICE_MODEL_CATALOG)
                if self.context.has(SERVICE_MODEL_CATALOG) else None)

    def model_config(self) -> Dict[str, Any]:
        """`/health` 的模型配置态：来源 / 权威 / 降级，三者都可机读。"""
        snapshot = self._catalog_snapshot()
        return {
            "source": self.model_config_state,
            "authoritative": bool(snapshot is not None and snapshot.authoritative),
            "degraded": self.model_config_state == "none",
        }

    def model_for(self, conversation_id: str) -> str:
        """解析会话模型，并把已被删掉的 id 收敛回默认值（读取点收敛）。

        插件改配置后，旧标签页可能还拿着一个已经不存在的 id。这里写回默认值，
        而不是让它一路撞到 `未配置的模型` 错误 —— 显示同步与状态写入必须分开。
        """
        state = self.live_state
        current = str(state.get_model(conversation_id) or "").strip()
        allowed = self.available_models()
        if not allowed or not current or current in allowed:
            return current
        snapshot = self._catalog_snapshot()
        fallback = (str(snapshot.default_id or "") if snapshot is not None
                    and snapshot.authoritative else str(state.default_model or "")).strip() or allowed[0]
        state.set_model(conversation_id, fallback)
        report_error(
            "app.model",
            f"会话模型 {current!r} 不在可用清单，已回落 {fallback!r}",
            conversation_id=str(conversation_id or ""),
        )
        return fallback

    def context_window_for(self, conversation_id: str) -> int:
        """会话当前所用模型的上下文窗口（token）。

        窗口是模型的物理上限；压缩阈值按它计算，换模型后下一回合重算。
        目录取条目自带的 `context_window`；拿不到时给 0。
        """
        snapshot = self._catalog_snapshot()
        if snapshot is not None and snapshot.authoritative:
            entry = snapshot.entry(self.model_for(conversation_id))
            if entry is not None:
                return entry.context_window or DEFAULT_CONTEXT_WINDOW
        return 0

    def compression_percent_for(self, conversation_id: str) -> int:
        """会话当前模型的压缩百分比；模型缺失时用默认 70。"""
        snapshot = self._catalog_snapshot()
        if snapshot is not None and snapshot.authoritative:
            entry = snapshot.entry(self.model_for(conversation_id))
            if entry is not None:
                return entry.compression_percent
        return DEFAULT_COMPRESSION_PERCENT

    def compression_threshold_for(self, conversation_id: str) -> int:
        """会话当前模型的压缩触发阈值；窗口缺失时用配置回退值。"""
        fallback = int(get_context().get("summary_token_fallback")
                       or DEFAULT_SUMMARY_TOKEN_FALLBACK)
        return compression_threshold(
            self.context_window_for(conversation_id),
            self.compression_percent_for(conversation_id),
            fallback,
        )

    def reload_model_config(self, config_path: Optional[Path] = None) -> str:
        """返回模型配置来源说明；模型由多模型插件维护。"""
        if self.model_config_state == "catalog":
            return "模型目录权威，配置由多模型插件维护"
        return "模型由多模型插件维护"

    def refresh_model_config(self, config_path: Optional[Path] = None) -> str:
        """插件装卸后重算权威来源：目录接管则刷新路由，否则清空模型。"""
        snapshot = self._catalog_snapshot()
        if snapshot is not None and snapshot.authoritative:
            self.model_config_state = "catalog"
            self._available_models = [item.id for item in snapshot.entries]
            self.live_state.default_model = snapshot.default_id
            self._reload_policy(self._available_models, snapshot.default_id, False)
            return ""
        return self._mark_model_config_none()

    def _reload_policy(self, allowed_ids: Any, default_id: str, fallback: bool) -> None:
        policy = getattr(self.provider, "reload_policy", None)
        if callable(policy):
            policy(allowed_ids=list(allowed_ids),
                   default_id=default_id, fallback_to_default=fallback)

    def _mark_model_config_none(self) -> str:
        self.model_config_state = "none"
        self._available_models = []
        self.live_state.default_model = ""
        reloader = getattr(self.provider, "reload_default", None)
        if callable(reloader):
            reloader(MissingProvider())
        self._reload_policy((), "", False)
        return "未配置可用模型：请在 multi_model 插件中配置至少一个模型"

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
    def conversation_queue(self) -> Any:
        return (
            self.context.get(SERVICE_CONVERSATION_QUEUE)
            if self.context.has(SERVICE_CONVERSATION_QUEUE)
            else None
        )

    @property
    def prompt_tail(self) -> Any:
        return (
            self.context.get(SERVICE_PROMPT_TAIL)
            if self.context.has(SERVICE_PROMPT_TAIL)
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
                # 旁路，刻意吞掉：停机路径不能让补投失败阻断释放流程。
                report_error("app.flush", exc)
        session_contexts = self.session_contexts
        if session_contexts is not None:
            session_contexts.close_all()
        self.context.dispose_all()
        unbind = getattr(self, "_error_unbind", None)
        if callable(unbind):
            unbind()
            self._error_unbind = None

    # ── 会话级门控 ──

    @property
    def gate(self) -> QualityGate:
        """默认会话桶的写盘门控（经 `gate_for("")`）。"""
        return self.gate_for("")

    def gate_for(self, conversation_id: str) -> QualityGate:
        """解析某会话的写盘门控；须已装配 `SessionContexts`。"""
        session_contexts = self.session_contexts
        if session_contexts is None:
            raise RuntimeError(
                "未装配会话注册表（SessionContexts）：无法解析写盘门控"
            )
        return session_contexts.resolve_sync(conversation_id).gate

    # ── 会话入口（内核三面：开始回合 / 事件流 / 工具调用协议）──

    def session(
        self,
        conversation_id: str,
        *,
        system_prompt: str = "",
        cancel: Optional[Callable[[], bool]] = None,
        mode_note: Any = "",
    ) -> Any:
        """创建会话引擎：装载既有记录（store 可用时）、装配上下文与持久化旁路。

        cancel：壳层传入的停止检查——内核只认"是否要求停止"。
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
        # 窗口随"这个会话当前用的模型"走：换模型后下一回合的分母就该换。
        # 只写这个字段，不动上下文工厂的构造约定 —— 工厂可以是外部替换的。
        window = self.context_window_for(conversation_id)
        if window and context is not None and hasattr(context, "model_context_window"):
            context.model_context_window = int(window)
        compactor = None
        compactor_factory = self.compactor_factory
        if compactor_factory is not None:
            compactor = compactor_factory(conversation_id)
            if compactor is not None:
                compactor.restore_from_events(list(log.events))
        # 压缩阈值按当前模型窗口 × 该模型百分比；窗口缺失时用配置回退值。
        threshold = self.compression_threshold_for(conversation_id)
        if context is not None and hasattr(context, "summary_token_threshold"):
            context.summary_token_threshold = threshold
        if compactor is not None and hasattr(compactor, "summary_token_threshold"):
            compactor.summary_token_threshold = threshold
        fact_sink = None
        if store is not None and conversation_id:
            cid = conversation_id
            fact_sink = lambda events, _cid=cid: store.append(_cid, events)

        # 推理档位解析器：按会话从 live_state 取，缺省全局默认。
        state = self.live_state
        effort_resolver = (
            (lambda cid: state.get_reasoning_effort(cid)) if state is not None else None
        )
        # 本回合事件的存储坐标按需分配（全局单调，跨会话唯一）。
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
        return build_engine(
            conversation_id=conversation_id,
            log=log,
            provider=self.provider,
            registry=self.registry,
            pipeline=self.pipeline,
            context=context,
            compactor=compactor,
            queued_input=self.conversation_queue,
            fact_sink=fact_sink,
            system_prompt=system_prompt,
            cancel=cancel,
            effort=str(effort_resolver(conversation_id)) if effort_resolver else "high",
            model=self.model_for(conversation_id),
            image_turns=self.image_turns,
            image_max=self.image_max,
            max_passes=self.max_passes,
            mode_note=mode_note,
            event_sink=self.event_bus.publish if self.event_bus is not None else None,
            session_context=session_ctx,
            seq_allocator=seq_allocator,
            app_context=self.context,
            session_contexts=self.session_contexts,
        )

    def run_turn(self, user_text: str, conversation_id: str = "default") -> Iterator[Event]:
        """便捷入口：单回合（新建会话引擎；无 store / 上下文时按无状态路径运行）。"""
        yield from self.session(conversation_id).start_turn(user_text)

    def execute_tool(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        *,
        conversation_id: str = "",
        call_id: str = "",
    ) -> Any:
        """经 ToolPort 执行一次工具（填齐 app / session，与生产路径一致）。"""
        from agent.core.ports import ToolPort
        from agent.core.tool_call import ToolCallRequest

        port = ToolPort(
            registry=self.registry,
            pipeline=self.pipeline,
            app=self.context,
            sessions=self.session_contexts,
        )
        call = ToolCallRequest(
            call_id=str(call_id or f"app-{name}"),
            name=str(name or ""),
            arguments=dict(arguments or {}),
        )
        return port.execute(call, conversation_id=str(conversation_id or ""))



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
    plugins_path: Optional[Path] = None,
    compactor_factory: Optional[Callable[[str], Any]] = None,
    config_ready: Optional[bool] = None,
    data_root: Optional[Path] = None,
) -> App:
    """组装底座：默认 Echo 假模型；可选真实 provider / 存储 / 上下文工厂。

    backup_root / recycle_root：版本化备份与回收目录根（默认 PROJECT_ROOT/data 下；
    写类工具覆盖前留备份供 file_undo 回滚，删除类操作移入回收目录可恢复）。
    live_state：会话实时状态（模型 / 模式 / 档位 / todo 清单）；
        默认落 PROJECT_ROOT/data/session_state（一个会话一份 JSON）。
    mesh：会话协作网格（Agent 注册表 / 运行占位）；默认落 PROJECT_ROOT/data/mesh。
    plugins_dir：插件根目录；默认 PROJECT_ROOT/plugins。装载哪些取工程根 plugins.ini 清单。
    plugins_path：插件清单文件；默认工程根 plugins.ini。给一个不存在的路径即"不装插件"（验收脚本与测试用它排除环境里的开发配置）。
    compactor_factory：上下文压缩器工厂；默认为对话提供 provider 摘要 + config [context] 阈值。
    config_ready：是否有显式注入的可用 provider；None = 由 provider 参数判定。
    data_root：队列 / 协作网格 / 插件数据 / 错误日志的落盘根。显式传入优先，
        否则认 `AI_AGENT_DATA_ROOT`（进程级隔离口），再否则 `PROJECT_ROOT/data`。
        测试必须传它：只靠环境变量的话，绕开 `scripts/ci.py` 直跑 unittest
        会漏进工程 `data/`（队列项就是这么攒下来的）。"""
    # 默认数据根：显式注入 > `AI_AGENT_DATA_ROOT` > `PROJECT_ROOT/data`——
    # 见 `config.default_data_root` 的说明。
    data_root = Path(data_root) if data_root is not None else default_data_root()
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
            report_error("core.backup_prune", exc)
    _available: list = []
    _default_model = ""
    state = live_state if live_state is not None else LiveState(
        storage_dir=data_root / "session_state",
        default_effort=get_reasoning_effort(),
        default_model="",
    )
    if mesh is None:
        conversation_queue = ConversationQueue(data_root / "queues")
        mesh_state = MeshState(storage_dir=data_root / "mesh",
                               input_queue=conversation_queue)
    else:
        mesh_state = mesh
        conversation_queue = mesh_state.queue

    registry = ToolRegistry()
    registry.register(echo.build())
    registry.register(read_file.build())
    registry.register(grep_files.build())
    registry.register(glob_files.build())
    registry.register(write_file.build())
    for plugin in edit_tools.build_plugins():
        registry.register(plugin)
    for plugin in fs_tools.build_plugins(backups, recycle):
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
    for plugin in image_tool.build_plugins():
        registry.register(plugin)
    for plugin in archive_tool.build_plugins():
        registry.register(plugin)
    for plugin in geo_weather_tools.build_plugins():
        registry.register(plugin)
    registry.register(github_tools.build())
    def _path_keys_for(name: str):
        plugin = registry.get(name)
        if plugin is None:
            return ()
        return tuple(getattr(plugin, "write_path_keys", ()) or ())

    contexts = SessionContexts(
        lambda cid: QualityGate(path_keys_for=_path_keys_for),
        live=state,
    )
    # 写盘工具经管道上下文取 session.gate；直调单测可另传门控实例。
    registry.register(review_conclusion.build())
    registry.register(present_tool.build())
    executors: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
    # 插件贡献的写类工具执行器登记在这里：提交那一刻才查，装配顺序无关。
    executor_registry = ExecutorRegistry()
    executors.update(write_file.build_executors(backups))
    executors.update(edit_tools.build_executors(backups))
    executors.update(fs_tools.build_executors(backups, recycle))
    executors.update(archive_tool.build_executors())
    registry.register(commit_write.build(executors, executor_registry))
    pipeline = ToolPipeline()
    # 管道钩子：会话门控经 sessions；预览只认工具 needs_preview。
    pre, post = build_pipeline_gate(
        registry=registry,
        sessions=contexts,
        live_state=state,
    )
    pipeline.add_pre(pre)
    pipeline.add_post(post)
    event_bus = EventBus()
    conversation_queue.set_change_listener(
        lambda cid, snapshot: event_bus.publish(
            Event(ev.QUEUE_UPDATED, {**dict(snapshot), "conversation_id": cid})
        )
    )
    # 上下文注入源：插件按段注册（宿主不认具体插件，段名与数量由插件给）。
    context_sources = ContextSources()
    # 请求尾部片段：插件注入的临时文本，拼在执行模式之后，不进入系统提示词前缀。
    prompt_tail = PromptTail()
    prompt_sections = PromptSections()
    # 插件贡献注册表：面板（界面）与插件命名空间端点（HTTP）都记在这里，
    # 壳层只按数据枚举，不必为每个插件加分支。
    contributions = ContributionRegistry()
    # 模型目录：插件声明条目，装配末尾据"有效条目数"判定是否权威。
    # 它与 provider 实例、内存缓存一样是进程级单例 —— 权威只能有一个。
    model_catalog = ModelCatalog()
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
        model_catalog=model_catalog,
        prompt_tail=prompt_tail,
        prompt_sections=prompt_sections,
    )
    provider_inst = provider if provider is not None else EchoProvider()
    # 路由从一开始就是 SERVICE_PROVIDER：内核只见一个 provider。
    # 插件装载完成后按目录权威性刷新策略（见下方 `reload_policy`）。
    # 没有目录条目时路由不允许回落到默认实例。
    router = ProviderRouter(
        default=provider_inst,
        resolve=model_catalog.provider_for,
        allowed_ids=_available,
        default_id=_default_model,
        fallback_to_default=False,
    )
    ctx_cfg = get_context()
    if context_factory is None:
        # 默认装配上下文管线：
        # 没有它，回合里 `ctx.context` 恒为 None，请求只是"记录 derive 出来的扁平消息"，
        # 上下文分段也无从谈起——只能退化成单段兜底。
        def _default_context_factory(conversation_id: str) -> ContextPipeline:
            # 这里逐项列出来（不是 `**context_defaults`）：漏一项就是"配置写了不生效"，
            # 而且症状很隐蔽 —— 配置能读出来、界面也显示，只有行为不对。
            # 每次建会话再读文件，设置页保存后下一回合用新阈值。
            fresh = get_context()
            return ContextPipeline(
                conversation_id,
                full_user_rounds=int(fresh["full_user_rounds"]),
                summary_token_threshold=int(fresh["summary_token_fallback"]),
                reasoning_replay_tokens=int(fresh["reasoning_replay_tokens"]),
                # 上下文窗口属于"模型"而不是"上下文预算"：由会话按当前模型
                # 在 `App.session` 里回填，工厂不猜。
                model_context_window=0,
                sources=context_sources,
            )

        context_factory = _default_context_factory
    if compactor_factory is None:
        def _default_compactor_factory(conversation_id: str) -> ContextCompactor:
            # 每次建会话再读阈值和摘要长度，设置页保存后下一回合用新值。
            fresh = get_context()
            summarizer = make_provider_summarizer(
                router,
                max_chars=int(fresh["summary_output_max_chars"]),
                # 摘要请求带上与平常请求相同的前缀，这次调用才能命中已有缓存。
                prefix_reuse=True,
            )
            return ContextCompactor(
                summarizer,
                summary_token_threshold=int(fresh["summary_token_fallback"]),
                full_user_rounds=int(fresh["full_user_rounds"]),
            )

        compactor_factory = _default_compactor_factory

    # ── 进程级服务登记（AppContext 是唯一持有者）──
    context = AppContext()
    # 错误日志尽早登记并绑定：后续装配/插件装载失败也能落盘。
    error_log = ErrorLog(data_root)
    context.register(SERVICE_ERROR_LOG, error_log)
    _unbind_error = bind_error_sink(error_log.report)
    # 逆序即清理序（后注册先清理）：先会话注册表与运行器，再各机制，最后管道与注册表。
    context.register(SERVICE_REGISTRY, registry)
    context.register(SERVICE_PIPELINE, pipeline)
    context.register(SERVICE_PROVIDER, router)
    context.register(SERVICE_MODEL_CATALOG, model_catalog)
    context.register(SERVICE_EVENT_BUS, event_bus)
    context.register(SERVICE_PLUGIN_HOST, plugin_host)
    context.register(SERVICE_CONTEXT_SOURCES, context_sources)
    context.register(SERVICE_CONVERSATION_QUEUE, conversation_queue)
    context.register(SERVICE_PROMPT_TAIL, prompt_tail)
    context.register(SERVICE_PROMPT_SECTIONS, prompt_sections)
    context.register(SERVICE_LIVE_STATE, state)
    context.register(SERVICE_MESH, mesh_state)
    context.register(SERVICE_SESSION_CONTEXTS, contexts)
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
            "reasoning_replay_tokens": int(ctx_cfg["reasoning_replay_tokens"]),
        },
        image_turns=int(ctx_cfg["image_turns"]),
        image_max=int(ctx_cfg["image_max"]),
        max_passes=get_max_passes(),
    )
    app._available_models = list(_available)
    app._error_unbind = _unbind_error
    # 显式传入 provider 的装配（测试替身 / 自定义入口）本身就有模型可用；
    # 只有显式注入且不是 MissingProvider 的装配才直接标记为可用。
    if config_ready is None:
        _config_ready = bool(provider is not None) and not isinstance(provider, MissingProvider)
    else:
        _config_ready = bool(config_ready)
    app.model_config_state = "config" if _config_ready else "none"
    runner = SessionRunner(
        app=app,
        mesh=mesh_state,
        # 自主模式：回合结束后按会话决定是否再续一轮
        auto_continue=lambda cid: bool(state.get_autonomy(cid).get("enabled")),
        # 目标（Goal）：有目标时续跑与否由目标状态决定，发的是目标文案
        goal_row=state.get_goal,
        prompt_sections=prompt_sections,
    )
    mesh_state.set_activator(runner.start)
    if store is not None:
        mesh_state.set_session_exists(lambda cid: bool(store.load(cid)))
    context.register(SERVICE_RUNNER, runner)
    # 经典界面适配层：观察内核事件总线做出站翻译（内核零改动，只加观察者）。
    # 订阅是按需的（有 SSE 连接才订阅，最后一个断开就摘掉）——见 ClassicAdapter.bind_bus。
    classic = ClassicAdapter(app)
    classic.bind_bus(event_bus)
    context.register(SERVICE_CLASSIC_ADAPTER, classic)
    context.register(SERVICE_PLUGIN_EVENTS, PluginEventPublisher(classic))
    # 插件加载放在装配末尾：插件的端点处理器要在调用时取内核服务
    # （`ctx.app.registry` 之类），服务没注册完就加载会让它们全都取到 None。
    # 注册贡献（面板 / 端点）本身是纯记账，放这里不影响工具与管道的装配顺序。
    plugin_host.app = app
    plugin_host.load_manifest(get_plugins(plugins_path))
    # 插件装载完成后才算得出权威：目录"启用了"不等于"可用"，看有效条目数。
    snapshot = model_catalog.snapshot()
    if snapshot.authoritative:
        app.model_config_state = "catalog"
        app._available_models = [item.id for item in snapshot.entries]
        state.default_model = snapshot.default_id
        router.reload_policy(
            allowed_ids=app._available_models,
            default_id=snapshot.default_id,
            fallback_to_default=False,
        )
    elif app.model_config_state == "config":
        # 显式注入 provider 的测试/自定义装配：没有目录条目，保留默认 provider。
        app._available_models = list(_available)
        state.default_model = _default_model
        router.reload_policy(
            allowed_ids=app._available_models,
            default_id=_default_model,
            fallback_to_default=False,
        )
    else:
        # 没有目录条目：清单为空，不能报出选不了的 id。
        app._available_models = []
        state.default_model = ""
        router.reload_policy(allowed_ids=[], default_id="", fallback_to_default=False)
    return app
