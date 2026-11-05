# -*- coding: utf-8 -*-
"""宿主装配组件：文件安全、应用门面、插件装载、内核模块容器。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Tuple

from agent.app_model_policy import apply_model_policy
from agent.common.status import (
    MODEL_CONFIG_NONE,
    PLUGIN_ERROR,
)
from agent.config import get_backup_retention_days
from agent.core.error_report import report_error
from agent.core.slot_config import SlotConfig
from agent.core.slot_factory import resolve_factory
from agent.core.slot_spec import SlotSpec
from agent.mechanisms.file_safety import build_file_safety


@dataclass(frozen=True)
class FileSafety:
    """备份与回收两份资源；由需要它们的工具按名字取用。"""

    backups: Any
    recycle: Any


def make_files(ctx: Any) -> FileSafety:
    """建文件安全资源并做一次保留期剪枝。"""
    config = ctx.boot_config
    backups, recycle = build_file_safety(
        config.data_root, config.backup_root, config.recycle_root)
    days = (get_backup_retention_days()
            if config.backup_retention_days is None
            else int(config.backup_retention_days))
    if days > 0:
        try:
            backups.prune(days)
        except Exception as exc:
            report_error("boot.backup_prune", exc)
    return FileSafety(backups=backups, recycle=recycle)


def make_facade(ctx: Any, **requires: Any) -> Any:
    """应用门面：把 requires 声明的服务逐个登记进 AppContext。

    登记名就是 requires 的键，与内核 `SERVICE_*` 常量一一对应；
    缺一个键就意味着图里少了一条边，`context.has` 会如实报不存在。
    """
    from agent.app import App
    from agent.core.context import AppContext
    from agent.core.error_report import bind_error_sink

    config = ctx.boot_config
    host = config.host_config
    context = AppContext(host.slots)
    for key, value in requires.items():
        if value is not None:
            context.register(key, value)
    unbind = bind_error_sink(requires["error_log"].report)
    app = App(
        context,
        context_defaults={
            "full_user_rounds": int(config.context_defaults["full_user_rounds"]),
            "reasoning_replay_tokens": int(config.context_defaults["reasoning_replay_tokens"]),
        },
    )
    # 初值：统一降级态。真实策略由 `apply_model_policy` 在装载与绑定后各算一次。
    app._available_models = []
    app._error_unbind = unbind
    app.model_config_state = MODEL_CONFIG_NONE
    return app


def make_plugins(ctx: Any, facade: Any = None) -> Any:
    """装载插件：把宿主交给 App，按模型目录刷新可用模型表。

    `host.tree` 不再赋值：旧装配树不进新架构，插件贡献不靠树分发。
    """
    config = ctx.boot_config
    app = facade
    host = app.plugin_host
    host.app = app
    reports = host.load_manifest(config.plugin_manifest)
    ok = not any(str(report.status) == PLUGIN_ERROR for report in reports)
    # 此刻目录来源尚未绑定，只能落降级态；目录权威由 `_bind` 后再调一次落定。
    apply_model_policy(app)
    return ok


class KernelModuleGroup:
    """内核模块容器：持会话预算，并在每次创建会话引擎时构造一遍模块链。

    模块声明是 `scope=session` 的节点，本身不进进程装配；
    这里是它们唯一的构造入口，所以每次会话都按节点声明重新构造一遍。
    """

    def __init__(self, config: SlotConfig, *,
                 modules: Tuple[SlotSpec, ...],
                 loop_config: Any = None,
                 resolver: Callable[..., Any] = resolve_factory) -> None:
        self._config = config
        self._modules = modules
        self._resolver = resolver
        self.loop_config = loop_config

    def configure_loop(self, *, image_turns: int, image_max: int,
                       max_passes: int) -> None:
        from agent.core.modules.slot_chain import AgentLoopConfig
        self.loop_config = AgentLoopConfig(
            image_turns=int(image_turns), image_max=int(image_max),
            max_passes=max(1, int(max_passes)))

    def build_modules(self, context: Any) -> List[Any]:
        from agent.core.module import ModuleBase
        modules = []
        for spec in self._modules:
            factory = self._resolver(spec.factory)
            module = factory(context, ())
            if not isinstance(module, ModuleBase):
                raise TypeError(
                    f"内核模块类型非法：{spec.path} / {type(module).__name__}")
            modules.append(module)
        return modules


def make_kernel_group(ctx: Any, children: Any = (), **requires: Any) -> KernelModuleGroup:
    """建内核模块容器：会话预算取自启动配置，模块清单取自当期配置。

    容器类工厂一律收到已构造的子节点；本节点的子节点是会话级模块，
    进程装配阶段一个也不会构造（见 `_construct` 按 scope 过滤），
    所以真正的模块清单要自己从配置里按 order 取。
    """
    from agent.core.modules.slot_chain import AgentLoopConfig

    config = ctx.boot_config
    loop = AgentLoopConfig(
        image_turns=int(config.image_turns), image_max=int(config.image_max),
        max_passes=max(1, int(config.max_passes)))
    prefix = "app/kernel/modules/"
    children = [
        ctx.config.specs[path] for path in ctx.config.specs
        if path.startswith(prefix) and "/" not in path[len(prefix):]
        and ctx.config.specs[path].scope == "session"
    ]
    children.sort(key=lambda spec: (spec.order is None, spec.order or 0, spec.path))
    return KernelModuleGroup(ctx.config, modules=tuple(children), loop_config=loop,
                             resolver=ctx.resolver)


__all__ = ["FileSafety", "KernelModuleGroup", "make_facade", "make_files",
           "make_kernel_group", "make_plugins"]
