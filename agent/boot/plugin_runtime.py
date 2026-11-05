"""插件代切换：片段重装配、登记事务与轮次边界发布。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.app_model_policy import apply_model_policy
from agent.boot.plugin_assembly import discover
from agent.capabilities.plugins import plugin_module_transaction, resolve_plugin_root
from agent.common.status import PLUGIN_ERROR
from agent.config import DEFAULT_PLUGINS_PATH, get_plugins
from agent.core.slot_fragments import load_merged
from agent.core.slot_lifecycle import SlotLifecycle
from agent.core.slot_snapshot import SnapshotStore
from agent.core.slot_spec import SlotAssemblyError
from agent.shell.service_keys import SERVICE_CLASSIC_ADAPTER


class PluginRuntime:
    """装配根拥有切换过程；回合只通过通用生命周期租约读取。"""

    def __init__(self, app: Any, assembly: Any, boot: Any,
                 repo_root: Path, plugins_path: Any = None) -> None:
        self.app = app
        self.assembly = assembly
        self.boot = boot
        self.repo_root = repo_root
        app.plugin_host.manifest_path = Path(plugins_path or DEFAULT_PLUGINS_PATH)
        self.manifest = boot.plugin_manifest
        self.snapshots = SnapshotStore(assembly.config, assembly.values,
                                       rebuild=self._snapshot_input)
        self.lifecycle = SlotLifecycle(self.snapshots)
        app.plugin_host.request_unload = self.unload

    def _snapshot_input(self) -> Any:
        return self.assembly.config, self.assembly.values

    def reload(self, *, plugins_path: Any = None, plugins_dir: Any = None,
               reload_plugin: Any = None) -> bool:
        """取清单形成候选代；活跃回合结束后按请求顺序应用。"""
        root = Path(plugins_dir or self.boot.host_config.plugins_root)
        path = plugins_path or self.app.plugin_host.manifest_path
        manifest = discover(root, get_plugins(path), include_unlisted=(
            Path(path).resolve() == DEFAULT_PLUGINS_PATH.resolve())).manifest
        config = load_merged(self.repo_root, plugins_root=root, manifest=manifest,
                             plugin_roots={item["name"]: resolve_plugin_root(root, item["name"], item.get("path", ""))
                                           for item in manifest})
        origins = ({reload_plugin} if reload_plugin is not None else
                   set(config.origins.values()) - {"__host__"})
        return self.lifecycle.request(lambda: self._apply(config, manifest, origins))

    def unload(self, name: Any) -> None:
        """直接宿主卸载也通过同一片段、登记和资源事务。"""
        manifest = [dict(item) for item in self.manifest]
        for item in manifest:
            if name is None or item["name"] == name:
                item["enabled"] = "0"
        config = load_merged(self.repo_root, plugins_root=self.assembly.config.plugins_root,
                             manifest=manifest, plugin_roots=self.assembly.config.plugin_roots)
        origins = set(self.app.plugin_host.loaded_names()) if name is None else {name}
        self.lifecycle.request(lambda: self._apply(config, manifest, origins))

    def _apply(self, config: Any, manifest: Any, origins: Any) -> None:
        previous = self.app._slot_binder
        replacement = previous.fork()
        host = self.app.plugin_host
        candidate = None
        enabled = {item["name"] for item in manifest
                   if str(item.get("enabled", "1")) != "0"}
        names = origins | (set(host.loaded_names()) ^ enabled)
        try:
            with host.identity_transaction(), plugin_module_transaction(names):
                previous.dispose()
                host.detach_plugins(names)
                candidate = self.assembly.prepare_plugins(config, names)
                reports = host.load_manifest(manifest)
                if any(report.status == PLUGIN_ERROR for report in reports):
                    raise SlotAssemblyError("插件身份装载失败")
                replacement.ranks = host.ranks()
                replacement.bind(candidate)
                if replacement.failures:
                    raise SlotAssemblyError("插件绑定失败：" + "；".join(replacement.failures))
                apply_model_policy(self.app)
        except Exception:
            replacement.dispose()
            restored = previous.fork().bind(self.assembly)
            self.app._slot_binder = restored
            if candidate is not None:
                candidate.dispose()
            apply_model_policy(self.app)
            if restored.failures:
                raise SlotAssemblyError("恢复插件绑定失败：" + "；".join(restored.failures))
            raise
        self.app._slot_binder = replacement
        self.assembly.publish_plugins(candidate)
        self.manifest = manifest
        self.snapshots.stage("plugins")
        self.snapshots.begin_turn()
        if self.app.context.has(SERVICE_CLASSIC_ADAPTER):
            self.app.context.get(SERVICE_CLASSIC_ADAPTER).announce_plugins(host.loaded_names())

    def dispose(self) -> None:
        self.lifecycle.close()
        host = self.app.plugin_host
        if host is not None:
            host.request_unload = None
            host.detach_all()
