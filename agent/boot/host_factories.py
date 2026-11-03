# -*- coding: utf-8 -*-
"""宿主服务组件工厂；路径与依赖由插口树声明。"""
from __future__ import annotations

from typing import Any

from agent.capabilities.contributions import ContributionRegistry
from agent.capabilities.model_catalog import ModelCatalog
from agent.capabilities.plugins import PluginHost
from agent.capabilities.registry import ToolRegistry
from agent.config import get_reasoning_effort
from agent.core import event_name as ev
from agent.core.event_bus import EventBus
from agent.core.events import Event
from agent.core.session_context import SessionContexts
from agent.mechanisms.background_tasks import BackgroundTaskManager
from agent.mechanisms.context import ContextPipeline
from agent.mechanisms.context.hooks import ContextAssemblyHooks
from agent.mechanisms.context.sources import ContextSources
from agent.mechanisms.conversation_queue import ConversationQueue
from agent.mechanisms.error_log import ErrorLog
from agent.mechanisms.live_state import LiveState
from agent.mechanisms.mesh import MeshState
from agent.mechanisms.prompt_sections import PromptSections
from agent.mechanisms.prompt_tail import PromptTail
from agent.mechanisms.provider_router import ProviderRouter
from agent.mechanisms.providers.echo import EchoProvider
from agent.mechanisms.quality import QualityGate
from agent.subagent.manager import SubagentManager
from agent.update.controller import UpdateController


def _config(ctx: Any) -> Any:
    return ctx.runtime.config.host_config


def make_event_bus(ctx: Any) -> Any:
    return EventBus()


def make_error_log(ctx: Any) -> Any:
    return ErrorLog(_config(ctx).data_root)


def make_live_state(ctx: Any) -> Any:
    cfg = _config(ctx)
    return cfg.live_state or LiveState(
        storage_dir=cfg.data_root / "session" / "state",
        default_effort=get_reasoning_effort(), default_model="")


def make_queue(ctx: Any) -> Any:
    cfg = _config(ctx)
    queue = cfg.mesh.queue if cfg.mesh is not None else ConversationQueue(
        cfg.data_root / "queues")
    bus = ctx.ports.get("event_bus") if getattr(ctx, "ports", None) else None
    if bus is not None:
        def _changed(cid: str, snapshot: Any) -> None:
            payload = {"conversation_id": str(cid or "")}
            payload.update(dict(snapshot or {}))
            bus.publish(Event(ev.QUEUE_UPDATED, payload))
        queue.set_change_listener(_changed)
    return queue


def make_mesh(ctx: Any) -> Any:
    cfg = _config(ctx)
    return cfg.mesh if cfg.mesh is not None else MeshState(
        storage_dir=cfg.data_root / "mesh",
        input_queue=ctx.ports["queue"])


def make_registry(ctx: Any) -> Any:
    return ToolRegistry()


def make_background_tasks(ctx: Any) -> Any:
    cfg = _config(ctx)
    return BackgroundTaskManager([cfg.project_root, cfg.data_root])


def make_context_sources(ctx: Any) -> Any:
    return ContextSources(_config(ctx).slots)


def make_context_hooks(ctx: Any) -> Any:
    return ContextAssemblyHooks()


def make_prompt_tail(ctx: Any) -> Any:
    return PromptTail()


def make_prompt_sections(ctx: Any) -> Any:
    return PromptSections(_config(ctx).slots)


def make_contributions(ctx: Any) -> Any:
    return ContributionRegistry()


def make_model_catalog(ctx: Any) -> Any:
    return ModelCatalog()


def make_update(ctx: Any) -> Any:
    return UpdateController()


def make_session_factory(ctx: Any) -> Any:
    cfg = _config(ctx)
    if cfg.context_factory is not None:
        return cfg.context_factory
    sources = ctx.ports["context_sources"]

    def factory(cid: str) -> Any:
        from agent.config import get_context
        fresh = get_context()
        return ContextPipeline(
            cid, full_user_rounds=int(fresh["full_user_rounds"]),
            summary_token_threshold=int(fresh["summary_token_fallback"]),
            reasoning_replay_tokens=int(fresh["reasoning_replay_tokens"]),
            model_context_window=0, sources=sources,
        )
    return factory


