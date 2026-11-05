# -*- coding: utf-8 -*-
"""插件 factory 的加载归属：包名与模块名只在 capabilities 一处，插件入口只装一份。

三条红线：
  同一 plugin.py 只能有一个模块对象（否则类、单例、注册表分裂）；
  core 不得自带插件包名（会与 capabilities 形成第二套规则）；
  未注入插件解析器时必须显式报错，不许静默回退。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.capabilities.plugins import (  # noqa: E402
    _MODULE_PREFIX,
    load_plugin_module,
    plugin_module_name,
    resolve_plugin_factory,
)
from agent.core.slot_assembly import SlotAssembly  # noqa: E402
from agent.core.slot_config import SlotConfig  # noqa: E402
from agent.core.slot_spec import (  # noqa: E402
    SlotConfigError,
    SlotSpec,
)

CORE_SLOT_MODULES = sorted((_ROOT / "agent" / "core").glob("slot_*.py"))


def _plugin_dir(parent: Path, name: str = "probe_plugin") -> Path:
    """造一个最小插件：入口 + 一个被相对导入的子模块。"""
    root = parent / name
    root.mkdir(parents=True)
    (root / "helper.py").write_text("VALUE = 'helper'\n", encoding="utf-8")
    (root / "plugin.py").write_text(
        "from .helper import VALUE\n\n"
        "def make_thing(ctx=None):\n"
        "    return ('thing', VALUE)\n",
        encoding="utf-8")
    return root


class ModuleIdentityTest(unittest.TestCase):
    """同一 plugin.py 无论从哪条路进入，都是同一个模块对象。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="plugident-")
        self.addCleanup(self._tmp.cleanup)
        self.plugins = Path(self._tmp.name) / "plugins"
        self.plugins.mkdir()
        self.name = "probe_plugin"
        self.root = _plugin_dir(self.plugins, self.name)
        self.addCleanup(self._forget, self.name)

    def _forget(self, name: str) -> None:
        prefix = plugin_module_name(name)
        for key in list(sys.modules):
            if key == prefix or key.startswith(prefix + "."):
                sys.modules.pop(key, None)

    def _entry_modules(self) -> list:
        target = plugin_module_name(self.name)
        return [mod for key, mod in sys.modules.items() if key == target]

    def test_loader_then_resolver_yields_one_object(self) -> None:
        """先走装载器、再走工厂解析：入口模块只有一个且 is 相同。"""
        loaded = load_plugin_module(self.plugins, self.name,
                                    root=self.root, entry=self.root / "plugin.py")
        factory = resolve_plugin_factory(
            self.plugins, self.name, "plugin:make_thing", "", _ROOT)
        self.assertEqual(factory.__module__, plugin_module_name(self.name))
        self.assertIs(sys.modules[plugin_module_name(self.name)], loaded)
        self.assertEqual(len(self._entry_modules()), 1)
        self.assertEqual(factory(), ("thing", "helper"))

    def test_resolver_then_loader_yields_one_object(self) -> None:
        """反过来也一样：解析先到，装载器复用同一对象。"""
        factory = resolve_plugin_factory(
            self.plugins, self.name, "plugin:make_thing", "", _ROOT)
        entry = sys.modules[plugin_module_name(self.name)]
        loaded = load_plugin_module(self.plugins, self.name)
        self.assertIs(loaded, entry)
        self.assertEqual(factory.__module__, plugin_module_name(self.name))
        self.assertEqual(len(self._entry_modules()), 1)

    def test_submodule_lives_under_the_same_package(self) -> None:
        """子模块是 <入口包>.<段>，不再套一层 .plugin。"""
        resolve_plugin_factory(self.plugins, self.name, "plugin:make_thing", "", _ROOT)
        helper = sys.modules.get(plugin_module_name(self.name) + ".helper")
        self.assertIsNotNone(helper)
        self.assertEqual(helper.VALUE, "helper")

    def test_repeated_resolution_does_not_reexec(self) -> None:
        """重复解析不会重新执行 plugin.py（重新执行就等于第二份模块）。"""
        first = resolve_plugin_factory(
            self.plugins, self.name, "plugin:make_thing", "", _ROOT)
        module = sys.modules[plugin_module_name(self.name)]
        second = resolve_plugin_factory(
            self.plugins, self.name, "plugin:make_thing", "", _ROOT)
        self.assertIs(first, second)
        self.assertIs(sys.modules[plugin_module_name(self.name)], module)


class PackageNameOwnershipTest(unittest.TestCase):
    """包名字面量只许出现在 capabilities，core 不得自带。"""

    def test_core_has_no_plugin_package_literal(self) -> None:
        for module in CORE_SLOT_MODULES:
            with self.subTest(module=module.name):
                text = module.read_text(encoding="utf-8")
                self.assertNotIn(_MODULE_PREFIX, text,
                                 msg="core 不得自带插件包名，包名归属 capabilities")

    def test_capabilities_owns_the_prefix(self) -> None:
        self.assertEqual(plugin_module_name("demo"), f"{_MODULE_PREFIX}.demo")


class InjectionRequiredTest(unittest.TestCase):
    """未注入插件解析器时必须报错且指明要注入，不许静默回退。"""

    def _config(self) -> SlotConfig:
        """声明方是插件的节点：origins 说实现在 alpha 那里，配置带插件根。

        插件节点要走到注入的解析器上，得先被认出来是插件节点 —— 判据是
        `origins` + 非空 `plugins_root`；两者缺一就无从来讲到注入点。
        """
        spec = SlotSpec(path="app/plugins/alpha/tool", kind="tool",
                        factory="plugin:make_thing")
        return SlotConfig(root="app", version=1,
                          specs={spec.path: spec},
                          origins={spec.path: "alpha"},
                          plugins_root=_ROOT / "plugins")

    def test_uninjected_raises_with_guidance(self) -> None:
        assembly = SlotAssembly(self._config())
        with self.assertRaises(SlotConfigError) as caught:
            assembly.build()
        message = str(caught.exception)
        self.assertIn("未注入插件 factory 解析器", message)
        self.assertIn("plugin_factories", message)

    def test_injected_is_not_the_stub(self) -> None:
        from agent.core.slot_factory import missing_plugin_factories

        def factories(origin, spec, path, plugins_root):
            raise SlotConfigError("真实解析器被调用")

        assembly = SlotAssembly(self._config(), plugin_factories=factories)
        self.assertIsNot(assembly.plugin_factories, missing_plugin_factories)


if __name__ == "__main__":
    unittest.main()
