# -*- coding: utf-8 -*-
"""`App` 的服务解析面：属性即进程级 `AppContext` 中登记实例的快捷方式。

服务只由上下文持有；这里按名解析并给出缺失提示，不保存第二份引用。
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from agent.capabilities.registry import ToolRegistry
from agent.core.context import (
    SERVICE_COMPACTOR_FACTORY,
    SERVICE_CONTEXT_SOURCES,
    SERVICE_CONVERSATION_QUEUE,
    SERVICE_EVENT_BUS,
    SERVICE_LIVE_STATE,
    SERVICE_MESH,
    SERVICE_PIPELINE,
    SERVICE_PLUGIN_HOST,
    SERVICE_PROMPT_TAIL,
    SERVICE_PROVIDER,
    SERVICE_REGISTRY,
    SERVICE_SESSION_CONTEXTS,
    SERVICE_SESSION_FACTORY,
    SERVICE_STORE,
)
from agent.core.session_context import SessionContexts
from agent.core.tool_call import ToolPipeline
from agent.shell.service_keys import SERVICE_RUNNER


class AppServices:
    """`App` 的服务属性（解析自进程级上下文）。"""

    def _svc(self, name: str) -> Any:
        """解析进程级服务；缺失服务给出装配提示（而非裸 KeyError）。"""
        try:
            return self.context.get(name)
        except KeyError as exc:
            raise KeyError(
                f"服务未注册：{name}（装配点 app.build_app 未登记该服务）"
            ) from exc

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
