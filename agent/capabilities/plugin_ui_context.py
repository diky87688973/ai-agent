# -*- coding: utf-8 -*-
"""插件 UI、设置、路由与执行器贡献方法。"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from agent.capabilities.plugin_ledger import Disposer
from agent.capabilities.registry import ToolPlugin
from agent.capabilities.slot_registry import (
    SETTINGS_PREFIX,
    canonical_slot_path,
    route_slot_path,
)
from agent.core.app_path import app_path
from agent.core.error_report import report_error


class PluginUiContextMixin:
    """由 PluginContext 继承；依赖宿主提供的 _ui/_settings/_executors 等字段。"""

    def add_executor(self, name: str, fn: Callable[[Dict[str, Any]], Dict[str, Any]]) -> Disposer:
        """登记写类工具的执行器（提交路径扩展点；需接入 ExecutorRegistry）。

        插件自己的写类工具走 `confirm_id` 制预览时，提交那一刻按工具名来这里取。
        """
        if self._executors is None:
            raise RuntimeError("插件未接入执行器注册表（PluginHost 未传 executors）")

        executor_path = app_path("backend", "tools", name, "executor")

        def register() -> Disposer:
            backend = self._backend_path(executor_path, "executor", fn)
            try:
                return self._executors.add(name, fn, owner=self.name, replace=True)
            except Exception:
                backend()
                raise

        return self._contribute(
            executor_path, register, replace=True)
    def register_tool(self, plugin: ToolPlugin) -> Disposer:
        """向工具注册表注册插件；子智能体可见性由 set_subagent_tools 声明。"""
        tool_path = app_path("backend", "tools", plugin.name)

        def register() -> Disposer:
            # 先落 backend 记录；后续注册失败时撤掉它，避免只留下半套贡献。
            backend = self._backend_path(tool_path, "tool", plugin,
                                         {"schema": getattr(plugin, "parameters", {})})
            try:
                return self._registry.register(plugin, owner=self.name)
            except Exception:
                backend()
                raise

        return self._contribute(
            tool_path, register, replace=True)
    def set_runtime(self, runtime: Any) -> None:
        """登记本插件的运行时对象，供壳层按插件名取用。

        插件被 `importlib` 以动态模块名加载，壳层没法 import 到同一个模块对象，
        所以插件自己持有的运行时必须经宿主登记出来 —— 否则壳层会另建一份，
        两边状态各写各的（勾选存进去却注入不出来）。
        """
        runtime_path = app_path("backend", "runtime", self.name)

        def register() -> Disposer:
            backend = self._backend_path(runtime_path, "runtime", runtime)
            if self._host is not None:
                self._host.register_runtime(self.name, runtime)
            return backend

        self._contribute(runtime_path, register)
    def add_route(
        self,
        method: str,
        path: str,
        handler: Callable[[Dict[str, Any]], Any],
        *,
        slot_path: str,
        master: bool = False,
    ) -> Disposer:
        """注册插件自己的 HTTP 端点；slot_path 必须显式声明。

        HTTP 路径只许是单段字面量（不许 `..`、通配或前导斜杠），命名空间不可越出。
        """
        tree_path = canonical_slot_path(str(slot_path or "").strip())

        def register() -> Disposer:
            backend = self._backend_path(
                tree_path, "http-route", handler, {"method": method, "path": path})
            try:
                return self._contrib().add_route(
                    self.name, method, path, handler)
            except Exception:
                backend()
                raise

        return self._contribute(tree_path, register, master=master,
                                kind="http-route")
    def add_context_assembly_hook(
        self,
        fn: Callable[[List[Dict[str, Any]], str], Any],
        *,
        path: str,
        master: bool = False,
    ) -> Disposer:
        """注册完整上下文拼装钩子；path 必须显式声明。"""
        if self._context_hooks is None:
            raise RuntimeError("插件未接入上下文拼装钩子（PluginHost 未传 context_hooks）")
        hook_path = canonical_slot_path(str(path or "").strip())

        def register() -> Disposer:
            backend = self._backend_path(hook_path, "assembly-hook", fn)
            try:
                return self._context_hooks.add(fn)
            except Exception:
                backend()
                raise

        return self._contribute(hook_path, register, master=master, kind="assembly-hook")
    def add_settings_panel(
        self, panel_id: str, title: str, *, order: int = 0,
        replace: bool = False,
    ) -> Disposer:
        """注册新的设置面板；渲染、保存和生命周期由宿主负责。"""
        if self._settings is None:
            raise RuntimeError("插件未接入设置注册表")
        def register() -> Disposer:
            return self._settings.add_panel(
                self.name, panel_id, title, order=order, replace=replace)

        panel_path = canonical_slot_path(panel_id)
        if not panel_path.startswith(SETTINGS_PREFIX):
            panel_path = app_path("settings", panel_path)
        return self._contribute(panel_path, register, replace=replace)
    def add_settings_item(
        self, parent: str, item_id: str, *,
        kind: str, label: str, default: Any = "",
        options: Any = (), hint: str = "", order: int = 0,
        save: Any = None, load: Any = None, replace: bool = False,
    ) -> Disposer:
        """注册设置条目；保存回调由插件实现并返回成功/失败。"""
        if self._settings is None:
            raise RuntimeError("插件未接入设置注册表")
        path = canonical_slot_path(f"{parent.rstrip('/')}/{item_id.strip('/')}")

        def register() -> Disposer:
            return self._settings.add_item(
                self.name, parent, item_id, kind=kind, label=label,
                default=default, options=options, hint=hint, order=order,
                save=save, load=load, replace=replace,
            )

        return self._contribute(path, register, replace=replace)
    def add_ui_slot(self, path: str, *, kind: str, children: str,
                    allowed_kinds: Any = (), fixed_children: Any = (),
                    owner: str = "*", replace: bool = False) -> Disposer:
        """注册 UI 插口；基础 UI 插件使用。"""
        if self._ui is None:
            raise RuntimeError("插件未接入 UI 注册表")
        path = canonical_slot_path(path)

        def register() -> Disposer:
            return self._ui.add_slot(
                path, kind=kind, children=children,
                allowed_kinds=allowed_kinds,
                fixed_children=fixed_children, owner=owner,
                replace=replace)

        return self._contribute(path, register, replace=replace)
    def bind(self, path: str, implementation: Any, *, mode: str = "replace",
             priority: int = 0, owner: Optional[str] = None) -> Disposer:
        """把插件实现绑定到已暴露的 slot；HTTP 路由使用 bind_route。"""
        slots = getattr(self._host, "slots", None)
        if slots is None:
            raise RuntimeError("插件未接入 SlotRegistry")
        path = canonical_slot_path(path)
        if path not in slots.nodes:
            raise ValueError(f"插口不存在：{path}")
        binding = slots.bind(
            path, implementation, owner=owner or self.name,
            mode=mode, priority=priority)
        self._disposers.append(binding.dispose)
        return binding.dispose
    def bind_route(self, method: str, path: str, implementation: Any,
                   *, priority: int = 0, owner: Optional[str] = None) -> Disposer:
        """按 HTTP 方法和路径绑定 route slot；路径身份由统一编码生成。"""
        key = route_slot_path(method, path)
        slots = getattr(self._host, "slots", None)
        if slots is None:
            raise RuntimeError("插件未接入 SlotRegistry")
        if key not in slots.nodes:
            slots.register_slot(
                key, kind="http-route", default=None, default_owner="__host__")
        return self.bind(key, implementation, mode="replace",
                         priority=priority, owner=owner)
    def add_ui_item(self, path: str, *, kind: str,
                    handler: Any = None, props: Any = None,
                    order: Any = None, replace: bool = False) -> Disposer:
        """注册 UI 控件；路径必须落在已声明插口内。"""
        if self._ui is None:
            raise RuntimeError("插件未接入 UI 注册表")
        path = canonical_slot_path(path)

        def register() -> Disposer:
            return self._ui.add_item(
                path, kind=kind, owner=self.name, handler=handler,
                props=props, order=order, replace=replace)

        return self._contribute(path, register, replace=replace)
    def add_model_catalog(self, entries: Any) -> Disposer:
        """声明本插件的模型清单；`entries` 是条目序列或每次重读配置的回调。

        来源名固定是插件名：目录只认一个权威，冲突时保留先登记的来源并留痕，
        插件装载不因此失败（装载顺序不是契约，但结果必须确定且可审计）。
        """
        if self._model_catalog is None:
            raise RuntimeError("插件未接入模型目录（PluginHost 未传 model_catalog）")
        def register() -> Disposer:
            try:
                return self._model_catalog.set_source(self.name, entries)
            except RuntimeError as exc:
                report_error("plugin.model_catalog", exc, plugin=self.name)
                return lambda: None

        return self._contribute(
            app_path("backend", "models", "catalog", self.name), register)
