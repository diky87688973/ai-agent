# -*- coding: utf-8 -*-
"""自装配组件工厂：容器、服务叶子、运行时门面。"""
from __future__ import annotations

from typing import Any

from agent.common.status import (
    MODEL_CONFIG_CATALOG,
    MODEL_CONFIG_CONFIG,
    MODEL_CONFIG_NONE,
    PLUGIN_ERROR,
)
from agent.config import get_backup_retention_days
from agent.core.context import SERVICE_MODEL_CATALOG
from agent.core.slot import SlotContainer, SlotLeaf, SlotValue
from agent.mechanisms.file_safety import build_file_safety


class SlotResult(SlotLeaf):
    """装配结果由子阶段决定的组件；失败可参与 master 传播。"""

    def __init__(self, path: str, ok: bool, *, master: bool = False) -> None:
        super().__init__(path, master=master)
        self._ok = bool(ok)

    def assembly(self, tree: Any) -> bool:
        return self._ok


class KernelModuleGroup(SlotContainer):
    """内核模块容器：拥有模块根路径并逐回合构造模块链。"""

    def __init__(self, path: str, *, loop_config: Any = None,
                 master: bool = True) -> None:
        super().__init__(path, master=master)
        self.tree = None
        self.loop_config = loop_config

    def assembly(self, tree: Any) -> bool:
        self.tree = tree
        ok = super().assembly(tree)
        if ok:
            tree.runtime.resources["kernel_group"] = self
        return ok

    def configure_loop(self, *, image_turns: int, image_max: int,
                       max_passes: int) -> None:
        from agent.core.modules.slot_chain import AgentLoopConfig
        self.loop_config = AgentLoopConfig(
            image_turns=int(image_turns), image_max=int(image_max),
            max_passes=max(1, int(max_passes)))

    def build_modules(self, context: Any) -> list[Any]:
        from agent.core.module import ModuleBase
        if self.tree is None:
            raise RuntimeError("内核模块容器尚未装配")
        rows = []
        for node in self.tree.children(self.path):
            if not node.enabled or node.metadata.get("scope") != "session":
                continue
            rows.append((int(node.metadata.get("order", 999)), node.path))
        rows.sort()
        modules = []
        for _order, path in rows:
            node = self.tree.node(path)
            plugin = self.tree.materialize(node)
            children = []
            for child_node in self.tree.children(path):
                if not child_node.enabled:
                    continue
                child = self.tree.materialize(child_node)
                if not self.tree.assemble(child):
                    raise RuntimeError(f"内核模块子插口装配失败：{child_node.path}")
                children.append(child)
            module = plugin.build(context, children)
            if not isinstance(module, ModuleBase):
                raise TypeError(f"内核模块类型非法：{path} / {type(module).__name__}")
            modules.append(module)
        return modules


def kernel_group(ctx: Any) -> KernelModuleGroup:
    config = ctx.runtime.config
    from agent.core.modules.slot_chain import AgentLoopConfig
    loop = AgentLoopConfig(
        image_turns=int(config.image_turns), image_max=int(config.image_max),
        max_passes=max(1, int(config.max_passes)))
    return KernelModuleGroup(
        ctx.node.path, loop_config=loop, master=ctx.node.master)


class KernelModulePlugin(SlotLeaf):
    """会话级内核模块描述符；真正的模块在每回合构造。"""

    def __init__(self, path: str, builder: Any, *, master: bool = False) -> None:
        super().__init__(path, master=master)
        self.builder = builder

    def build(self, context: Any, children: Any = ()) -> Any:
        return self.builder(context, children)


def kernel_module(ctx: Any) -> KernelModulePlugin:
    spec = str(ctx.node.metadata.get("builder") or "")
    module_name, sep, attr = spec.partition(":")
    if not sep:
        raise ValueError(f"内核模块 builder 非法：{spec}")
    import importlib
    builder = getattr(importlib.import_module(module_name), attr)
    return KernelModulePlugin(ctx.node.path, builder, master=ctx.node.master)


