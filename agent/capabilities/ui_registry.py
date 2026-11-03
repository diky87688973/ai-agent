# -*- coding: utf-8 -*-
"""插件 UI 路径注册表：区域插口、控件和 catalog。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from agent.capabilities.path_registry import PathRegistry
from agent.capabilities.slot_registry import (
    UI_PREFIX,
    SlotRegistry,
    canonical_slot_path,
)
from agent.core.error_report import report_error


@dataclass
class UiRegistry:
    paths: PathRegistry = field(default_factory=PathRegistry)
    bindings: SlotRegistry = field(default_factory=SlotRegistry)
    pending: List[Dict[str, Any]] = field(default_factory=list)

    def add_slot(self, path: str, *, kind: str, children: str,
                 allowed_kinds=(), fixed_children=(), owner: str = "*",
                 replace: bool = False) -> Callable[[], None]:
        path = canonical_slot_path(path)
        previous = self.paths.slots.get(path)
        if previous is not None and not replace:
            return self.paths.add_slot(
                path, kind=kind, children=children,
                allowed_kinds=allowed_kinds, fixed_children=fixed_children, owner=owner)
        if previous is not None:
            self.paths.slots.pop(path, None)
            try:
                self.paths.add_slot(
                    path, kind=kind, children=children,
                    allowed_kinds=allowed_kinds,
                    fixed_children=fixed_children, owner=owner)
            except Exception:
                self.paths.slots[path] = previous
                raise
            current = self.paths.slots.get(path)

            def drop_replaced() -> None:
                if self.paths.slots.get(path) is current:
                    self.paths.slots[path] = previous

            try:
                self._flush_pending()
            except Exception:
                self.paths.slots[path] = previous
                raise
            return drop_replaced
        disposer = self.paths.add_slot(
            path, kind=kind, children=children,
            allowed_kinds=allowed_kinds, fixed_children=fixed_children, owner=owner)
        try:
            self._flush_pending()
        except Exception:
            disposer()
            raise
        return disposer

    def _item(self, path: str, kind: str, owner: str,
              handler: Optional[Callable[..., Any]],
              props: Optional[Dict[str, Any]],
              order: Optional[int]) -> Dict[str, Any]:
        if order is not None:
            if isinstance(order, bool) or not isinstance(order, int):
                raise ValueError("UI order 必须是整数")
        metadata: Dict[str, Any] = {"props": dict(props or {})}
        if order is not None:
            metadata["order"] = order
        return {"path": path, "kind": kind, "owner": owner,
                "handler": handler, "metadata": metadata}

    def _install(self, item: Dict[str, Any], *, replace: bool) -> Callable[[], None]:
        path = item["path"]
        existing = self.bindings.nodes.get(path)
        if existing is not None:
            if not replace:
                raise ValueError(f"UI 路径已注册：{path}")
            binding = self.bindings.bind(
                path, item, owner=item["owner"], mode="replace")
            return binding.dispose
        self.paths.validate(path, kind=item["kind"], owner=item["owner"])
        self.bindings.register_slot(
            path, kind=item["kind"], default=item,
            default_owner=item["owner"], metadata={"ui": True})

        def drop() -> None:
            node = self.bindings.nodes.get(path)
            if node is not None and node.default is item and not node.bindings:
                self.bindings.nodes.pop(path, None)

        return drop

    def _flush_pending(self) -> None:
        waiting: List[Dict[str, Any]] = []
        pending = list(self.pending)
        self.pending = []
        installed: List[Callable[[], None]] = []
        try:
            for index, item in enumerate(pending):
                try:
                    disposer = self._install(item, replace=False)
                except Exception as exc:
                    if "父插口未注册" in str(exc):
                        waiting.append(item)
                        continue
                    waiting.append(item)
                    waiting.extend(pending[index + 1:])
                    raise
                installed.append(disposer)
                deferred = item.pop("_deferred", None)
                if isinstance(deferred, dict):
                    deferred["disposer"] = disposer
        except Exception:
            for undo in reversed(installed):
                try:
                    undo()
                except Exception as exc:
                    report_error("agent.capabilities.ui_registry.rollback", exc)
            raise
        finally:
            self.pending = waiting

    def finalize(self) -> None:
        self._flush_pending()
        if self.pending:
            first = self.pending[0]
            raise ValueError(f"UI 插口未注册：{first.get('path')}")

    def add_item(self, path: str, *, kind: str, owner: str,
                 handler: Optional[Callable[..., Any]] = None,
                 props: Optional[Dict[str, Any]] = None,
                 order: Optional[int] = None,
                 replace: bool = False) -> Callable[[], None]:
        path = canonical_slot_path(path)
        item = self._item(path, kind, owner, handler, props, order)
        existing = self.bindings.nodes.get(path)
        if existing is not None:
            return self._install(item, replace=replace)
        try:
            self.paths.validate(path, kind=kind, owner=owner)
        except Exception as exc:
            if "父插口未注册" not in str(exc):
                raise
            deferred = {"disposer": None}
            item["_deferred"] = deferred
            self.pending.append(item)

            def drop_pending() -> None:
                installed = deferred.get("disposer")
                if installed is not None:
                    installed()
                    return
                self.pending = [entry for entry in self.pending
                                if entry is not item]

            return drop_pending
        return self._install(item, replace=replace)

    def _active_entry(self, node: Any) -> Optional[Dict[str, Any]]:
        if node.bindings:
            active = self.bindings.active_binding(node.path)
            if active is not None:
                return active.implementation
        return node.default

    def catalog(self) -> Dict[str, Any]:
        catalog = self.paths.catalog()
        entries: List[Dict[str, Any]] = []
        for node in self.bindings.nodes.values():
            if not node.path.startswith(UI_PREFIX):
                continue
            entry = self._active_entry(node)
            if entry is not None:
                entries.append(dict(entry))

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
        count = self.bindings.drop_owner(owner)
        stale = [path for path, node in self.bindings.nodes.items()
                 if node.default_owner == owner and not node.bindings]
        for path in stale:
            self.bindings.nodes.pop(path, None)
        return count + len(stale)


__all__ = ["UiRegistry"]
