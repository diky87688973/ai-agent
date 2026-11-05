# -*- coding: utf-8 -*-
"""启动器：合并片段、装配插口、返回 App。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional, Tuple

from agent.app_model_policy import apply_model_policy
from agent.boot.config import BootConfig, HostBootConfig
from agent.boot.plugin_assembly import discover
from agent.capabilities.plugins import resolve_plugin_factory
from agent.capabilities.slot_binder import SlotBinder
from agent.capabilities.slot_registry import SlotRegistry
from agent.config import (
    DEFAULT_MAX_PASSES,
    default_data_root,
    default_plugins_root,
    get_context,
    get_max_passes,
)
from agent.core.slot_assembly import SlotAssembly
from agent.core.slot_config import SlotConfig
from agent.core.slot_fragments import load_merged
from agent.core.slot_spec import SlotAssemblyError
from agent.mechanisms.executors import ExecutorRegistry
from agent.mechanisms.providers.missing import MissingProvider
from agent.session_paths import ensure_layout

#: 项目根：本文件在 `agent/boot/` 下，往上三层即仓库根。
REPO_ROOT = Path(__file__).resolve().parents[2]


def _build_boot_config(
    *,
    provider: Any,
    store: Any,
    context_factory: Optional[Callable[[str], Any]],
    backup_root: Optional[Path],
    recycle_root: Optional[Path],
    live_state: Any,
    mesh: Any,
    backup_retention_days: Optional[int],
    plugins_dir: Optional[Path],
    compactor_factory: Optional[Callable[[str], Any]],
    config_ready: Optional[bool],
    data_root: Optional[Path],
    plugin_manifest: Any,
) -> Tuple[BootConfig, Path]:
    """进程根输入 → BootConfig；插件根一并交回，装配要用同一个根。"""
    root = Path(data_root) if data_root is not None else default_data_root()
    ensure_layout(root)
    slots = SlotRegistry()
    executors = ExecutorRegistry(slots)
    plugins_root = Path(plugins_dir) if plugins_dir is not None else default_plugins_root()
    overlay = discover(plugins_root, plugin_manifest)
    cfg = get_context()
    if config_ready is None:
        ready = provider is not None and not isinstance(provider, MissingProvider)
    else:
        ready = bool(config_ready)
    host_config = HostBootConfig(
        data_root=root, live_state=live_state, mesh=mesh, slots=slots,
        executors=executors, provider=provider, available=(), default_model="",
        store=store, context_factory=context_factory,
        compactor_factory=compactor_factory, plugins_root=plugins_root,
        plugin_data_root=root / "plugin")
    boot = BootConfig(
        data_root=root, host_config=host_config,
        backup_root=backup_root, recycle_root=recycle_root,
        backup_retention_days=backup_retention_days,
        context_defaults={
            "full_user_rounds": int(cfg["full_user_rounds"]),
            "reasoning_replay_tokens": int(cfg["reasoning_replay_tokens"]),
        },
        image_turns=int(cfg["image_turns"]), image_max=int(cfg["image_max"]),
        max_passes=get_max_passes() if get_max_passes() else DEFAULT_MAX_PASSES,
        available=(), default_model="", config_ready=ready,
        plugin_manifest=overlay.manifest,
    )
    return boot, plugins_root


def _assemble(config: SlotConfig, boot: BootConfig) -> Tuple[SlotAssembly, Any]:
    """按配置装配并交出 App；必需产物缺失时先释放再上抛。"""

    def plugin_factories(origin: str, spec: str, path: str,
                         plugins_root: Path) -> Callable[..., Any]:
        """把配置里的插件根直接交给解析器；包名与模块名规则全在 capabilities 侧。"""
        return resolve_plugin_factory(plugins_root, origin, spec, path, REPO_ROOT)

    assembly = SlotAssembly(
        config, boot_config=boot,
        plugin_factories=plugin_factories)
    try:
        assembly.build()
        app = assembly.get("app/boot/facade")
    except Exception:
        # 装配器内部已按依赖逆序释放；这里只补上「结果不可用」这件事。
        assembly.dispose()
        raise
    if app is None:
        assembly.dispose()
        raise SlotAssemblyError("装配未产出 App")
    if assembly.get("app/kernel/modules") is None:
        assembly.dispose()
        raise SlotAssemblyError("内核模块容器未装配")
    return assembly, app


def _bind(app: Any, assembly: SlotAssembly, boot: BootConfig) -> Any:
    """装配之后才登记：节点怎么进注册表归绑定器，装配器只负责构造。"""
    binder = SlotBinder(
        plugin_host=assembly.get("app/host/services/plugin_host"),
        registry=assembly.get("app/host/services/registry"),
        event_bus=assembly.get("app/host/services/event_bus"),
        contributions=assembly.get("app/host/services/contributions"),
        prompt_sections=assembly.get("app/host/services/prompt_sections"),
        prompt_tail=assembly.get("app/host/services/prompt_tail"),
        context_sources=assembly.get("app/host/services/context_sources"),
        context_hooks=assembly.get("app/host/services/context_hooks"),
        model_catalog=assembly.get("app/host/services/model_catalog"),
        executors=boot.host_config.executors,
        ranks=app.plugin_host.ranks(),
    ).bind(assembly)
    app._kernel_group = assembly.get("app/kernel/modules")
    app._slot_assembly = assembly
    app._slot_binder = binder
    # 目录来源刚刚在 bind 里建立：重算一次模型策略，否则目录权威落不到 App 上
    # （装载阶段调那次时 catalog 还不权威，见 apply_model_policy 的说明）。
    apply_model_policy(app)
    return app


def boot_app(
    *,
    provider: Any = None,
    store: Any = None,
    context_factory: Optional[Callable[[str], Any]] = None,
    backup_root: Optional[Path] = None,
    recycle_root: Optional[Path] = None,
    live_state: Any = None,
    mesh: Any = None,
    backup_retention_days: Optional[int] = None,
    plugins_dir: Optional[Path] = None,
    plugins_path: Optional[Path] = None,
    compactor_factory: Optional[Callable[[str], Any]] = None,
    config_ready: Optional[bool] = None,
    data_root: Optional[Path] = None,
    plugin_manifest: Any = (),
) -> Any:
    boot, plugins_root = _build_boot_config(
        provider=provider, store=store, context_factory=context_factory,
        backup_root=backup_root, recycle_root=recycle_root,
        live_state=live_state, mesh=mesh,
        backup_retention_days=backup_retention_days, plugins_dir=plugins_dir,
        compactor_factory=compactor_factory, config_ready=config_ready,
        data_root=data_root, plugin_manifest=plugin_manifest)
    config = load_merged(REPO_ROOT, plugins_root=plugins_root)
    assembly, app = _assemble(config, boot)
    return _bind(app, assembly, boot)


__all__ = ["boot_app"]
