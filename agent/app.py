# -*- coding: utf-8 -*-
"""装配点：全工程唯一"知道一切"的文件。

装配纪律：工具 → 注册表，门控 → 管道，提供者 / 存储 / 上下文工厂 → 会话；事件总线 → 引擎旁路与插件订阅。
会话入口：`App.session(...)` 产出 `TurnEngine`（内核三面：开始回合 / 事件流 /
工具调用协议）；`App.run_turn(...)` 保留便捷单回合入口。
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Optional

from agent.app_model_policy import AppModelPolicy
from agent.app_services import AppServices
from agent.capabilities import tasks
from agent.capabilities.builtin import (
    archive_tool,
    background_task,
    command_tools,
    commit_write,
    echo,
    edit_tools,
    fs_tools,
    geo_weather_tools,
    glob_files,
    grep_files,
    image_tool,
    locate_tools,
    ocr_tool,
    present_tool,
    read_file,
    review_conclusion,
    session_tools,
    subagent_tools,
    system_tools,
    text_data_tools,
    web_tools,
    write_file,
)
from agent.capabilities.contributions import ContributionRegistry
from agent.capabilities.model_catalog import ModelCatalog
from agent.capabilities.plugins import PluginHost
from agent.capabilities.registry import ToolRegistry, ToolRegistryView
from agent.config import (
    DEFAULT_MAX_PASSES,
    PROJECT_ROOT,
    default_data_root,
    default_plugins_root,
    get_backup_retention_days,
    get_context,
    get_max_passes,
    get_plugins,
    get_reasoning_effort,
)
from agent.core import event_name as ev
from agent.core.context import (
    SERVICE_BACKGROUND_TASKS,
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
    SERVICE_SUBAGENTS,
    SERVICE_UPDATE,
    SERVICE_WAKE_SCHEDULER,
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
from agent.mechanisms.background_tasks import BackgroundTaskManager
from agent.mechanisms.compaction.compactor import ContextCompactor, make_provider_summarizer
from agent.mechanisms.context import ContextPipeline, ContextSources
from agent.mechanisms.conversation_queue import ConversationQueue
from agent.mechanisms.error_log import ErrorLog
from agent.mechanisms.executors import ExecutorRegistry
from agent.mechanisms.file_safety import (
    FileBackups,
    Recycle,
)
from agent.mechanisms.live_state import LiveState
from agent.mechanisms.mesh import MeshState
from agent.mechanisms.prompt_sections import PromptSections
from agent.mechanisms.prompt_tail import PromptTail
from agent.mechanisms.provider_router import ProviderRouter
from agent.mechanisms.providers.echo import EchoProvider
from agent.mechanisms.providers.missing import MissingProvider
from agent.mechanisms.quality import QualityGate, build_pipeline_gate
from agent.mechanisms.wake_scheduler import WakeScheduler
from agent.shell.classic_adapter import ClassicAdapter
from agent.shell.classic_adapter.plugin_events import PluginEventPublisher
from agent.shell.service_keys import SERVICE_CLASSIC_ADAPTER, SERVICE_RUNNER
from agent.shell.session.runner import SessionRunner
from agent.subagent.manager import SubagentManager
from agent.update.controller import UpdateController


class App(AppModelPolicy, AppServices):
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

    # ── 生命周期（进程级服务的注销通路）──

    def dispose(self) -> None:
        """进程停机：释放会话运行态，再按注册逆序注销全部服务。

        顺序要点：先释放会话上下文（否则默认桶门控在容器清空后才被取出、
        永远漏掉释放）；再 `dispose_all()` 逆序清理各注册 disposer。
        """
        # 先停生产者，避免停机 flush 之后仍有 runner 线程写入。
        if self.context.has(SERVICE_WAKE_SCHEDULER):
            scheduler = self.context.get(SERVICE_WAKE_SCHEDULER)
            stop = getattr(scheduler, "stop", None)
            if callable(stop):
                stop()
        if self.context.has(SERVICE_RUNNER):
            runner = self.context.get(SERVICE_RUNNER)
            shutdown = getattr(runner, "shutdown", None)
            if callable(shutdown):
                shutdown()
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
        if self.context.has(SERVICE_BACKGROUND_TASKS):
            background_tasks = self.context.get(SERVICE_BACKGROUND_TASKS)
            shutdown = getattr(background_tasks, "shutdown", None)
            if callable(shutdown):
                shutdown()
        if self.context.has(SERVICE_SUBAGENTS):
            subagents = self.context.get(SERVICE_SUBAGENTS)
            shutdown = getattr(subagents, "shutdown", None)
            if callable(shutdown):
                shutdown()
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

    def _prepare_session(self, conversation_id: str, session_store: Any,
                         system_prompt: str) -> tuple[Any, Any, Any]:
        log = SessionLog()
        if session_store is not None and conversation_id:
            log = SessionLog(events=session_store.load(conversation_id))
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
        window = self.context_window_for(conversation_id)
        if window and context is not None and hasattr(context, "model_context_window"):
            context.model_context_window = int(window)
        compactor = None
        compactor_factory = self.compactor_factory
        if compactor_factory is not None:
            compactor = compactor_factory(conversation_id)
            if compactor is not None:
                compactor.restore_from_events(list(log.events))
        threshold = self.compression_threshold_for(conversation_id)
        if context is not None and hasattr(context, "summary_token_threshold"):
            context.summary_token_threshold = threshold
        if compactor is not None and hasattr(compactor, "summary_token_threshold"):
            compactor.summary_token_threshold = threshold
        return log, context, compactor

    def _session_bindings(self, conversation_id: str, session_store: Any) -> tuple[Any, Any, Any, Any, Any]:
        fact_sink = None
        seq_allocator = None
        if session_store is not None and conversation_id:
            cid = conversation_id
            fact_sink = lambda events, _cid=cid: session_store.append(_cid, events)
            seq_allocator = lambda: session_store.allocate_seq(1)
        state = self.live_state
        effort = str(state.get_reasoning_effort(conversation_id)) if state is not None else "high"
        session_ctx = None
        if conversation_id and self.session_contexts is not None:
            session_ctx = self.session_contexts.resolve_sync(conversation_id)
        return fact_sink, effort, seq_allocator, session_ctx

    def session(
        self,
        conversation_id: str,
        *,
        store: Any = None,
        registry: Any = None,
        system_prompt: str = "",
        cancel: Optional[Callable[[], bool]] = None,
        mode_note: Any = "",
    ) -> Any:
        """创建会话引擎：装载既有记录（store 可用时）、装配上下文与持久化旁路。"""
        session_store = self.store if store is None else store
        session_registry = self.registry if registry is None else registry
        log, context, compactor = self._prepare_session(
            conversation_id, session_store, system_prompt)
        fact_sink, effort, seq_allocator, session_ctx = self._session_bindings(
            conversation_id, session_store)
        return build_engine(
            conversation_id=conversation_id,
            log=log,
            provider=self.provider,
            registry=session_registry,
            pipeline=self.pipeline,
            context=context,
            compactor=compactor,
            queued_input=self.conversation_queue,
            fact_sink=fact_sink,
            system_prompt=system_prompt,
            cancel=cancel,
            effort=effort,
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



class _AppAssembly:
    """按阶段装配进程；每个阶段只持有自己的局部状态。"""

    def __init__(self, *, provider: Any, store: Any, context_factory: Any,
                 backup_root: Any, recycle_root: Any, live_state: Any,
                 mesh: Any, backup_retention_days: Any, plugins_dir: Any,
                 plugins_path: Any, compactor_factory: Any, config_ready: Any,
                 data_root: Any) -> None:
        self.provider = provider
        self.store = store
        self.context_factory = context_factory
        self.backup_root = backup_root
        self.recycle_root = recycle_root
        self.live_state = live_state
        self.mesh = mesh
        self.backup_retention_days = backup_retention_days
        self.plugins_dir = plugins_dir
        self.plugins_path = plugins_path
        self.compactor_factory = compactor_factory
        self.config_ready = config_ready
        self.data_root = Path(data_root) if data_root is not None else default_data_root()
        self.available: list = []
        self.default_model = ""

    def build(self) -> App:
        self._prepare_files()
        self._prepare_runtime()
        self._register_tools()
        self._prepare_processing()
        self._prepare_router()
        self._assemble_app()
        self._load_plugins()
        return self.app

    def _prepare_files(self) -> None:
        backup_dir = self.data_root / "temp" / "file_backup"
        recycle_dir = self.data_root / "recycle"
        self.backups = FileBackups(
            Path(self.backup_root) if self.backup_root is not None else backup_dir)
        self.recycle = Recycle(
            Path(self.recycle_root) if self.recycle_root is not None else recycle_dir)
        days = (get_backup_retention_days() if self.backup_retention_days is None
                else int(self.backup_retention_days))
        if days <= 0:
            return
        try:
            removed, kept = self.backups.prune(days)
            if removed:
                print(f"[core] 已清理 {removed} 份过期文件备份（保留 {kept} 份，"
                      f"保留期 {days} 天）", file=sys.stderr, flush=True)
        except Exception as exc:
            report_error("core.backup_prune", exc)

    def _prepare_runtime(self) -> None:
        self.state = self.live_state if self.live_state is not None else LiveState(
            storage_dir=self.data_root / "session_state",
            default_effort=get_reasoning_effort(), default_model="",
        )
        if self.mesh is None:
            self.queue = ConversationQueue(self.data_root / "queues")
            self.mesh_state = MeshState(
                storage_dir=self.data_root / "mesh", input_queue=self.queue)
        else:
            self.mesh_state = self.mesh
            self.queue = self.mesh_state.queue
        self.event_bus = EventBus()
        self.registry = ToolRegistry()
        self.background_tasks = BackgroundTaskManager([PROJECT_ROOT, self.data_root])
        self.subagent_manager = None
        if self.store is not None:
            self.subagent_manager = SubagentManager(
                data_root=self.data_root, parent_store=self.store,
                mesh=self.mesh_state, queue=self.queue, event_bus=self.event_bus,
            )
        self.update_controller = UpdateController()

    def _register_tools(self) -> None:
        registry = self.registry
        registry.register(background_task.build(self.background_tasks, self.state))
        for builder in (echo.build, read_file.build, grep_files.build,
                        glob_files.build, write_file.build):
            registry.register(builder())
        for plugin in edit_tools.build_plugins():
            registry.register(plugin)
        for plugin in fs_tools.build_plugins(self.backups, self.recycle):
            registry.register(plugin)
        for plugin in command_tools.build_plugins(self.state):
            registry.register(plugin)
        for plugin in tasks.build_plugins(self.state):
            registry.register(plugin)
        for plugin in session_tools.build_plugins(self.mesh_state):
            registry.register(plugin)
        if self.subagent_manager is not None:
            for plugin in subagent_tools.build(self.subagent_manager):
                registry.register(plugin)
        for builder in (locate_tools.build_plugins, text_data_tools.build_plugins,
                        system_tools.build_plugins, web_tools.build_plugins,
                        ocr_tool.build_plugins, image_tool.build_plugins,
                        archive_tool.build_plugins, geo_weather_tools.build_plugins):
            for plugin in builder():
                registry.register(plugin)
        self.executors: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
        self.executor_registry = ExecutorRegistry()
        self.executors.update(write_file.build_executors(self.backups))
        self.executors.update(edit_tools.build_executors(self.backups))
        self.executors.update(fs_tools.build_executors(self.backups, self.recycle))
        self.executors.update(archive_tool.build_executors())
        registry.register(review_conclusion.build())
        registry.register(present_tool.build())
        registry.register(commit_write.build(self.executors, self.executor_registry))

    @staticmethod
    def _path_keys_for(registry: ToolRegistry, name: str):
        plugin = registry.get(name)
        return tuple(getattr(plugin, "write_path_keys", ()) or ()) if plugin else ()

    def _prepare_processing(self) -> None:
        self.contexts = SessionContexts(
            lambda cid: QualityGate(
                path_keys_for=lambda name: self._path_keys_for(self.registry, name)),
            live=self.state,
        )
        self.pipeline = ToolPipeline()
        pre, post = build_pipeline_gate(
            registry=self.registry, sessions=self.contexts, live_state=self.state)
        self.pipeline.add_pre(pre)
        self.pipeline.add_post(post)
        self.queue.set_change_listener(
            lambda cid, snapshot: self.event_bus.publish(
                Event(ev.QUEUE_UPDATED, {**dict(snapshot), "conversation_id": cid})))
        self.context_sources = ContextSources()
        self.prompt_tail = PromptTail()
        self.prompt_sections = PromptSections()
        self.contributions = ContributionRegistry()
        self.model_catalog = ModelCatalog()
        plugins_root = (Path(self.plugins_dir) if self.plugins_dir is not None
                        else default_plugins_root())
        self.plugin_host = PluginHost(
            plugins_root, self.registry, event_bus=self.event_bus,
            context_sources=self.context_sources, pipeline=self.pipeline,
            contributions=self.contributions,
            plugin_data_root=self.data_root / "plugin",
            executors=self.executor_registry, model_catalog=self.model_catalog,
            prompt_tail=self.prompt_tail, prompt_sections=self.prompt_sections,
        )

    def _prepare_router(self) -> None:
        provider_inst = self.provider if self.provider is not None else EchoProvider()
        self.router = ProviderRouter(
            default=provider_inst, resolve=self.model_catalog.provider_for,
            allowed_ids=self.available, default_id=self.default_model,
            fallback_to_default=False,
        )
        ctx_cfg = get_context()
        if self.context_factory is None:
            def _default_context_factory(cid: str) -> ContextPipeline:
                fresh = get_context()
                return ContextPipeline(
                    cid, full_user_rounds=int(fresh["full_user_rounds"]),
                    summary_token_threshold=int(fresh["summary_token_fallback"]),
                    reasoning_replay_tokens=int(fresh["reasoning_replay_tokens"]),
                    model_context_window=0, sources=self.context_sources,
                )
            self.context_factory = _default_context_factory
        if self.compactor_factory is None:
            def _default_compactor_factory(cid: str) -> ContextCompactor:
                fresh = get_context()
                return ContextCompactor(
                    make_provider_summarizer(
                        self.router, max_chars=int(fresh["summary_output_max_chars"]),
                        prefix_reuse=True),
                    summary_token_threshold=int(fresh["summary_token_fallback"]),
                    full_user_rounds=int(fresh["full_user_rounds"]),
                )
            self.compactor_factory = _default_compactor_factory
        self.ctx_cfg = ctx_cfg

    def _assemble_app(self) -> None:
        self.context = AppContext()
        self.error_log = ErrorLog(self.data_root)
        self.context.register(SERVICE_ERROR_LOG, self.error_log)
        self._unbind_error = bind_error_sink(self.error_log.report)
        for name, service in (
            (SERVICE_REGISTRY, self.registry), (SERVICE_PIPELINE, self.pipeline),
            (SERVICE_PROVIDER, self.router), (SERVICE_MODEL_CATALOG, self.model_catalog),
            (SERVICE_EVENT_BUS, self.event_bus), (SERVICE_PLUGIN_HOST, self.plugin_host),
            (SERVICE_CONTEXT_SOURCES, self.context_sources),
            (SERVICE_CONVERSATION_QUEUE, self.queue),
            (SERVICE_PROMPT_TAIL, self.prompt_tail),
            (SERVICE_PROMPT_SECTIONS, self.prompt_sections),
            (SERVICE_LIVE_STATE, self.state), (SERVICE_MESH, self.mesh_state),
            (SERVICE_SESSION_CONTEXTS, self.contexts),
        ):
            self.context.register(name, service)
        if self.store is not None:
            self.context.register(SERVICE_STORE, self.store)
        if self.context_factory is not None:
            self.context.register(SERVICE_SESSION_FACTORY, self.context_factory)
        if self.compactor_factory is not None:
            self.context.register(SERVICE_COMPACTOR_FACTORY, self.compactor_factory)
        cfg = self.ctx_cfg
        self.app = App(
            self.context,
            context_defaults={
                "full_user_rounds": int(cfg["full_user_rounds"]),
                "reasoning_replay_tokens": int(cfg["reasoning_replay_tokens"]),
            },
            image_turns=int(cfg["image_turns"]), image_max=int(cfg["image_max"]),
            max_passes=get_max_passes(),
        )
        self.app._available_models = list(self.available)
        self.app._error_unbind = self._unbind_error
        if self.config_ready is None:
            ready = bool(self.provider is not None) and not isinstance(
                self.provider, MissingProvider)
        else:
            ready = bool(self.config_ready)
        self.app.model_config_state = "config" if ready else "none"
        self._build_runner()

    def _wake_store(self, cid: str) -> Any:
        key = str(cid or "").strip()
        manager = self.subagent_manager
        if manager is not None and key and manager.is_child(key):
            store_for = getattr(manager, "store_for", None)
            if callable(store_for):
                store = store_for(key)
                if store is not None:
                    return store
        return self.store

    def _wake_target_exists(self, cid: str) -> bool:
        store = self._wake_store(cid)
        if store is None:
            return False
        try:
            return bool(store.load(str(cid or "").strip()))
        except Exception as exc:
            report_error("app.wake.target_exists", exc, conversation_id=cid)
            return False

    def _wake_delivered(self, cid: str, job_id: str) -> bool:
        store = self._wake_store(cid)
        if store is None:
            return False
        try:
            for event in store.load(str(cid or "").strip()):
                if str(getattr(event, "type", "")) != "input_claimed":
                    continue
                data = getattr(event, "data", None) or {}
                if str(data.get("wake_job_id") or "") == str(job_id or ""):
                    return True
        except Exception as exc:
            report_error("app.wake.delivered", exc, conversation_id=cid, job_id=job_id)
        return False

    def _build_runner(self) -> None:
        hidden = {"session_send", "session_multisend", "session_broadcast",
                  "session_create", "session_list"}
        parent = ToolRegistryView(self.registry, excluded={"subagent_send"} | hidden)
        child = ToolRegistryView(
            self.registry, excluded={"subagent"} | hidden, honor_subagent_hidden=True)
        self.runner = SessionRunner(
            app=self.app, mesh=self.mesh_state,
            registry_for=lambda cid: (
                child if self.subagent_manager is not None
                and self.subagent_manager.is_child(cid) else parent),
            auto_continue=lambda cid: bool(self.state.get_autonomy(cid).get("enabled")),
            goal_row=self.state.get_goal, prompt_sections=self.prompt_sections,
        )
        self.mesh_state.set_activator(self.runner.start)
        if self.store is not None:
            self.mesh_state.set_session_exists(lambda cid: bool(self.store.load(cid)))
        self.wake_scheduler = WakeScheduler(
            self.data_root / "wake",
            submit=self.mesh_state.submit,
            delivered=self._wake_delivered,
            target_exists=self._wake_target_exists,
        )
        self.context.register(SERVICE_WAKE_SCHEDULER, self.wake_scheduler)
        if self.subagent_manager is not None:
            self.runner.set_store_for(self.subagent_manager.store_for)
            self.context.register(SERVICE_SUBAGENTS, self.subagent_manager)
        self.context.register(SERVICE_BACKGROUND_TASKS, self.background_tasks)
        self.context.register(SERVICE_UPDATE, self.update_controller)
        self.context.register(SERVICE_RUNNER, self.runner)
        self.background_tasks.set_notice(self._background_task_notice)
        self.classic = ClassicAdapter(self.app)
        self.classic.bind_bus(self.event_bus)
        self.context.register(SERVICE_CLASSIC_ADAPTER, self.classic)
        self.context.register(SERVICE_PLUGIN_EVENTS, PluginEventPublisher(self.classic))
        # 所有会话/壳层服务就绪后再开始投递，恢复任务不得在装配中途起回合。
        self.wake_scheduler.start()

    def _background_notice_meta(self, text: str) -> Dict[str, Any]:
        batch = ""
        for line in str(text or "").splitlines():
            if line.startswith("任务批次："):
                batch = line[len("任务批次："):].split(" 已完结", 1)[0].strip()
                break
        return {"kind": "system_notice", "source": "background_tasks",
                "notice_id": uuid.uuid4().hex, "batch": batch}

    def _queue_background_notice(self, cid: str, text: str) -> None:
        meta = self._background_notice_meta(text)
        item = self.queue.enqueue(
            cid, content=text, origin="system", delivery="next_pass",
            payload={**meta, "rule": "user", "internal": True})
        try:
            self.queue.set_insert(cid, str(item.get("id") or ""))
        except Exception as exc:
            report_error("app.background_notice_insert", exc, conversation_id=cid)

    def _background_task_notice(self, cid: str, text: str) -> None:
        if self.mesh_state.is_running(cid):
            self._queue_background_notice(cid, text)
            return
        meta = self._background_notice_meta(text)
        started = self.runner.start(cid, {"content": text, "meta": meta})
        if not started:
            self._queue_background_notice(cid, text)

    def _load_plugins(self) -> None:
        self.plugin_host.app = self.app
        self.plugin_host.load_manifest(get_plugins(self.plugins_path))
        snapshot = self.model_catalog.snapshot()
        if snapshot.authoritative:
            self.app.model_config_state = "catalog"
            self.app._available_models = [item.id for item in snapshot.entries]
            self.state.default_model = snapshot.default_id
            self.router.reload_policy(
                allowed_ids=self.app._available_models,
                default_id=snapshot.default_id, fallback_to_default=False)
        elif self.app.model_config_state == "config":
            self.app._available_models = list(self.available)
            self.state.default_model = self.default_model
            self.router.reload_policy(
                allowed_ids=self.app._available_models,
                default_id=self.default_model, fallback_to_default=False)
        else:
            self.app._available_models = []
            self.state.default_model = ""
            self.router.reload_policy(
                allowed_ids=[], default_id="", fallback_to_default=False)


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
    """组装底座；具体阶段由 `_AppAssembly` 持有。"""
    return _AppAssembly(
        provider=provider, store=store, context_factory=context_factory,
        backup_root=backup_root, recycle_root=recycle_root, live_state=live_state,
        mesh=mesh, backup_retention_days=backup_retention_days,
        plugins_dir=plugins_dir, plugins_path=plugins_path,
        compactor_factory=compactor_factory, config_ready=config_ready,
        data_root=data_root,
    ).build()
