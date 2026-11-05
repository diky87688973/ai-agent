# -*- coding: utf-8 -*-
"""宿主服务组件工厂；依赖由插口节点的 `requires` 声明，按参数名注入。"""
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
    """宿主配置：装配根输入里的 `host_config`。"""
    return ctx.boot_config.host_config


def make_event_bus(ctx: Any) -> Any:
    return EventBus()


def make_error_log(ctx: Any, event_bus: Any = None) -> Any:
    return ErrorLog(_config(ctx).data_root)


def make_live_state(ctx: Any) -> Any:
    cfg = _config(ctx)
    return cfg.live_state or LiveState(
        storage_dir=cfg.data_root / "session" / "state",
        default_effort=get_reasoning_effort(), default_model="")


def make_queue(ctx: Any, event_bus: Any = None) -> Any:
    cfg = _config(ctx)
    queue = cfg.mesh.queue if cfg.mesh is not None else ConversationQueue(
        cfg.data_root / "queues")
    if event_bus is not None:
        def _changed(cid: str, snapshot: Any) -> None:
            payload = {"conversation_id": str(cid or "")}
            payload.update(dict(snapshot or {}))
            event_bus.publish(Event(ev.QUEUE_UPDATED, payload))
        queue.set_change_listener(_changed)
    return queue


def make_mesh(ctx: Any, queue: Any = None) -> Any:
    cfg = _config(ctx)
    return cfg.mesh if cfg.mesh is not None else MeshState(
        storage_dir=cfg.data_root / "mesh", input_queue=queue)


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


def make_session_factory(ctx: Any, context_sources: Any = None) -> Any:
    cfg = _config(ctx)
    if cfg.context_factory is not None:
        return cfg.context_factory

    def factory(cid: str) -> Any:
        from agent.config import get_context
        fresh = get_context()
        return ContextPipeline(
            cid, full_user_rounds=int(fresh["full_user_rounds"]),
            summary_token_threshold=int(fresh["summary_token_fallback"]),
            reasoning_replay_tokens=int(fresh["reasoning_replay_tokens"]),
            model_context_window=0, sources=context_sources,
        )
    return factory


def make_compactor_factory(ctx: Any, provider: Any = None) -> Any:
    cfg = _config(ctx)
    if cfg.compactor_factory is not None:
        return cfg.compactor_factory

    def factory(cid: str) -> Any:
        from agent.config import get_context
        from agent.mechanisms.compaction.compactor import (
            ContextCompactor,
            make_provider_summarizer,
        )
        fresh = get_context()
        return ContextCompactor(
            make_provider_summarizer(
                provider, max_chars=int(fresh["summary_output_max_chars"]),
                prefix_reuse=True),
            summary_token_threshold=int(fresh["summary_token_fallback"]),
            full_user_rounds=int(fresh["full_user_rounds"]),
            slots=cfg.slots,
        )
    return factory


def make_provider(ctx: Any, model_catalog: Any = None) -> Any:
    cfg = _config(ctx)
    return ProviderRouter(
        default=cfg.provider if cfg.provider is not None else EchoProvider(),
        resolve=model_catalog.provider_for,
        allowed_ids=tuple(cfg.available or ()),
        default_id=cfg.default_model, fallback_to_default=False,
        slots=cfg.slots,
    )


def make_contexts(ctx: Any, registry: Any = None, live_state: Any = None) -> Any:
    def keys_for(name: str):
        plugin = registry.get(name)
        return tuple(getattr(plugin, "write_path_keys", ()) or ()) if plugin else ()

    return SessionContexts(
        lambda cid: QualityGate(path_keys_for=keys_for), live=live_state)


def make_pipeline(ctx: Any, registry: Any = None, contexts: Any = None,
                  live_state: Any = None) -> Any:
    from agent.core.tool_call import ToolPipeline
    from agent.mechanisms.quality import build_pipeline_gate
    pipeline = ToolPipeline(_config(ctx).slots)
    pre, post = build_pipeline_gate(
        registry=registry, sessions=contexts, live_state=live_state)
    pipeline.add_pre(pre)
    pipeline.add_post(post)
    return pipeline


def make_plugin_host(ctx: Any, registry: Any = None, event_bus: Any = None,
                     context_sources: Any = None, pipeline: Any = None,
                     contributions: Any = None, context_hooks: Any = None,
                     model_catalog: Any = None, prompt_tail: Any = None,
                     prompt_sections: Any = None) -> Any:
    cfg = _config(ctx)
    return PluginHost(
        cfg.plugins_root,
        registry, event_bus=event_bus,
        context_sources=context_sources, pipeline=pipeline,
        contributions=contributions, context_hooks=context_hooks,
        slots=cfg.slots, plugin_data_root=cfg.plugin_data_root, executors=cfg.executors,
        model_catalog=model_catalog, prompt_tail=prompt_tail,
        prompt_sections=prompt_sections,
    )


def make_store(ctx: Any) -> Any:
    return _config(ctx).store


def make_subagents(ctx: Any, store: Any = None, mesh: Any = None,
                   queue: Any = None, event_bus: Any = None) -> Any:
    cfg = _config(ctx)
    if cfg.store is None:
        return None
    return SubagentManager(
        data_root=cfg.data_root, parent_store=store,
        mesh=mesh, queue=queue, event_bus=event_bus,
    )


__all__ = [
    "make_background_tasks", "make_compactor_factory", "make_context_hooks",
    "make_context_sources", "make_contexts", "make_contributions",
    "make_error_log", "make_event_bus", "make_live_state", "make_mesh",
    "make_model_catalog", "make_pipeline", "make_plugin_host", "make_prompt_sections",
    "make_prompt_tail", "make_provider", "make_queue", "make_registry",
    "make_session_factory", "make_store", "make_subagents", "make_update",
]
