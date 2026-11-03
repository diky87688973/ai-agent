# -*- coding: utf-8 -*-
"""壳层组件：运行器、唤醒调度、经典适配与插件事件出口。"""
from __future__ import annotations

from typing import Any

from agent.core.context import (
    SERVICE_BACKGROUND_TASKS,
    SERVICE_PLUGIN_EVENTS,
    SERVICE_PROMPT_SECTIONS,
    SERVICE_SUBAGENTS,
    SERVICE_WAKE_SCHEDULER,
)
from agent.core.slot import SlotLeaf
from agent.shell.service_keys import SERVICE_CLASSIC_ADAPTER, SERVICE_RUNNER


def _app(ctx: Any) -> Any:
    return ctx.runtime.app


def _leaf(ctx: Any) -> SlotLeaf:
    return SlotLeaf(ctx.node.path, master=ctx.node.master)


def runner(ctx: Any):
    from agent.capabilities.registry import ToolRegistryView
    from agent.shell.session.runner import SessionRunner

    app = _app(ctx)
    manager = app.context.get(SERVICE_SUBAGENTS) if app.context.has(SERVICE_SUBAGENTS) else None
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
    ctx.runtime.resources["runner"] = session_runner
    return _leaf(ctx)


def wake_scheduler(ctx: Any):
    from agent.mechanisms.wake_scheduler import WakeScheduler

    app = _app(ctx)
    manager = app.context.get(SERVICE_SUBAGENTS) if app.context.has(SERVICE_SUBAGENTS) else None

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

    scheduler = WakeScheduler(
        ctx.runtime.config.data_root / "wake", submit=app.mesh.submit,
        delivered=delivered, target_exists=target_exists)
    ctx.runtime.resources["wake_scheduler"] = scheduler
    return _leaf(ctx)


def classic_adapter(ctx: Any):
    from agent.shell.classic_adapter import ClassicAdapter
    app = _app(ctx)
    adapter = ClassicAdapter(app)
    adapter.bind_bus(app.event_bus)
    ctx.runtime.resources["classic_adapter"] = adapter
    return _leaf(ctx)


def plugin_events(ctx: Any):
    from agent.shell.classic_adapter.plugin_events import PluginEventPublisher
    publisher = PluginEventPublisher(ctx.runtime.resources["classic_adapter"])
    ctx.runtime.resources["plugin_events"] = publisher
    return _leaf(ctx)


def finalizer(ctx: Any):
    app = _app(ctx)
    runtime = ctx.runtime
    session_runner = runtime.resources["runner"]
    wake = runtime.resources["wake_scheduler"]
    app.context.register(SERVICE_RUNNER, session_runner)
    app.context.register(SERVICE_WAKE_SCHEDULER, wake)
    app.context.register(SERVICE_CLASSIC_ADAPTER, runtime.resources["classic_adapter"])
    app.context.register(SERVICE_PLUGIN_EVENTS, runtime.resources["plugin_events"])
    app.mesh.set_activator(session_runner.start)
    if app.store is not None:
        app.mesh.set_session_exists(lambda cid: bool(app.store.load(cid)))
    app.context.get(SERVICE_BACKGROUND_TASKS).set_notice(_notice_handler(app, session_runner))
    wake.start()
    return _leaf(ctx)


def _notice_handler(app: Any, runner: Any):
    def notice(cid: str, text: str, meta: Any = None) -> None:
        extra = dict(meta) if isinstance(meta, dict) else {}
        payload = {"internal": True, **extra}
        if app.mesh.is_running(cid):
            app.conversation_queue.enqueue(
                cid, content=text, origin="system", delivery="next_pass",
                payload=payload)
            return
        if not runner.start(cid, {"content": text, "meta": extra}):
            app.conversation_queue.enqueue(
                cid, content=text, origin="system", delivery="next_pass",
                payload=payload)
    return notice


__all__ = [
    "classic_adapter", "finalizer", "plugin_events", "runner", "wake_scheduler",
]
