# -*- coding: utf-8 -*-
"""插口树：唯一清单、节点索引、递归装配与失败回滚。"""
from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from agent.core.app_path import APP_ROOT
from agent.core.error_report import report_error
from agent.core.slot import SlotComponent


def _apply_overrides(nodes: List[Dict[str, Any]],
                     overrides: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把插件装配节点合并进基础树；冻结节点及其子树不可替换。"""
    rows = [dict(row) for row in nodes]
    index = {str(row.get("path") or ""): i for i, row in enumerate(rows)}

    def frozen_hit(path: str) -> str:
        for row in rows:
            if not bool(row.get("frozen", False)):
                continue
            base = str(row.get("path") or "")
            if path == base or path.startswith(base + "/"):
                return base
        return ""

    for override in overrides:
        if not isinstance(override, dict):
            raise SlotTreeError("装配覆盖必须是对象")
        row = dict(override)
        path = str(row.get("path") or "").strip()
        if not path:
            raise SlotTreeError("装配覆盖缺少 path")
        blocked = frozen_hit(path)
        if blocked:
            raise SlotTreeError(f"冻结节点不可替换：{blocked}")
        replace = bool(row.pop("replace", True))
        if path not in index:
            rows.append(row)
            index[path] = len(rows) - 1
            continue
        if not replace:
            raise SlotTreeError(f"节点已存在且不允许替换：{path}")
        before = rows[index[path]]
        merged = dict(before)
        for key, value in row.items():
            if key in ("metadata", "requires") and isinstance(value, dict):
                merged[key] = {**dict(before.get(key) or {}), **value}
            else:
                merged[key] = value
        rows[index[path]] = merged
    return rows


class SlotTreeError(RuntimeError):
    """清单无效、工厂失败或装配循环。"""


@dataclass
class SlotNode:
    path: str
    factory: str
    master: bool = False
    enabled: bool = True
    frozen: bool = False
    requires: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    factory_callable: Optional[Callable[[Any], SlotComponent]] = None
    instance: Optional[SlotComponent] = None
    assembled: bool = False
    failed: bool = False


@dataclass
class SlotRuntime:
    """启动期通用运行时；业务服务由树节点填充。"""

    config: Any = None
    tree: Any = None
    services: Dict[str, Any] = field(default_factory=dict)
    resources: Dict[str, Any] = field(default_factory=dict)

    def service(self, path: str) -> Any:
        key = str(path or "")
        if key not in self.services:
            raise SlotTreeError(f"服务未装配：{key}")
        return self.services[key]


@dataclass(frozen=True)
class BuildContext:
    node: SlotNode
    tree: "SlotTree"
    runtime: SlotRuntime
    ports: Dict[str, Any]

    @property
    def config(self) -> Any:
        return getattr(self.runtime.config, "host_config", self.runtime.config)

    def resolve(self, path: str) -> Any:
        for port_path in self.node.requires.values():
            if port_path == path:
                for port, value in self.ports.items():
                    if self.node.requires.get(port) == path:
                        return value
        if path in self.runtime.services:
            return self.runtime.services[path]
        raise SlotTreeError(f"依赖未就绪：{path}")


class SlotTree:
    """从 JSON 清单构建的可递归装配树。"""

    def __init__(self, nodes: List[SlotNode], *, root: str = APP_ROOT,
                 runtime: SlotRuntime = None, backend_slots: Any = ()) -> None:
        self.root = str(root)
        paths = [node.path for node in nodes]
        if len(paths) != len(set(paths)):
            duplicates = sorted({path for path in paths if paths.count(path) > 1})
            raise SlotTreeError(f"节点重复：{', '.join(duplicates)}")
        self.nodes: Dict[str, SlotNode] = {node.path: node for node in nodes}
        self.backend_slots = list(backend_slots or ())
        self.runtime = runtime or SlotRuntime(tree=self)
        self.runtime.tree = self
        self._materialized: List[SlotComponent] = []
        self._visiting: set[str] = set()
        self._materializing: set[str] = set()
        self._dynamic: List[SlotComponent] = []
        self._disposed = False
        self._validate()

    @classmethod
    def load(cls, path: Path, *, runtime: SlotRuntime = None,
             overrides: Optional[Iterable[Dict[str, Any]]] = None) -> "SlotTree":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        nodes = list(raw.get("nodes", []))
        base = Path(path).parent
        for include in raw.get("includes", []):
            fragment_path = (base / include).resolve()
            fragment = json.loads(fragment_path.read_text(encoding="utf-8"))
            nodes.extend(fragment.get("nodes", []))
        nodes = _apply_overrides(nodes, overrides or ())
        parsed = [SlotNode(
            path=str(row.get("path") or ""),
            factory=str(row.get("factory") or ""),
            master=bool(row.get("master", False)),
            enabled=bool(row.get("enabled", True)),
            frozen=bool(row.get("frozen", False)),
            requires={str(k): str(v) for k, v in (row.get("requires") or {}).items()},
            metadata=dict(row.get("metadata") or {}),
        ) for row in nodes]
        return cls(parsed, root=str(raw.get("root") or APP_ROOT),
                   runtime=runtime, backend_slots=raw.get("backend_slots") or ())

    def _validate(self) -> None:
        for node in self.nodes.values():
            if not node.path.startswith(self.root + "/"):
                raise SlotTreeError(f"节点不在 root 下：{node.path}")
            if not node.factory:
                raise SlotTreeError(f"节点缺少 factory：{node.path}")
            for dep in node.requires.values():
                if dep not in self.nodes:
                    raise SlotTreeError(f"依赖不存在：{node.path} -> {dep}")

    def children(self, path: str) -> Tuple[SlotNode, ...]:
        prefix = path.rstrip("/") + "/"
        return tuple(sorted(
            (node for node in self.nodes.values()
             if node.path.startswith(prefix)
             and "/" not in node.path[len(prefix):]),
            key=lambda item: item.path))

    def roots(self) -> Tuple[SlotNode, ...]:
        return self.children(self.root)

    def node(self, path: str) -> SlotNode:
        try:
            return self.nodes[path]
        except KeyError as exc:
            raise SlotTreeError(f"节点不存在：{path}") from exc

    def release_component(self, component: Any) -> None:
        """Drop an assembled component's instance cache and materialized entry."""
        node = self.nodes.get(str(getattr(component, "path", "")))
        if node is not None and node.instance is component:
            node.instance = None
        if component in self._materialized:
            self._materialized.remove(component)

    def _frozen_ancestor(self, path: str) -> str:
        for node in self.nodes.values():
            if not node.frozen:
                continue
            if path == node.path or path.startswith(node.path + "/"):
                return node.path
        return ""

    def materialize(self, node: SlotNode) -> SlotComponent:
        if not node.enabled:
            raise SlotTreeError(f"节点未启用：{node.path}")
        if node.instance is not None:
            return node.instance
        if node.path in self._materializing:
            raise SlotTreeError(f"装配循环：{node.path}")
        self._materializing.add(node.path)
        try:
            ports = {}
            for port, path in node.requires.items():
                dependency = self.materialize(self.node(path))
                if not self.assemble(dependency):
                    raise SlotTreeError(f"依赖装配失败：{node.path} -> {path}")
                ports[port] = dependency.port_value()
            factory = (node.factory_callable
                       if node.factory_callable is not None
                       else _resolve(node.factory))
            context = BuildContext(
                node=node, tree=self, runtime=self.runtime, ports=ports)
            try:
                plugin = factory(context)
            except Exception as exc:
                raise SlotTreeError(f"factory 失败：{node.path}") from exc
            if not isinstance(plugin, SlotComponent):
                raise SlotTreeError(f"factory 未返回 SlotComponent：{node.path}")
            if plugin.path != node.path:
                raise SlotTreeError(
                    f"组件 path 不匹配：{node.path} != {plugin.path}")
            plugin.master = bool(node.master)
            node.instance = plugin
            self._materialized.append(plugin)
            return plugin
        finally:
            self._materializing.discard(node.path)

    def assemble(self, plugin: SlotComponent) -> bool:
        node = self.node(plugin.path)
        if node.failed:
            return False
        if node.assembled:
            return True
        if node.path in self._visiting:
            raise SlotTreeError(f"装配循环：{node.path}")
        self._visiting.add(node.path)
        try:
            for path in node.requires.values():
                dependency = self.materialize(self.node(path))
                if not self.assemble(dependency):
                    node.failed = True
                    return False
            ok = bool(plugin.assembly(self))
        finally:
            self._visiting.discard(node.path)
        node.assembled = bool(ok)
        node.failed = not bool(ok)
        return bool(ok)

    def add_dynamic(self, path: str, factory: Callable[..., SlotComponent],
                    *, metadata: Dict[str, Any] = None,
                    master: bool = True,
                    replace: bool = False) -> Callable[[], None]:
        """把运行期扩展点挂到同一棵树上；replace 允许同路径替换。"""
        key = str(path or "").strip()
        if not key.startswith(self.root + "/"):
            raise SlotTreeError(f"节点不在 root 下：{key}")
        blocked = self._frozen_ancestor(key)
        if blocked:
            raise SlotTreeError(f"冻结节点不可替换：{blocked}")
        previous_node = self.nodes.get(key)
        previous_plugin = None
        if previous_node is not None:
            if not replace:
                raise SlotTreeError(f"节点重复：{key}")
            previous_plugin = previous_node.instance
            dynamic = bool(previous_node.metadata.get("dynamic"))
            replaceable_static = previous_node.metadata.get("scope") == "session"
            if not dynamic and not replaceable_static:
                raise SlotTreeError(f"启动节点不可运行期替换：{key}")
            if previous_plugin is not None:
                deactivate = getattr(previous_plugin, "deactivate", None)
                if callable(deactivate):
                    deactivate()
                elif replaceable_static:
                    dispose = getattr(previous_plugin, "dispose", None)
                    if not callable(dispose):
                        raise SlotTreeError(f"节点不可替换：{key}")
                    dispose()
                    previous_node.instance = None
                    previous_node.assembled = False
                    previous_plugin = None
                else:
                    raise SlotTreeError(f"节点不可替换：{key}")
            self.nodes.pop(key, None)
            if previous_plugin in self._dynamic:
                self._dynamic.remove(previous_plugin)
            if previous_plugin in self._materialized:
                self._materialized.remove(previous_plugin)
        node = SlotNode(
            path=key, factory="", master=master,
            metadata={**dict(metadata or {}), "dynamic": True},
            factory_callable=factory)
        self.nodes[key] = node
        try:
            plugin = self.materialize(node)
            if not self.assemble(plugin):
                raise SlotTreeError(f"扩展点装配失败：{key}")
        except Exception:
            self.nodes.pop(key, None)
            if previous_node is not None:
                self.nodes[key] = previous_node
                if previous_plugin is not None:
                    previous_plugin.assembly(self)
                    self._dynamic.append(previous_plugin)
                    self._materialized.append(previous_plugin)
            raise
        self._dynamic.append(plugin)

        def _dispose() -> None:
            if self.nodes.get(key) is not node:
                return
            self.nodes.pop(key, None)
            plugin.dispose()
            if plugin in self._dynamic:
                self._dynamic.remove(plugin)
            if previous_node is not None:
                self.nodes[key] = previous_node
                if previous_plugin is not None:
                    previous_plugin.assembly(self)
                    self._dynamic.append(previous_plugin)
                    self._materialized.append(previous_plugin)

        return _dispose

    def dispose_all(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        for plugin in reversed(self._dynamic):
            try:
                plugin.dispose()
            except Exception as exc:
                report_error("slot_tree.dispose_dynamic", exc)
        self._dynamic.clear()
        for plugin in reversed(self._materialized):
            if plugin.path.rsplit("/", 1)[0] != self.root:
                continue
            try:
                plugin.dispose()
            except Exception as exc:
                report_error("slot_tree.dispose", exc)
        self._materialized.clear()

    def assert_no_pending(self) -> None:
        failed = [node.path for node in self.nodes.values()
                  if node.enabled and node.failed]
        if failed:
            raise SlotTreeError(f"装配失败：{', '.join(sorted(failed))}")


def _resolve(spec: str) -> Callable[[BuildContext], SlotComponent]:
    module_name, sep, attr = spec.partition(":")
    if not sep:
        raise SlotTreeError(f"factory 必须是 module:attr：{spec}")
    try:
        factory = getattr(importlib.import_module(module_name), attr)
    except (ImportError, AttributeError) as exc:
        raise SlotTreeError(f"factory 不可解析：{spec}") from exc
    if not callable(factory):
        raise SlotTreeError(f"factory 不可调用：{spec}")
    return factory


__all__ = [
    "BuildContext", "SlotNode", "SlotRuntime", "SlotTree",
    "SlotTreeError",
]
