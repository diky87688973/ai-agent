# -*- coding: utf-8 -*-
"""装配：按依赖顺序构造、记账，失败时逆序释放。

构造分两段：`scope=app` 的节点在启动时构造一次；`scope=session` 的节点只登记
成模板，由每个会话各自实例化，会话结束时逆序释放。构造只读有效视图，
因此装配主干不会绕过覆盖。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from agent.core.error_report import report_error
from agent.core.plugin_meta import read_plugin_meta, safe_dir_name
from agent.core.slot_config import SlotConfig, load_config, topo_order
from agent.core.slot_factory import (
    PluginFactories,
    missing_plugin_factories,
    resolve_factory,
    resolver_for,
)
from agent.core.slot_override import effective_view
from agent.core.slot_spec import (
    CONTAINER_KINDS,
    DECLARATIVE_KINDS,
    HOST_OWNER,
    SCOPE_APP,
    SCOPE_SESSION,
    Resolver,
    SlotAssemblyError,
    SlotConfigError,
    SlotSpec,
)


@dataclass(frozen=True)
class BuildContext:
    """factory 的第一个参数：本次构造的声明、环境与已构造的值。

    能力面就这七个字段，每一项都有唯一来源；不存在「运行时袋子」，
    能从图里取的一律走 `depend`。
    """

    spec: SlotSpec
    config: SlotConfig
    built: Mapping[str, Any] = field(default_factory=dict)
    resolver: Resolver = resolve_factory
    #: 进程根输入；无启动配置的装配（单测）为 None。
    boot_config: Any = None
    #: 本节点所属插件的数据目录；宿主与第三方 owner 为 None。
    data_dir: Optional[Path] = None
    #: 本插件 plugin-meta.json 全文；非插件节点为空表。
    plugin_meta: Mapping[str, Any] = field(default_factory=dict)

    def depend(self, path: str) -> Any:
        try:
            return self.built[path]
        except KeyError as exc:
            raise SlotAssemblyError(
                f"依赖未构造：{self.spec.path} -> {path}") from exc


def _invoke(ctx: BuildContext, args: Mapping[str, Any],
            children: Sequence[Any]) -> Any:
    """按 kind 的约定调用 factory。"""
    spec = ctx.spec
    if spec.kind in DECLARATIVE_KINDS:
        return spec
    if not spec.factory:
        return tuple(children)
    factory = ctx.resolver(spec.factory)
    if spec.kind in CONTAINER_KINDS:
        return factory(ctx, tuple(children), **args)
    return factory(ctx, **args)


def _release(ledger: Sequence[Tuple[str, Any]], tag: str) -> None:
    """逆序释放；单个释放失败只上报，其余继续。"""
    for path, value in reversed(list(ledger)):
        dispose = getattr(value, "dispose", None)
        if not callable(dispose):
            continue
        try:
            dispose()
        except Exception as exc:
            report_error(tag, exc, path=path)


def plugin_env(boot_config: Any, owner: str,
               cache: Optional[Dict[str, Mapping[str, Any]]] = None,
               plugin_root: Optional[Path] = None) -> Tuple[Optional[Path], Mapping[str, Any]]:
    """插件节点的数据目录与身份；非插件 owner 一律 (None, {})。

    判据只有一条：owner 目录存在于 `plugins/` 下才算插件。
    宿主节点（`__host__`）与第三方 owner（如 `auth`）都没有自己的插件目录。
    装配器与会话装配共用这一份，不各算一遍。
    """
    host = getattr(boot_config, "host_config", None)
    plugins_root = getattr(host, "plugins_root", None)
    data_root = getattr(host, "plugin_data_root", None)
    if not owner or owner == HOST_OWNER:
        return None, {}
    if plugins_root is None:
        return None, {}
    directory = plugin_root or Path(plugins_root) / owner
    if not directory.is_dir():
        return None, {}
    if cache is None:
        cache = {}
    if owner not in cache:
        cache[owner] = MappingProxyType(read_plugin_meta(directory))
    meta = cache[owner]
    if data_root is None:
        return None, meta
    target = Path(data_root) / safe_dir_name(owner)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        report_error("slot_loader.data_dir", exc, path=owner)
        return None, meta
    return target, meta


class SlotAssembly:
    """app 级装配：按依赖顺序构造、记账，失败时逆序释放。

    构造只读有效视图（声明 + 覆盖求值）：`self.config` 就是那个视图，
    原始声明的 `specs` 退为求值输入，因此装配主干不会绕过覆盖。
    """

    def __init__(self, config: SlotConfig, *, resolver: Resolver = resolve_factory,
                 scope: str = SCOPE_APP, boot_config: Any = None,
                 plugin_factories: PluginFactories = missing_plugin_factories) -> None:
        self.config = effective_view(config)
        self.resolver = resolver
        self.scope = scope
        self.boot_config = boot_config
        self.plugin_factories = plugin_factories
        self.values: Dict[str, Any] = {}
        self.templates: Dict[str, SlotSpec] = {}
        self._ledger: List[Tuple[str, Any]] = []
        self._disposed = False
        self._plugin_meta_cache: Dict[str, Mapping[str, Any]] = {}

    def _resolver_for(self, path: str) -> Resolver:
        """本节点的解析器：宿主 factory 走 self.resolver，插件 factory 走注入的工厂。

        无插件根时不自作主张退回宿主解析器：那等于把插件 factory 当宿主模块导，
        报出来的错会变成「factory 不可解析」，掩盖真正原因。
        """
        return resolver_for(self.config, path, self.plugin_factories, self.resolver)

    def context_for(self, spec: SlotSpec) -> BuildContext:
        """按节点算出它的装配上下文：环境部分是只读的，运行时部分是本次的值。"""
        origin = self.config.origins.get(spec.path, spec.owner)
        data_dir, meta = plugin_env(self.boot_config, origin, self._plugin_meta_cache,
                                    self.config.plugin_roots.get(origin))
        return BuildContext(
            spec=spec, config=self.config, built=self.values,
            resolver=self._resolver_for(spec.path), boot_config=self.boot_config,
            data_dir=data_dir, plugin_meta=meta)

    def build(self) -> "SlotAssembly":
        try:
            for path in topo_order(self.config):
                spec = self.config.spec(path)
                if spec.scope != self.scope:
                    self.templates[path] = spec
                    continue
                self._construct(spec)
        except Exception:
            self.dispose()
            raise
        return self

    def get(self, path: str) -> Any:
        try:
            return self.values[path]
        except KeyError as exc:
            raise SlotAssemblyError(f"节点未构造：{path}") from exc

    def prepare_plugins(self, config: SlotConfig, reload_origins: Any = ()) -> "SlotAssembly":
        """复用宿主实例，隔离构造候选插件；候选失败只释放候选资源。"""
        candidate = SlotAssembly(
            config, resolver=self.resolver, boot_config=self.boot_config,
            plugin_factories=self.plugin_factories)
        try:
            for path in topo_order(candidate.config):
                spec = candidate.config.spec(path)
                if spec.scope != self.scope:
                    candidate.templates[path] = spec
                elif candidate.config.origin_of(path) == HOST_OWNER and path in self.values:
                    if spec != self.config.spec(path):
                        raise SlotAssemblyError(f"热插拔不能修改宿主声明：{path}")
                    if spec.factory or self._can_reuse(candidate, spec, ()):
                        candidate.values[path] = self.values[path]
                    else:
                        candidate._construct(spec)
                elif self._can_reuse(candidate, spec, reload_origins):
                    candidate.values[path] = self.values[path]
                else:
                    candidate._construct(spec)
        except Exception:
            candidate.dispose()
            raise
        return candidate

    def _can_reuse(self, candidate: "SlotAssembly", spec: SlotSpec,
                   reload_origins: Any) -> bool:
        if (spec.path not in self.values or spec.path not in self.config.paths()
                or spec != self.config.spec(spec.path)
                or candidate.config.origin_of(spec.path) in reload_origins):
            return False
        dependencies = [*spec.requires.values(),
                        *(child.path for child in candidate.config.children(spec.path)
                          if child.scope == self.scope)]
        old_children = tuple(child.path for child in self.config.children(spec.path))
        new_children = tuple(child.path for child in candidate.config.children(spec.path))
        return old_children == new_children and all(
            candidate.values.get(path) is self.values.get(path) for path in dependencies)

    def publish_plugins(self, candidate: "SlotAssembly") -> None:
        """发布已完成绑定的插件代，宿主资源继续由当前装配器持有。"""
        retired = [(path, value) for path, value in self._ledger
                   if candidate.values.get(path) is not value]
        self._ledger = [(path, value) for path, value in self._ledger
                        if candidate.values.get(path) is value]
        self._ledger.extend(candidate._ledger)
        candidate._ledger.clear()
        self.config = candidate.config
        self.values = candidate.values
        self.templates = candidate.templates
        _release(retired, "slot_loader.retire_plugins")

    def _construct(self, spec: SlotSpec) -> None:
        try:
            args = {key: self.get(dep) for key, dep in spec.requires.items()}
            children = [self.get(child.path)
                        for child in self.config.children(spec.path)
                        if child.scope == self.scope]
            value = _invoke(self.context_for(spec), args, children)
        except (SlotAssemblyError, SlotConfigError):
            raise
        except Exception as exc:
            raise SlotAssemblyError(f"节点构造失败：{spec.path}") from exc
        self.values[spec.path] = value
        self._ledger.append((spec.path, value))

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        _release(self._ledger, "slot_loader.dispose")
        self._ledger.clear()
        self.values.clear()


def build_from_config(path: Path,
                      resolver: Optional[Resolver] = None,
                      boot_config: Any = None,
                      plugin_factories: PluginFactories = missing_plugin_factories,
                      ) -> SlotAssembly:
    """读配置、校验、拓扑装配，返回可 dispose 的装配结果。

    默认用模块级 `resolve_factory` 解析 factory，故调用方不需要传参。
    `boot_config` 是进程根输入，工厂通过 ctx.boot_config 取用；
    插件 factory 的加载方式由 `plugin_factories` 注入，未注入时解析插件节点即报错。
    不读全局状态；出错抛 `SlotConfigError`（配置非法或 factory 不可解析）
    或 `SlotAssemblyError`（节点构造失败，已构造的节点已逆序释放）。
    """
    target = Path(path)
    return SlotAssembly(
        load_config(target), resolver=resolver or resolve_factory,
        boot_config=boot_config,
        plugin_factories=plugin_factories).build()


class SessionAssembly:
    """会话级装配：只构造 session 节点，依赖先在本会话内解析。

    与 app 级同源：`self.config` 也是有效视图，会话装配同样不绕过覆盖。
    """

    def __init__(self, config: SlotConfig, app_values: Mapping[str, Any], *,
                 resolver: Resolver = resolve_factory,
                 boot_config: Any = None) -> None:
        self.config = effective_view(config)
        self.app_values = dict(app_values or {})
        self.resolver = resolver
        self.boot_config = boot_config
        self.values: Dict[str, Any] = {}
        self._ledger: List[Tuple[str, Any]] = []
        self._disposed = False
        self._plugin_meta_cache: Dict[str, Mapping[str, Any]] = {}

    def context_for(self, spec: SlotSpec) -> BuildContext:
        """会话节点的上下文：环境与 app 级同形，运行时是本会话的值。"""
        origin = self.config.origins.get(spec.path, spec.owner)
        data_dir, meta = plugin_env(self.boot_config, origin, self._plugin_meta_cache,
                                    self.config.plugin_roots.get(origin))
        return BuildContext(
            spec=spec, config=self.config, built=self.values,
            resolver=self.resolver, boot_config=self.boot_config,
            data_dir=data_dir, plugin_meta=meta)

    def build(self) -> "SessionAssembly":
        try:
            for path in topo_order(self.config):
                spec = self.config.spec(path)
                if spec.scope != SCOPE_SESSION:
                    continue
                self._construct(spec)
        except Exception:
            self.dispose()
            raise
        return self

    def get(self, path: str) -> Any:
        if path in self.values:
            return self.values[path]
        if path in self.app_values:
            return self.app_values[path]
        raise SlotAssemblyError(f"依赖未就绪：{path}")

    def _construct(self, spec: SlotSpec) -> None:
        try:
            args = {key: self.get(dep) for key, dep in spec.requires.items()}
            children = [self.get(child.path) for child in self.config.children(spec.path)]
            value = _invoke(self.context_for(spec), args, children)
        except (SlotAssemblyError, SlotConfigError):
            raise
        except Exception as exc:
            raise SlotAssemblyError(f"节点构造失败：{spec.path}") from exc
        self.values[spec.path] = value
        self._ledger.append((spec.path, value))

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        _release(self._ledger, "slot_loader.dispose_session")
        self._ledger.clear()
        self.values.clear()
