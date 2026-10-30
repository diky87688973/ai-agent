# -*- coding: utf-8 -*-
"""插件 UI 路径注册表：区域插口、控件和 catalog。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from agent.capabilities.path_registry import PathRegistry


@dataclass
class UiRegistry:
    paths: PathRegistry = field(default_factory=PathRegistry)
    pending: List[Dict[str, Any]] = field(default_factory=list)

    def add_slot(self, path: str, *, kind: str, children: str,
                 allowed_kinds=(), fixed_children=(), owner: str = "*") -> Callable[[], None]:
        disposer = self.paths.add_slot(
            path, kind=kind, children=children,
            allowed_kinds=allowed_kinds, fixed_children=fixed_children, owner=owner)
        self._flush_pending()
        return disposer

    def _flush_pending(self) -> None:
        waiting = []
        for item in self.pending:
            try:
                self.paths.register(**item)
            except Exception as exc:
                if "父插口未注册" in str(exc):
                    waiting.append(item)
                else:
                    raise
        self.pending = waiting

    def finalize(self) -> None:
        self._flush_pending()
        if self.pending:
            first = self.pending[0]
            raise ValueError(f"UI 插口未注册：{first.get('path')}")

    def add_item(self, path: str, *, kind: str, owner: str,
                 handler: Optional[Callable[..., Any]] = None,
                 props: Optional[Dict[str, Any]] = None,
                 order: Optional[int] = None) -> Callable[[], None]:
        if order is not None:
            if isinstance(order, bool) or not isinstance(order, int):
                raise ValueError("UI order 必须是整数")
        metadata: Dict[str, Any] = {"props": dict(props or {})}
        if order is not None:
            metadata["order"] = order
        item = {"path": path, "kind": kind, "owner": owner,
                "handler": handler, "metadata": metadata}
        try:
            disposer = self.paths.register(**item)
        except Exception as exc:
            if "父插口未注册" not in str(exc):
                raise
            self.pending.append(item)
            def drop_pending() -> None:
                self.pending = [entry for entry in self.pending
                                if entry.get("path") != path]
            return drop_pending
        return disposer

    def catalog(self) -> Dict[str, Any]:
        catalog = self.paths.catalog()
        entries = list(catalog.get("entries") or [])
        def sort_key(item: Dict[str, Any]) -> Any:
            raw = item.get("metadata", {}).get("order")
            if raw is None:
                region, value = 1, 0
            elif raw >= 0:
                region, value = 0, raw
            else:
                region, value = 2, raw
            return (str(item.get("path", "")).rsplit("/", 1)[0],
                    region, value, str(item.get("path", "")))

        entries.sort(key=sort_key)
        catalog["entries"] = entries
        return catalog

    def drop_owner(self, owner: str) -> int:
        return self.paths.drop_owner(owner)


__all__ = ["UiRegistry"]
