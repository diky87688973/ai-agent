# -*- coding: utf-8 -*-
"""应用门面：会话入口与上下文服务访问。

启动装配由 `agent.boot.bootstrap.boot_app` 与 `SlotAssembly` 完成；本类不持有组件清单。
"""
from __future__ import annotations

import sys
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Optional

from agent.app_model_policy import AppModelPolicy
from agent.app_services import AppServices
from agent.boot.bootstrap import boot_app
from agent.common.status import DEFAULT_REASONING_EFFORT, MODEL_CONFIG_NONE
from agent.core.context import (
    SERVICE_BACKGROUND_TASKS,
    SERVICE_SUBAGENTS,
    SERVICE_WAKE_SCHEDULER,
    AppContext,
)
from agent.core.engine_factory import build_engine
from agent.core.error_report import report_error
from agent.core.events import Event
from agent.core.modules.slot_chain import ModuleBuildContext
from agent.core.session_log import SessionLog
from agent.core.slot_lifecycle import SlotRequest
from agent.mechanisms.quality import QualityGate
from agent.shell.service_keys import SERVICE_RUNNER
from agent.shell.session.queue import persist_inputs


def get_plugins(plugins_path=None):
    """读取插件清单；保留模块级入口供启动器和测试替换。"""
    from agent.config import get_plugins as load
    return load(plugins_path)