def make_compactor_factory(ctx: Any) -> Any:
    cfg = _config(ctx)
    if cfg.compactor_factory is not None:
        return cfg.compactor_factory
    router = ctx.ports["provider"]

    def factory(cid: str) -> Any:
        from agent.config import get_context
        from agent.mechanisms.compaction.compactor import ContextCompactor, make_provider_summarizer
        fresh = get_context()
        return ContextCompactor(
            make_provider_summarizer(
                router, max_chars=int(fresh["summary_output_max_chars"]),
                prefix_reuse=True),
            summary_token_threshold=int(fresh["summary_token_fallback"]),
            full_user_rounds=int(fresh["full_user_rounds"]),
            slots=cfg.slots,
        )
    return factory


def make_provider(ctx: Any) -> Any:
    cfg = _config(ctx)
    return ProviderRouter(
        default=cfg.provider if cfg.provider is not None else EchoProvider(),
        resolve=ctx.ports["model_catalog"].provider_for,
        allowed_ids=tuple(cfg.available or ()),
        default_id=cfg.default_model, fallback_to_default=False,
        slots=cfg.slots,
    )


def make_contexts(ctx: Any) -> Any:
    registry = ctx.ports["registry"]
    live = ctx.ports["live_state"]

    def keys_for(name: str):
        plugin = registry.get(name)
        return tuple(getattr(plugin, "write_path_keys", ()) or ()) if plugin else ()

    return SessionContexts(
        lambda cid: QualityGate(path_keys_for=keys_for), live=live)


def make_pipeline(ctx: Any) -> Any:
    from agent.core.tool_call import ToolPipeline
    from agent.mechanisms.quality import build_pipeline_gate
    cfg = _config(ctx)
    pipeline = ToolPipeline(cfg.slots)
    pre, post = build_pipeline_gate(
        registry=ctx.ports["registry"], sessions=ctx.ports["contexts"],
        live_state=ctx.ports["live_state"])
    pipeline.add_pre(pre)
    pipeline.add_post(post)
    return pipeline


def make_plugin_host(ctx: Any) -> Any:
    cfg = _config(ctx)
    return PluginHost(
        cfg.plugins_root,
        ctx.ports["registry"], event_bus=ctx.ports["event_bus"],
        context_sources=ctx.ports["context_sources"], pipeline=ctx.ports["pipeline"],
        contributions=ctx.ports["contributions"], context_hooks=ctx.ports["context_hooks"],
        slots=cfg.slots, plugin_data_root=cfg.plugin_data_root, executors=cfg.executors,
        model_catalog=ctx.ports["model_catalog"], prompt_tail=ctx.ports["prompt_tail"],
        prompt_sections=ctx.ports["prompt_sections"],
        backend_slots=ctx.runtime.resources.get("backend_slots", ()),
    )


def make_store(ctx: Any) -> Any:
    return _config(ctx).store


def make_subagents(ctx: Any) -> Any:
    cfg = _config(ctx)
    if cfg.store is None:
        return None
    return SubagentManager(
        data_root=cfg.data_root, parent_store=ctx.ports["store"],
        mesh=ctx.ports["mesh"], queue=ctx.ports["queue"],
        event_bus=ctx.ports["event_bus"],
    )


__all__ = [
    "make_background_tasks", "make_compactor_factory", "make_context_hooks",
    "make_context_sources", "make_contexts", "make_contributions",
    "make_error_log", "make_event_bus", "make_live_state", "make_mesh",
    "make_model_catalog", "make_pipeline", "make_plugin_host", "make_prompt_sections",
    "make_prompt_tail", "make_provider", "make_queue", "make_registry",
    "make_session_factory", "make_store", "make_subagents", "make_update",
]
