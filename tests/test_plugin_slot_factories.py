# -*- coding: utf-8 -*-
"""插件插口 factory 的可构造性：只看 BuildContext + requires 注入能不能建起来。

这是「app/plugins 不再跳过」的前置条件：任何一个 factory 依赖了 BuildContext
没有的东西（比如旧 PluginContext 才有的方法），这里就会红。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.capabilities.plugins import resolve_plugin_factory  # noqa: E402
from agent.core.slot_assembly import BuildContext  # noqa: E402
from agent.core.slot_config import topo_order  # noqa: E402
from agent.core.slot_fragments import load_merged  # noqa: E402

PLUGINS_ROOT = _ROOT / "plugins"
PLUGIN_PREFIX = "app/plugins/"


class _FakeApp:
    """App 替身：只提供 factory 在构造期会碰到的那几项。

    事件出口走 lazy lambda，构造期不触发；`context` 供步骤日志路径探测。
    """

    context = None
    live_state = None


class _FakeSources:
    """注入源注册表替身：只记 bump 调用。"""

    def __init__(self) -> None:
        self.bumps = 0

    def bump(self) -> None:
        self.bumps += 1


def _fake_service(target: str) -> Any:
    """非插件节点（宿主服务）的替身。"""
    if target == "app/boot/facade":
        return _FakeApp()
    if target == "app/host/services/context_sources":
        return _FakeSources()
    if target == "app/host/services/live_state":
        return object()
    return object()


def _build_plugin_nodes(config: Any) -> Any:
    """按拓扑序构造全部插件节点，依赖值取已构造的真对象。

    与装配器的差别只有两处：不登记到注册表（binder 的事），
    宿主服务用替身（不启动整个 App）。
    """
    built: Dict[str, Any] = {}
    failures = []
    for path in topo_order(config):
        if not path.startswith(PLUGIN_PREFIX):
            continue
        spec = config.specs[path]
        if not spec.factory:
            built[path] = spec
            continue
        args: Dict[str, Any] = {}
        for key, target in spec.requires.items():
            args[key] = built[target] if target in built else _fake_service(target)
        try:
            factory = resolve_plugin_factory(
                PLUGINS_ROOT, config.origin_of(path), spec.factory, path, _ROOT)
            ctx = BuildContext(spec=spec, config=config, built=built)
            built[path] = factory(ctx, **args)
        except (TypeError, AttributeError, KeyError, IndexError,
                ValueError, RuntimeError, ImportError, OSError) as exc:
            failures.append(f"{path}（{type(exc).__name__}: {exc}）")
    return built, failures


class PluginFactoryConstructTest(unittest.TestCase):
    """合并结果里每个插件 factory 节点都能用最小 BuildContext 构造。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_merged(_ROOT)
        cls.paths = [p for p in cls.config.specs
                     if p.startswith(PLUGIN_PREFIX) and cls.config.specs[p].factory]
        cls.built, cls.failures = _build_plugin_nodes(cls.config)

    def test_every_plugin_factory_constructs(self) -> None:
        self.assertEqual(self.failures, [], "\n".join(self.failures))
        self.assertTrue(all(path in self.built for path in self.paths))

    def test_plugin_node_count_by_kind(self) -> None:
        """按 kind 分组报数：装配不再跳过后，这些节点必须全都有值。"""
        total: Dict[str, int] = {}
        factory: Dict[str, int] = {}
        for path in self.paths:
            kind = self.config.specs[path].kind
            total[kind] = total.get(kind, 0) + 1
            factory[kind] = factory.get(kind, 0) + 1
        plugin_nodes = [p for p in self.config.specs if p.startswith(PLUGIN_PREFIX)]
        all_kinds: Dict[str, int] = {}
        for path in plugin_nodes:
            kind = self.config.specs[path].kind
            all_kinds[kind] = all_kinds.get(kind, 0) + 1
        print(f"\n[插件节点全部] {sorted(all_kinds.items())} 合计 {len(plugin_nodes)}")
        print(f"[其中有 factory] {sorted(factory.items())} 合计 {len(self.paths)}")
        self.assertTrue(all(path in self.built for path in plugin_nodes))


class DependencyOrderTest(unittest.TestCase):
    """新增的依赖边必须成环可检，且方向正确。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_merged(_ROOT)
        cls.order = topo_order(cls.config)
        cls.index = {path: i for i, path in enumerate(cls.order)}

    def test_no_cycle(self) -> None:
        self.assertEqual(len(self.order), len(self.config.specs))

    def test_services_precede_their_consumers(self) -> None:
        services = ("app/boot/facade", "app/host/services/context_sources",
                    "app/host/services/live_state")
        problems = []
        for path, spec in self.config.specs.items():
            for key, target in spec.requires.items():
                if target not in self.index:
                    continue
                if self.index[target] > self.index[path]:
                    problems.append(f"{path}.{key} → {target}")
        self.assertEqual(problems, [], "依赖排在被依赖者之前：" + ", ".join(problems))

    def test_three_services_are_before_plugin_runtimes(self) -> None:
        runtimes = [p for p in self.config.specs
                    if p.startswith(PLUGIN_PREFIX) and p.endswith("/runtime")]
        self.assertTrue(runtimes)
        for service in ("app/boot/facade",
                        "app/host/services/context_sources",
                        "app/host/services/live_state"):
            for path in runtimes:
                consumers = [t for t in self.config.specs[path].requires.values()]
                if service not in consumers:
                    continue
                self.assertLess(self.index[service], self.index[path],
                                f"{service} 应排在 {path} 之前")


if __name__ == "__main__":
    unittest.main()
