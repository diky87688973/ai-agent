# -*- coding: utf-8 -*-
"""HTTP 路由 slot：宿主路由的实现绑定与替换。"""
from __future__ import annotations

from typing import Any, Optional

from agent.capabilities.slot_registry import route_slot_path
from agent.core.app_path import app_path

PREFIX = app_path("shell", "http", "routes") + "/"


class HttpRouteSlots:
    """把 method + path 映射到 SlotRegistry 的 route 节点。"""

    def __init__(self, slots: Any = None) -> None:
        self.slots = slots

    def path(self, method: str, path: str) -> str:
        return route_slot_path(method, path)

    def ensure_default(self, method: str, path: str, handler: Any,
                       owner: str = "__host__") -> Any:
        if self.slots is None:
            return None
        key = self.path(method, path)
        if key not in self.slots.nodes:
            self.slots.register_slot(
                key, kind="http-route", default=handler,
                default_owner=owner)
        return key

    def bind(self, method: str, path: str, handler: Any, owner: str,
             *, priority: int = 0) -> Any:
        if self.slots is None:
            raise RuntimeError("HTTP 路由 slot 未接入")
        key = self.path(method, path)
        if key not in self.slots.nodes:
            self.slots.register_slot(
                key, kind="http-route", default=None, default_owner=owner)
        return self.slots.bind(
            key, handler, owner=owner, mode="replace", priority=priority)

    def resolve(self, method: str, path: str) -> Optional[Any]:
        if self.slots is None:
            return None
        key = self.path(method, path)
        node = self.slots.nodes.get(key)
        if node is None:
            return None
        if node.default is None and not node.bindings:
            return None
        if not self.slots.snapshot_contains(key):
            return None
        return self.slots.resolve(key)


__all__ = ["HttpRouteSlots", "PREFIX"]
