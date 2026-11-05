# -*- coding: utf-8 -*-
"""绑定器：只读派生、登记进既有注册表、失败留痕、dispose 逆序撤回。

三条验收在这里：
  登记与注册表实际内容对得上；
  dispose 后注册表回到「绑定器登记前」（宿主工具留着，其余清空）；
  单条登记失败不中断其余，且失败带节点路径与注册表名。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.app import build_app  # noqa: E402
from agent.capabilities.slot_binder import SlotBinder  # noqa: E402
from agent.core.slot_spec import (  # noqa: E402
    HOST_OWNER,
    SlotSpec,
)


class _Recorder:
    """最小注册表替身：记下成功的登记项，返回幂等 disposer。"""

    def __init__(self) -> None:
        self.live = []

    def _add(self, name, *_args, **_kwargs):
        self.live.append(name)

        def drop() -> None:
            if name in self.live:
                self.live.remove(name)

        return drop


class _FlakyRegistry(_Recorder):
    """遇到名为 boom 的工具就抛，用来验证「单条失败不中断」。"""

    def register(self, plugin, *, owner=""):
        if getattr(plugin, "name", "") == "boom":
            raise ValueError("故意失败")
        return self._add(getattr(plugin, "name", ""))


class _Plugin:
    def __init__(self, name):
        self.name = name


class _FakeConfig:
    def __init__(self, specs):
        self.specs = specs

    def paths(self):
        return tuple(self.specs)

    def spec(self, path):
        return self.specs[path]

    @staticmethod
    def origin_of(_path):
        return "alpha"


class _FakeAssembly:
    """只带 bind() 需要的那两样：声明表与已构造值。"""

    def __init__(self, specs, values):
        self.config = _FakeConfig(specs)
        self.values = values


class BinderFailureTest(unittest.TestCase):
    """单条失败留痕、其余继续。"""

    def test_one_failure_does_not_stop_the_rest(self) -> None:
        registry = _FlakyRegistry()
        binder = SlotBinder(
            plugin_host=None, registry=registry, event_bus=_Recorder(),
            contributions=_Recorder(), prompt_sections=_Recorder(),
            prompt_tail=_Recorder(), context_sources=_Recorder(),
            context_hooks=_Recorder(), model_catalog=_Recorder(),
            executors=_Recorder())
        boom = "app/plugins/alpha/tools/boom"
        ok = "app/plugins/alpha/tools/ok"
        specs = {
            boom: SlotSpec(path=boom, kind="tool", factory="plugin:x"),
            ok: SlotSpec(path=ok, kind="tool", factory="plugin:y"),
        }
        binder.bind(_FakeAssembly(specs, {boom: _Plugin("boom"), ok: _Plugin("ok")}))

        self.assertEqual(len(binder.failures), 1)
        self.assertIn(boom, binder.failures[0])
        self.assertIn("registry", binder.failures[0])
        self.assertIn("ValueError", binder.failures[0])
        self.assertEqual(registry.live, ["ok"])
        self.assertEqual(binder.bound_paths(), (ok,))

    def test_model_catalog_conflict_is_reported_and_rest_binds(self) -> None:
        """目录只认一个权威：第二个来源被拒是留痕不中断，其余节点照常绑定。"""
        class _ConflictCatalog(_Recorder):
            def set_source(self, owner, entries):
                self.live.append(owner)
                raise RuntimeError("模型目录已有来源 'first'")

        conflict = "app/plugins/alpha/providers/catalog-second"
        ok = "app/plugins/alpha/tools/ok"
        specs = {
            conflict: SlotSpec(path=conflict, kind="provider",
                               props={"target": "model-catalog"}),
            ok: SlotSpec(path=ok, kind="tool", factory="plugin:y"),
        }
        binder = SlotBinder(
            plugin_host=None, registry=_FlakyRegistry(), event_bus=_Recorder(),
            contributions=_Recorder(), prompt_sections=_Recorder(),
            prompt_tail=_Recorder(), context_sources=_Recorder(),
            context_hooks=_Recorder(), model_catalog=_ConflictCatalog(),
            executors=_Recorder())
        with mock.patch("agent.capabilities.slot_binder.report_error") as report:
            binder.bind(_FakeAssembly(
                specs, {conflict: lambda: [], ok: _Plugin("ok")}))

        self.assertEqual(report.call_count, 1)
        args, kwargs = report.call_args
        self.assertEqual(args[0], "slot_binder.model_catalog")
        self.assertEqual(kwargs.get("path"), conflict)
        self.assertEqual(kwargs.get("plugin"), "alpha")
        self.assertEqual(len(binder.failures), 1)
        self.assertIn(conflict, binder.failures[0])
        self.assertEqual(binder.bound_paths(), (ok,))


class RealAssemblyBindingTest(unittest.TestCase):
    """真实启动：登记内容与注册表一致，dispose 回到登记前。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(prefix="binder-")
        cls.app = build_app(data_root=Path(cls._tmp.name))
        cls.host = cls.app.plugin_host
        cls.registry = cls.app.registry
        cls.sources = cls.app.context.get("context_sources")
        cls.sections = cls.app.context.get("prompt_sections")
        cls.tails = cls.app.context.get("prompt_tail")
        cls.hooks = cls.app.context.get("context_hooks")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.dispose()
        cls._tmp.cleanup()

    def test_no_binding_failures(self) -> None:
        self.assertEqual(self.app._slot_binder.failures, [])

    def test_plugin_tool_count_matches_declared_nodes(self) -> None:
        """插件工具数 == 插件声明的 tool 节点数（宿主工具由工具容器登记，不归绑定器）。"""
        config = self.app._slot_assembly.config
        declared = [path for path, spec in config.specs.items()
                    if spec.kind == "tool" and config.origin_of(path) != HOST_OWNER]
        owned = [owner for owner in self.registry._owners.values() if owner]
        self.assertEqual(len(owned), len(declared))

    def test_every_bound_route_exists_in_contributions(self) -> None:
        config = self.app._slot_assembly.config
        routes = [path for path in self.app._slot_binder.bound_paths()
                  if config.specs[path].kind == "route"]
        self.assertTrue(routes)
        for path in routes:
            spec = config.specs[path]
            key = f"{spec.method} {config.origin_of(path)}/{spec.props['path']}"
            self.assertIn(key, self.host.contributions.routes, path)

    def test_every_bound_setting_exists_in_settings_registry(self) -> None:
        config = self.app._slot_assembly.config
        item_ids = {item.item_id for item in self.host.settings.items.values()}
        paths = [path for path in self.app._slot_binder.bound_paths()
                 if config.specs[path].kind == "setting"]
        self.assertTrue(paths)
        for path in paths:
            self.assertTrue(path in self.host.settings.panels or path in item_ids, path)

    def test_dispose_returns_registries_to_pre_bind_state(self) -> None:
        """逐项点名比：宿主工具留着（装配期容器登记），绑定器登记的各类全清空。

        本用例自带一个进程：它会 dispose，不能与只读用例共用。
        """
        with tempfile.TemporaryDirectory(prefix="binder-dispose-") as tmp:
            app = build_app(data_root=Path(tmp))
            host = app.plugin_host
            registry = app.registry
            sources = app.context.get("context_sources")
            sections = app.context.get("prompt_sections")
            tails = app.context.get("prompt_tail")
            hooks = app.context.get("context_hooks")

            # 登记前状态：工具容器在装配期就登记了宿主工具（owner 为空），
            # 绑定器只负责插件资产（owner 为插件名），所以两者要分开看。
            host_tools = sorted(name for name, owner in registry._owners.items()
                                if not owner)
            self.assertTrue(host_tools)
            self.assertTrue(host.ui.catalog()["entries"])
            self.assertTrue(sources._sources)
            self.assertTrue(sections._sources)
            self.assertTrue(tails._sources)
            self.assertTrue(hooks._hooks)
            self.assertTrue(host.settings.panels)
            self.assertTrue(host.settings.items)
            self.assertTrue(host.contributions.routes)
            self.assertTrue(host._runtimes)

            app.dispose()

            self.assertEqual(sorted(registry.names()), host_tools)
            self.assertEqual(host.ui.catalog()["entries"], [])
            self.assertEqual(host.settings.panels, {})
            self.assertEqual(host.settings.items, {})
            self.assertEqual(host.contributions.routes, {})
            self.assertEqual(host._runtimes, {})
            self.assertEqual(sources._sources, [])
            self.assertEqual(sections._sources, [])
            self.assertEqual(sections._after_sources, [])
            self.assertEqual(tails._sources, [])
            self.assertEqual(hooks._hooks, [])


if __name__ == "__main__":
    unittest.main()
