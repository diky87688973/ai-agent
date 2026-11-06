# -*- coding: utf-8 -*-
"""壳层组件：运行器、唤醒调度、经典适配与插件事件出口。

每个工厂只产出一个对象；彼此之间的先后与取值由插口节点的 `requires` 决定，
不再经由 `runtime.resources` 这份共享字典传递。
"""
from __future__ import annotations

from typing import Any

from agent.core.context import (
    SERVICE_BACKGROUND_TASKS,
    SERVICE_PLUGIN_EVENTS,
    SERVICE_PROMPT_SECTIONS,
    SERVICE_SUBAGENTS,
    SERVICE_WAKE_SCHEDULER,
)
from agent.core.stderr import write_stderr
from agent.shell.service_keys import SERVICE_CLASSIC_ADAPTER, SERVICE_RUNNER


def _manager(app: Any) -> Any:
    """子智能体管理器；未装配时返回 None（语义与装配顺序无关）。"""
    return app.context.get(SERVICE_SUBAGENTS) if app.context.has(SERVICE_SUBAGENTS) else None


def runner(ctx: Any, facade: Any = None):
    from agent.capabilities.registry import ToolRegistryView
    from agent.shell.session.runner import SessionRunner

    app = facade
    manager = _manager(app)
    hidden = {"session_send", "session_multisend", "session_broadcast",
              "session_create", "session_list"}
    parent = ToolRegistryView(app.registry, excluded={"subagent_send"} | hidden)
    child = ToolRegistryView(
        app.registry, excluded={"subagent"} | hidden, honor_subagent_hidden=True)

    def registry_for(cid: str) -> Any:
        return child if manager is not None and manager.is_child(cid) else parent

    session_runner = SessionRunner(
        app=app, mesh=app.mesh, registry_for=registry_for,
        auto_continue=lambda cid: bool(app.live_state.get_autonomy(cid).get("enabled")),
        goal_row=app.live_state.get_goal,
        prompt_sections=app.context.get(SERVICE_PROMPT_SECTIONS),
    )
    if manager is not None:
        session_runner.set_store_for(manager.store_for)
    return session_runner


def wake_scheduler(ctx: Any, facade: Any = None):
    from agent.mechanisms.wake_scheduler import WakeScheduler

    app = facade
    manager = _manager(app)

    def wake_store(cid: str) -> Any:
        if manager is not None and manager.is_child(cid):
            store_for = getattr(manager, "store_for", None)
            if callable(store_for):
                return store_for(cid)
        return app.store

    def delivered(cid: str, job_id: str) -> bool:
        store = wake_store(cid)
        if store is None:
            return False
        try:
            for event in store.load(str(cid or "").strip()):
                data = getattr(event, "data", None) or {}
                if (str(getattr(event, "type", "")) == "input_claimed"
                        and str(data.get("wake_job_id") or "") == str(job_id or "")):
                    return True
        except Exception as exc:
            from agent.core.error_report import report_error
            report_error("boot.wake.delivered", exc, conversation_id=cid, job_id=job_id)
        return False

    def target_exists(cid: str) -> bool:
        store = wake_store(cid)
        if store is None:
            return False
        try:
            return bool(store.load(str(cid or "").strip()))
        except Exception as exc:
            from agent.core.error_report import report_error
            report_error("boot.wake.target_exists", exc, conversation_id=cid)
            return False

    return WakeScheduler(
        ctx.boot_config.data_root / "wake", submit=app.mesh.submit,
        delivered=delivered, target_exists=target_exists)


def classic_adapter(ctx: Any, facade: Any = None):
    from agent.shell.classic_adapter import ClassicAdapter
    app = facade
    adapter = ClassicAdapter(app)
    adapter.bind_bus(app.event_bus)
    return adapter


def plugin_events(ctx: Any, classic_adapter: Any = None):
    from agent.shell.classic_adapter.plugin_events import PluginEventPublisher
    return PluginEventPublisher(classic_adapter)


def finalizer(ctx: Any, facade: Any = None, classic_adapter: Any = None,
              plugin_events: Any = None, runner: Any = None,
              wake_scheduler: Any = None):
    """收尾：把壳层对象登记进 AppContext，并启动唤醒调度。"""
    app = facade
    app.context.register(SERVICE_RUNNER, runner)
    app.context.register(SERVICE_WAKE_SCHEDULER, wake_scheduler)
    app.context.register(SERVICE_CLASSIC_ADAPTER, classic_adapter)
    app.context.register(SERVICE_PLUGIN_EVENTS, plugin_events)
    app.mesh.set_activator(runner.start)
    if app.store is not None:
        app.mesh.set_session_exists(lambda cid: bool(app.store.load(cid)))
    app.context.get(SERVICE_BACKGROUND_TASKS).set_notice(_notice_handler(app))
    # 调度器总是登记（服务必须可取到对象）；抢不到锁时本进程不是 owner，
    # 只影响能不能注册/取消唤醒任务，不影响启停。
    if not wake_scheduler.start():
        write_stderr("[boot] 唤醒调度本进程未成为 owner：唤醒任务工具会返回"
                     "「另一个进程正在运行唤醒调度器」，查询仍可用")
    return True


def _notice_handler(app: Any):
    def notice(cid: str, text: str, meta: Any = None) -> None:
        extra = dict(meta) if isinstance(meta, dict) else {}
        notice_id = str(extra.get("notice_id") or "").strip()
        dedupe_key = f"system_notice:background_tasks:{notice_id}" if notice_id else ""
        app.mesh.submit_insert(
            cid,
            {"content": text, "meta": extra},
            origin="system",
            dedupe_key=dedupe_key,
        )
    return notice


__all__ = [
    "classic_adapter", "finalizer", "plugin_events", "runner", "wake_scheduler",
]