class App(AppModelPolicy, AppServices):
    """组装完成的底座实例（App 属性即 `context.get(name)` 的快捷方式）。

    服务一律由进程级 `AppContext` 持有与解析——本类不重复保存任何服务引用
    （避免"注册表一份、App 属性一份"的双份状态）。`dispose()` 按注册逆序清理。
    """

    # 装配器在 boot_app 末尾写入；类内显式声明，避免未装配访问落成 AttributeError。
    _plugin_runtime: Any = None
    _slot_assembly: Any = None
    _slot_binder: Any = None
    _kernel_group: Any = None

    def __init__(
        self,
        context: AppContext,
        *,
        context_defaults: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.context = context
        self.context_defaults = dict(context_defaults or {})
        #: 可选的模型 id 列表（装配时由配置注入；空 = 未配置，不做白名单校验）。
        #: 该字段只保存模型 id；凭据由 provider 持有，不下发到浏览器。
        self._available_models: list = []
        #: 模型来源：catalog（插件目录权威）/ none；显式注入 provider 的测试装配为 config。
        self.model_config_state = MODEL_CONFIG_NONE

    def reload_plugins(self, *, plugins_path: Any = None, plugins_dir: Any = None,
                       reload_plugin: Any = None) -> SlotRequest:
        """请求在安全轮次边界重新装配插件。"""
        return self._plugin_runtime.reload(plugins_path=plugins_path, plugins_dir=plugins_dir,
                                           reload_plugin=reload_plugin)

    def apply_agent_loop(self, *, image_turns: int, image_max: int,
                         max_passes: int) -> None:
        """把宿主配置写入内核模块组；应用门面不保存 AgentLoop 状态。"""
        self._kernel_group.configure_loop(
            image_turns=image_turns, image_max=image_max,
            max_passes=max_passes)

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
        if self._plugin_runtime is not None:
            self._plugin_runtime.dispose()
        # 先撤登记（注册表回到装配前），再释放构造物。
        binder = self._slot_binder
        if binder is not None:
            binder.dispose()
        assembly = self._slot_assembly
        if assembly is not None:
            assembly.dispose()
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
        context = None
        context_factory = self.context_factory
        if context_factory is not None:
            context = context_factory(conversation_id)
        if context is not None and system_prompt:
            context.append_system(system_prompt)
        window = self.context_window_for(conversation_id)
        if window and context is not None and hasattr(context, "model_context_window"):
            context.model_context_window = int(window)
        compactor = None
        compactor_factory = self.compactor_factory
        if compactor_factory is not None:
            compactor = compactor_factory(conversation_id)
        log = SessionLog()
        covered = 0
        if session_store is not None and conversation_id:
            load = getattr(session_store, "load_for_turn", None)
            if callable(load):
                events, covered = load(conversation_id, compacted=context is not None and hasattr(compactor, "loaded_prefix"))
            else:
                events = session_store.load(conversation_id)
            log = SessionLog(events=events)
        if compactor is not None:
            compactor.restore_from_events(log.events)
            if covered:
                compactor.loaded_prefix = covered
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
        effort = str(state.get_reasoning_effort(conversation_id)) if state is not None else DEFAULT_REASONING_EFFORT
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
        model_name = self.model_for(conversation_id)
        loop = self._kernel_group.loop_config
        queue_commit = None
        if callable(getattr(session_store, "append_if_absent", None)):
            queue_commit = lambda cid, items: persist_inputs(cid, self, session_store, items)
        modules = self._kernel_group.build_modules(
            ModuleBuildContext(
                context=context, compactor=compactor,
                context_hooks=self.context_hooks,
                queued_input=self.conversation_queue, queue_commit=queue_commit, effort=effort,
                model=model_name, image_turns=loop.image_turns,
                image_max=loop.image_max, mode_note=mode_note,
            ),
        )
        return build_engine(
            conversation_id=conversation_id,
            log=log,
            provider=self.provider,
            registry=session_registry,
            pipeline=self.pipeline,
            context=context,
            compactor=compactor,
            context_hooks=self.context_hooks,
            queued_input=self.conversation_queue,
            fact_sink=fact_sink,
            system_prompt=system_prompt,
            cancel=cancel,
            effort=effort,
            model=model_name,
            image_turns=loop.image_turns,
            image_max=loop.image_max,
            max_passes=loop.max_passes,
            mode_note=mode_note,
            event_sink=self.event_bus.publish if self.event_bus is not None else None,
            session_context=session_ctx,
            seq_allocator=seq_allocator,
            app_context=self.context,
            session_contexts=self.session_contexts,
            modules=modules,
        )

    def run_turn(self, user_text: str, conversation_id: str = "default") -> Iterator[Event]:
        """便捷入口：单回合（新建会话引擎；无 store / 上下文时按无状态路径运行）。"""
        lifecycle = self.context.slot_lifecycle
        with lifecycle.turn() if lifecycle is not None else nullcontext():
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

        lifecycle = self.context.slot_lifecycle
        with lifecycle.turn() if lifecycle is not None else nullcontext():
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


    def resume_suspended(
        self, conversation_id: str, call_id: str, data: Any = None, *,
        request_id: str = "", kind: str = "", ok: bool = True,
        name: str = "", error: str = "", resolve: Any = None,
    ) -> Dict[str, Any]:
        """Validate and settle the specific confirmation before scheduling a turn."""
        from agent.shell.session.resume import (
            EXPIRED,
            confirmation_store,
            dispatch_confirmation,
            load_pending,
            notify_closed,
            write_resolution,
        )

        cid = str(conversation_id or "").strip()
        ident = str(call_id or "").strip()
        contexts = self.session_contexts
        if not cid or not ident or not request_id or contexts is None:
            return {"ok": False, "expired": True, "error": EXPIRED}
        session = contexts.resolve_sync(cid)
        store = confirmation_store(self, cid)
        resolution = {"ok": ok, "data": data, "error": error}
        try:
            with session.confirmation_lock:
                pending = load_pending(session, store, cid)
                if (not pending or pending["call_id"] != ident
                        or (pending.get("request_id") or ident) != request_id
                        or (kind and pending.get("kind") != kind)):
                    return {"ok": False, "expired": True, "error": EXPIRED}
                if self.mesh is None:
                    return {"ok": False, "error": "会话运行器不可用"}
                if self.mesh.is_stopped(cid):
                    return {"ok": False, "error": "会话已终止，请先发送新消息"}
                if resolve is not None:
                    resolution = resolve(session, pending)
                    if resolution.get("rejected"):
                        return {"ok": False, "error": resolution["error"]}
                written = write_resolution(store, cid, ident, name or pending.get("name", ""),
                                           resolution, request_id=request_id, continue_after=True)
                session.pending_confirm = None
        except Exception as exc:
            rollback = resolution.get("rollback")
            if callable(rollback):
                rollback()
            report_error("agent.app.resume_suspended", exc, conversation_id=cid)
            return {"ok": False, "error": "确认结果未保存，请重试"}
        if not written:
            rollback = resolution.get("rollback")
            if callable(rollback):
                rollback()
            return {"ok": False, "expired": True, "error": EXPIRED}
        notify_closed(self, cid, pending, expired=False)
        return {**dispatch_confirmation(self, cid, ident, request_id),
                **resolution.get("response", {})}



def build_app(
    *,
    provider: Any = None,
    store: Any = None,
    context_factory: Optional[Callable[[str], Any]] = None,
    backup_root: Optional[Path] = None,
    recycle_root: Optional[Path] = None,
    live_state: Any = None,
    mesh: Any = None,
    backup_retention_days: Optional[int] = None,
    plugins_dir: Optional[Path] = None,
    plugins_path: Optional[Path] = None,
    compactor_factory: Optional[Callable[[str], Any]] = None,
    config_ready: Optional[bool] = None,
    data_root: Optional[Path] = None,
) -> App:
    """从自装配树构建底座。"""
    return boot_app(
        provider=provider, store=store, context_factory=context_factory,
        backup_root=backup_root, recycle_root=recycle_root, live_state=live_state,
        mesh=mesh, backup_retention_days=backup_retention_days,
        plugins_dir=plugins_dir, plugins_path=plugins_path,
        compactor_factory=compactor_factory, config_ready=config_ready,
        data_root=data_root, plugin_manifest=get_plugins(plugins_path),
    )
