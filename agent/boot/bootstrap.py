# -*- coding: utf-8 -*-
"""自装配启动器：读取唯一树，递归装配，返回 App。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from agent.boot.config import BootConfig, HostBootConfig
from agent.boot.plugin_assembly import discover
from agent.capabilities.slot_registry import SlotRegistry
from agent.config import (
    DEFAULT_MAX_PASSES,
    default_data_root,
    default_plugins_root,
    get_context,
    get_max_passes,
)
from agent.core.slot_tree import SlotRuntime, SlotTree, SlotTreeError
from agent.mechanisms.executors import ExecutorRegistry
from agent.mechanisms.providers.missing import MissingProvider
from agent.session_paths import ensure_layout


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
    data_root = Path(data_root) if data_root is not None else default_data_root()
    ensure_layout(data_root)
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
        data_root=data_root, live_state=live_state, mesh=mesh, slots=slots,
        executors=executors, provider=provider, available=(), default_model="",
        store=store, context_factory=context_factory,
        compactor_factory=compactor_factory, plugins_root=plugins_root,
        plugin_data_root=data_root / "plugin")
    boot = BootConfig(
        data_root=data_root, host_config=host_config,
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
    runtime = SlotRuntime(config=boot)
    runtime.resources["slots"] = slots
    runtime.resources["executors"] = executors
    tree = SlotTree.load(Path(__file__).with_name("slot_tree.json"),
                           runtime=runtime, overrides=overlay.nodes)
    runtime.resources["backend_slots"] = tree.backend_slots
    for node in tree.roots():
        plugin = tree.materialize(node)
        if not tree.assemble(plugin) and node.master:
            tree.dispose_all()
            raise SlotTreeError(f"启动失败：{node.path}")
    tree.assert_no_pending()
    app = runtime.app
    if app is None:
        tree.dispose_all()
        raise SlotTreeError("装配未产出 App")
    app._slot_tree = tree
    app._boot_runtime = runtime
    app._kernel_group = runtime.resources.get("kernel_group")
    if app._kernel_group is None:
        tree.dispose_all()
        raise SlotTreeError("内核模块容器未装配")
    return app


__all__ = ["boot_app"]