def append_context(ctx: Any) -> SlotValue:
    """内核对上下文追加插口的通用叶子；builder 由插件提供。"""
    spec = str(ctx.node.metadata.get("builder") or "")
    module_name, sep, attr = spec.partition(":")
    if not sep:
        raise ValueError(f"builder 必须是 module:attr：{spec}")
    import importlib
    builder = getattr(importlib.import_module(module_name), attr)
    return SlotValue(ctx.node.path, builder, master=ctx.node.master)


def service_component(ctx: Any) -> SlotValue:
    spec = str(ctx.node.metadata.get("builder") or "")
    module_name, sep, attr = spec.partition(":")
    if not sep:
        raise ValueError(f"builder 必须是 module:attr：{spec}")
    import importlib
    builder = getattr(importlib.import_module(module_name), attr)
    value = builder(ctx)
    # 服务键默认取节点路径；节点可显式声明 `metadata.service`，避免调用方
    # 把某个树路径当成服务名硬编码。
    service_key = str(ctx.node.metadata.get("service") or ctx.node.path)
    ctx.runtime.services[service_key] = value
    return SlotValue(ctx.node.path, value, master=ctx.node.master)


def container(ctx: Any) -> SlotContainer:
    return SlotContainer(ctx.node.path, master=ctx.node.master)


def files(ctx: Any) -> SlotValue:
    config = ctx.runtime.config
    backups, recycle = build_file_safety(
        config.data_root, config.backup_root, config.recycle_root)
    days = (get_backup_retention_days()
            if config.backup_retention_days is None
            else int(config.backup_retention_days))
    if days > 0:
        try:
            backups.prune(days)
        except Exception as exc:
            from agent.core.error_report import report_error
            report_error("boot.backup_prune", exc)
    ctx.runtime.resources["backups"] = backups
    ctx.runtime.resources["recycle"] = recycle
    return SlotValue(ctx.node.path, (backups, recycle), master=ctx.node.master)


def facade(ctx: Any) -> SlotLeaf:
    from agent.app import App
    from agent.core.context import AppContext
    from agent.core.error_report import bind_error_sink

    runtime = ctx.runtime
    config = runtime.config
    context = AppContext(runtime.resources["slots"])
    for key, value in ctx.ports.items():
        if value is not None:
            context.register(key, value)
    unbind = bind_error_sink(ctx.ports["error_log"].report)
    app = App(
        context,
        context_defaults={
            "full_user_rounds": int(config.context_defaults["full_user_rounds"]),
            "reasoning_replay_tokens": int(config.context_defaults["reasoning_replay_tokens"]),
        },
    )
    app._available_models = list(config.available)
    app._error_unbind = unbind
    app.model_config_state = MODEL_CONFIG_CONFIG if config.config_ready else MODEL_CONFIG_NONE
    runtime.app = app
    return SlotLeaf(ctx.node.path, master=ctx.node.master)


def plugins(ctx: Any) -> SlotLeaf:
    app = ctx.runtime.app
    host = app.plugin_host
    host.app = app
    host.tree = ctx.tree
    reports = host.load_manifest(ctx.runtime.config.plugin_manifest)
    ok = not any(str(report.status) == PLUGIN_ERROR for report in reports)
    snapshot = app.context.get(SERVICE_MODEL_CATALOG).snapshot()
    if snapshot.authoritative:
        app.model_config_state = MODEL_CONFIG_CATALOG
        app._available_models = [item.id for item in snapshot.entries]
        app.live_state.default_model = snapshot.default_id
        app.provider.reload_policy(
            allowed_ids=app._available_models,
            default_id=snapshot.default_id, fallback_to_default=False)
    elif app.model_config_state == MODEL_CONFIG_CONFIG:
        app._available_models = list(ctx.runtime.config.available)
        app.live_state.default_model = ctx.runtime.config.default_model
        app.provider.reload_policy(
            allowed_ids=app._available_models,
            default_id=ctx.runtime.config.default_model, fallback_to_default=False)
    else:
        app._available_models = []
        app.live_state.default_model = ""
        app.provider.reload_policy(
            allowed_ids=[], default_id="", fallback_to_default=False)
    return SlotResult(ctx.node.path, ok, master=ctx.node.master)


__all__ = [
    "KernelModuleGroup", "KernelModulePlugin", "SlotResult", "append_context",
    "container", "facade", "files", "kernel_group", "kernel_module",
    "plugins", "service_component",
]
