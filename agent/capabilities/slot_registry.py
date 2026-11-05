# -*- coding: utf-8 -*-
"""插口树：路径节点、绑定、解析和回退。"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from agent.capabilities.path_registry import split_path
from agent.core.app_path import app_path
from agent.core.slot_snapshot import freeze_value


class SlotRegistryError(ValueError):
    """插口注册或绑定不符合契约。"""


_MODES = ("replace", "replace_subtree", "wrap", "extend")
_NO_SUBTREE = object()
_CURRENT_SNAPSHOT: ContextVar[Optional["ResolvedSlotView"]] = ContextVar(
    "slot_execution_snapshot", default=None)


def _locked(method: Any) -> Any:
    @wraps(method)
    def wrapper(self: "SlotRegistry", *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper


UI_PREFIX = app_path("shell", "web-ui") + "/"
SETTINGS_PREFIX = app_path("settings") + "/"


def canonical_slot_path(path: Any) -> str:
    """把相对 UI/settings 根归一为目标 app 根。"""
    value = str(path or "").strip().strip("/")
    if value == "web-ui":
        return UI_PREFIX.rstrip("/")
    if value.startswith("web-ui/"):
        return UI_PREFIX + value[len("web-ui/"):]
    if value == "settings":
        return SETTINGS_PREFIX.rstrip("/")
    if value.startswith("settings/"):
        return SETTINGS_PREFIX + value[len("settings/"):]
    if value == "backend":
        return app_path("backend")
    if value.startswith("backend/"):
        return app_path(value)
    return value


def route_slot_path(method: Any, path: Any) -> str:
    """路由身份按 method + path 的无符号十六进制编码，避免字符归一化碰撞。"""
    raw = f"{str(method or 'GET').lower()}:{str(path or '/')}".encode("utf-8")
    return app_path("shell", "http", "routes", raw.hex())


def normalize_slot_path(path: Any) -> str:
    """把任意路径归一为插口树使用的规范形式。"""
    return "/".join(split_path(str(path or "")))


def _normalize_path(path: Any) -> str:
    return normalize_slot_path(path)


def _mode(value: Any) -> str:
    mode = str(value or "replace").strip().lower()
    if mode not in _MODES:
        raise SlotRegistryError(f"绑定模式非法：{value!r}")
    return mode


@dataclass(slots=True)
class SlotSpec:
    path: str
    kind: str
    contract: Any = None
    contract_version: str = "1"
    children: str = "none"
    subtree: Tuple[str, ...] = ()
    default: Any = None
    default_owner: str = "__host__"
    factory: Any = None
    dependencies: Tuple[str, ...] = ()
    lifecycle: str = "singleton"
    enabled: bool = True
    scope: str = "app"
    metadata: Dict[str, Any] = field(default_factory=dict)
    bindings: List["Binding"] = field(default_factory=list)

    def clone(self) -> "SlotSpec":
        return SlotSpec(
            path=self.path,
            kind=self.kind,
            contract=self.contract,
            contract_version=self.contract_version,
            children=self.children,
            subtree=tuple(self.subtree),
            default=self.default,
            default_owner=self.default_owner,
            factory=self.factory,
            dependencies=tuple(self.dependencies),
            lifecycle=self.lifecycle,
            enabled=self.enabled,
            scope=self.scope,
            metadata=dict(self.metadata),
            bindings=list(self.bindings),
        )

    def as_dict(self) -> Dict[str, Any]:
        active = None
        if self.bindings:
            active = max(
                self.bindings,
                key=lambda item: (item.priority, item.order, item.created),
            ).id
        return {
            "path": self.path,
            "kind": self.kind,
            "contract_version": self.contract_version,
            "children": self.children,
            "subtree": list(self.subtree),
            "default": _implementation_name(self.default),
            "default_owner": self.default_owner,
            "factory": _implementation_name(self.factory),
            "dependencies": list(self.dependencies),
            "lifecycle": self.lifecycle,
            "enabled": self.enabled,
            "scope": self.scope,
            "active": active,
            "bindings": [_binding_dict(binding) for binding in self.bindings],
        }


@dataclass(slots=True)
class Binding:
    id: str
    path: str
    owner: str
    implementation: Any
    mode: str
    priority: int = 0
    order: int = 0
    contract_version: str = "1"
    created: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    _registry: Any = field(default=None, repr=False, compare=False)

    def dispose(self) -> None:
        if self._registry is not None:
            self._registry.unbind(self.id)

    def __call__(self) -> None:
        self.dispose()

    def as_dict(self) -> Dict[str, Any]:
        return _binding_dict(self)


def _binding_dict(binding: Binding) -> Dict[str, Any]:
    return {
        "id": binding.id,
        "path": binding.path,
        "owner": binding.owner,
        "mode": binding.mode,
        "priority": binding.priority,
        "order": binding.order,
        "contract_version": binding.contract_version,
        "implementation": _implementation_name(binding.implementation),
        "metadata": dict(binding.metadata),
    }


def _implementation_name(value: Any) -> str:
    if value is None:
        return ""
    name = getattr(value, "__qualname__", None) or getattr(value, "__name__", None)
    if name:
        return str(name)
    return type(value).__name__


@dataclass(frozen=True)
class ResolvedSlotView:
    """单轮执行使用的已解析 slot 快照；此后不再读取实时绑定。"""

    registry_id: int
    version: int
    values: Mapping[str, Any]
    items: Mapping[str, Tuple[Any, ...]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", freeze_value(self.values))
        object.__setattr__(self, "items", freeze_value(self.items))

    def contains(self, path: Any) -> bool:
        return _normalize_path(path) in self.values or _normalize_path(path) in self.items

    def resolve(self, path: Any) -> Any:
        name = _normalize_path(path)
        if name not in self.values:
            raise SlotRegistryError(f"路径不在本轮快照中：{name}")
        return self.values[name]

    def resolve_items(self, path: Any) -> List[Any]:
        name = _normalize_path(path)
        value = self.items.get(name)
        if value is None:
            raise SlotRegistryError(f"路径不在本轮快照中：{name}")
        return list(value)


@dataclass
class SlotRegistry:
    """维护 slot 的默认实现和可替换绑定。"""

    nodes: Dict[str, SlotSpec] = field(default_factory=dict)
    _seq: int = 0
    _lock: Any = field(default_factory=threading.RLock, repr=False, compare=False)

    @_locked
    def register_slot(
        self,
        path: Any,
        *,
        kind: str = "slot",
        contract: Any = None,
        contract_version: Any = "1",
        children: str = "none",
        subtree: Sequence[str] = (),
        default: Any = None,
        default_owner: str = "__host__",
        factory: Any = None,
        dependencies: Sequence[str] = (),
        lifecycle: str = "singleton",
        enabled: bool = True,
        scope: str = "app",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Any:
        name = _normalize_path(path)
        if name in self.nodes:
            raise SlotRegistryError(f"插口已注册：{name}")
        if children not in ("none", "fixed", "keyed", "extension", "tree"):
            raise SlotRegistryError(f"子路径策略非法：{children!r}")
        node = SlotSpec(
            path=name,
            kind=str(kind or "slot"),
            contract=contract,
            contract_version=str(contract_version or "1"),
            children=str(children),
            subtree=tuple(
                "/".join(split_path(str(item).strip().strip("/")))
                for item in subtree if str(item).strip()),
            default=default,
            default_owner=str(default_owner or "__host__"),
            factory=factory,
            dependencies=tuple(
                "/".join(split_path(str(item).strip().strip("/")))
                for item in dependencies if str(item).strip()),
            lifecycle=str(lifecycle or "singleton"),
            enabled=bool(enabled),
            scope=str(scope or "app"),
            metadata=dict(metadata or {}),
        )
        self.nodes[name] = node

        def dispose() -> None:
            if self.nodes.get(name) is node:
                self.nodes.pop(name, None)

        return dispose

    @_locked
    def bind(
        self,
        path: Any,
        implementation: Any,
        *,
        owner: Any,
        mode: Any = "replace",
        priority: int = 0,
        order: int = 0,
        contract_version: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Binding:
        name = _normalize_path(path)
        node = self.nodes.get(name)
        if node is None:
            raise SlotRegistryError(f"插口不存在：{name}")
        mode_value = _mode(mode)
        if mode_value == "replace_subtree" and not node.subtree:
            raise SlotRegistryError(
                f"replace_subtree 需要子树白名单：{name}")
        version = str(contract_version or node.contract_version)
        if version != node.contract_version:
            raise SlotRegistryError(
                f"契约版本不匹配：{name} 需要 {node.contract_version}，收到 {version}")
        owner_value = str(owner or "").strip()
        if not owner_value:
            raise SlotRegistryError("绑定 owner 不能为空")
        priority_value = int(priority)
        order_value = int(order)
        if mode_value != "extend":
            for existing in node.bindings:
                if (existing.priority == priority_value
                        and existing.order == order_value):
                    raise SlotRegistryError(
                        f"同一路径同优先级绑定冲突：{name} / {owner_value} / "
                        f"{priority_value}:{order_value}")
        self._seq += 1
        binding = Binding(
            id=f"binding-{self._seq}",
            path=name,
            owner=owner_value,
            implementation=implementation,
            mode=mode_value,
            priority=priority_value,
            order=order_value,
            contract_version=version,
            created=self._seq,
            metadata=dict(metadata or {}),
            _registry=self,
        )
        node.bindings.append(binding)
        return binding

    @_locked
    def unbind(self, binding: Any) -> bool:
        binding_id = binding.id if isinstance(binding, Binding) else str(binding or "")
        for node in self.nodes.values():
            for index, current in enumerate(node.bindings):
                if current.id == binding_id:
                    node.bindings.pop(index)
                    return True
        return False

    @_locked
    def drop_owner(self, owner: Any) -> int:
        owner_name = str(owner or "")
        count = 0
        for node in self.nodes.values():
            kept = [b for b in node.bindings if b.owner != owner_name]
            count += len(node.bindings) - len(kept)
            node.bindings = kept
        return count

    @_locked
    def node(self, path: Any) -> SlotSpec:
        name = _normalize_path(path)
        node = self.nodes.get(name)
        if node is None:
            raise SlotRegistryError(f"插口不存在：{name}")
        return node

    @_locked
    def bindings_of(self, path: Any) -> List[Binding]:
        return list(self.node(path).bindings)

    def _ordered(self, node: SlotSpec) -> List[Binding]:
        return sorted(node.bindings, key=lambda b: (b.priority, b.order, b.created))

    @_locked
    def active_binding(self, path: Any) -> Optional[Binding]:
        node = self.node(path)
        ordered = self._ordered(node)
        return ordered[-1] if ordered else None

    @_locked
    def resolve_base(self, path: Any) -> Any:
        node = self.node(path)
        subtree = self._subtree_override(node.path)
        if subtree is not _NO_SUBTREE:
            return subtree
        value = node.default
        for binding in self._ordered(node):
            if binding.mode in ("replace", "replace_subtree"):
                value = binding.implementation
            elif binding.mode == "wrap":
                if not callable(binding.implementation):
                    raise SlotRegistryError(
                        f"wrap 绑定必须可调用：{binding.owner} / {binding.path}")
                value = binding.implementation(value)
            elif binding.mode == "extend":
                if value is None:
                    value = []
                if not isinstance(value, list):
                    raise SlotRegistryError(
                        f"extend 需要列表默认值：{binding.path}")
                value = list(value)
                extra = binding.implementation
                value.extend(extra if isinstance(extra, list) else [extra])
        if value is None:
            raise SlotRegistryError(f"插口没有实现：{node.path}")
        return value

    @_locked
    def resolve(self, path: Any) -> Any:
        snapshot = self._current_snapshot()
        if snapshot is not None:
            return snapshot.resolve(path)
        return self.resolve_base(path)

    @_locked
    def resolve_items(self, path: Any) -> List[Any]:
        snapshot = self._current_snapshot()
        if snapshot is not None:
            return snapshot.resolve_items(path)
        node = self.node(path)
        base: List[Any] = []
        if node.default is not None:
            base = list(node.default) if isinstance(node.default, (list, tuple)) else [node.default]
        for binding in self._ordered(node):
            if binding.mode == "extend":
                extra = binding.implementation
                base.extend(extra if isinstance(extra, list) else [extra])
            elif binding.mode in ("replace", "replace_subtree"):
                base = (list(binding.implementation)
                        if isinstance(binding.implementation, (list, tuple))
                        else [binding.implementation])
            elif binding.mode == "wrap":
                raise SlotRegistryError(f"wrap 不能用于集合插口：{binding.path}")
        return base

    def _subtree_override(self, path: str) -> Any:
        parts = split_path(path)
        for index in range(len(parts) - 1, 0, -1):
            ancestor = "/".join(parts[:index])
            node = self.nodes.get(ancestor)
            if node is None:
                continue
            relative = "/".join(parts[index:])
            allowed = any(
                relative == entry or relative.startswith(entry + "/")
                for entry in node.subtree)
            if not allowed:
                continue
            for binding in reversed(self._ordered(node)):
                if binding.mode == "replace_subtree":
                    return binding.implementation
        return _NO_SUBTREE

    @_locked
    def freeze(self) -> ResolvedSlotView:
        values: Dict[str, Any] = {}
        items: Dict[str, List[Any]] = {}
        for name, node in self.nodes.items():
            if node.default is not None or node.bindings:
                values[name] = self.resolve_base(name)
            if node.children in ("keyed", "fixed", "extension", "tree"):
                items[name] = list(self.resolve_items(name))
        return ResolvedSlotView(
            registry_id=id(self), version=self._seq,
            values=values, items=items)

    @contextmanager
    def execution_snapshot(self) -> Iterator[ResolvedSlotView]:
        current = self._current_snapshot()
        if current is not None:
            yield current
            return
        snapshot = self.freeze()
        token = _CURRENT_SNAPSHOT.set(snapshot)
        try:
            yield snapshot
        finally:
            _CURRENT_SNAPSHOT.reset(token)

    def _current_snapshot(self) -> Optional[ResolvedSlotView]:
        snapshot = _CURRENT_SNAPSHOT.get()
        if snapshot is not None and snapshot.registry_id == id(self):
            return snapshot
        return None

    def snapshot_contains(self, path: Any) -> bool:
        """当前执行上下文是否能解析该路径；无快照时始终允许。"""
        snapshot = self._current_snapshot()
        return snapshot is None or snapshot.contains(path)

    @_locked
    def describe(self) -> Dict[str, Any]:
        """返回注册表元数据；执行期固定使用 execution_snapshot。"""
        return {
            "nodes": [node.as_dict() for node in self.nodes.values()],
            "version": self._seq,
        }

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            before = {path: node.clone() for path, node in self.nodes.items()}
            seq_before = self._seq
            try:
                yield
            except Exception:
                self.nodes = before
                self._seq = seq_before
                raise
