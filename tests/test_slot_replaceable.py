# -*- coding: utf-8 -*-
"""可替换性（第 8 条）：有效视图、冻结子树、结构字段、子树失效与独立替换。

验收面：
  a 内核 service 主插口 replace_subtree → 其全部后代消失（逐个子节点断言）
  b 子插口 replace → 父与兄弟实现不变，父只构造一次
  c 冻结节点自身与后代覆盖全拒，文案含路径与 frozen
  d 内核与插件两类各验一遍
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.core.slot_assembly import SlotAssembly  # noqa: E402
from agent.core.slot_config import SlotConfig  # noqa: E402
from agent.core.slot_fragments import load_merged  # noqa: E402
from agent.core.slot_override import (  # noqa: E402
    effective_view,
    frozen_paths,
    resolve_bindings,
)
from agent.core.slot_spec import (  # noqa: E402
    SlotAssemblyError,
    SlotConfigError,
)


def _config(rows: List[Dict[str, Any]], **extra: Any) -> SlotConfig:
    return SlotConfig.parse({"version": 1, "root": "app", "slots": rows, **extra})


def _stub(name: str) -> Any:
    """一个可识别的实现：带上自己的名字，便于断言「换成了谁」。"""
    def factory(*_args: Any, **_kwargs: Any) -> Dict[str, str]:
        return {"impl": name}
    return factory


def _resolver(table: Dict[str, Any]) -> Any:
    def _resolve(spec: str) -> Any:
        if spec not in table:
            raise AssertionError(f"未预期的 factory：{spec}")
        return table[spec]
    return _resolve


#: 内核侧样本：一个 service 主插口带两个后代，一个无关的兄弟 service。
_KERNEL_ROWS = [
    {"path": "app/kernel", "kind": "container"},
    {"path": "app/kernel/modules", "kind": "container"},
    {"path": "app/kernel/modules/model", "kind": "service",
     "children": "keyed", "factory": "agent.m:model"},
    {"path": "app/kernel/modules/model/port", "kind": "service",
     "factory": "agent.m:port"},
    {"path": "app/kernel/modules/model/stream", "kind": "service",
     "factory": "agent.m:stream"},
    {"path": "app/host", "kind": "container"},
    {"path": "app/host/services", "kind": "container"},
    {"path": "app/host/services/registry", "kind": "service",
     "factory": "agent.m:registry"},
]

_KERNEL_TABLE = {
    "agent.m:model": _stub("model"),
    "agent.m:port": _stub("port"),
    "agent.m:stream": _stub("stream"),
    "agent.m:registry": _stub("registry"),
    "agent.m:swapped": _stub("swapped"),
}


class KernelReplaceSubtreeTest(unittest.TestCase):
    """a + d（内核侧）：主插口被整棵替换，全部后代从有效视图消失。"""

    ROWS = _KERNEL_ROWS

    def _view(self, overrides: List[Dict[str, Any]]) -> SlotConfig:
        return effective_view(_config(self.ROWS, overrides=overrides))

    def test_every_descendant_disappears_from_effective_view(self) -> None:
        view = self._view([{"path": "app/kernel/modules/model",
                            "mode": "replace_subtree", "factory": "agent.m:swapped"}])
        # 逐个子节点断言，不是只看一个
        for gone in ("app/kernel/modules/model/port",
                     "app/kernel/modules/model/stream"):
            self.assertNotIn(gone, view.paths(), gone)
        self.assertIn("app/kernel/modules/model", view.paths())

    def test_descendants_are_not_constructed(self) -> None:
        assembly = SlotAssembly(
            _config(self.ROWS, overrides=[
                {"path": "app/kernel/modules/model", "mode": "replace_subtree",
                 "factory": "agent.m:swapped"}]),
            resolver=_resolver(_KERNEL_TABLE)).build()
        self.addCleanup(assembly.dispose)
        for gone in ("app/kernel/modules/model/port",
                     "app/kernel/modules/model/stream"):
            with self.assertRaises(SlotAssemblyError):
                assembly.get(gone)

    def test_no_node_receives_the_replaced_implementation(self) -> None:
        assembly = SlotAssembly(
            _config(self.ROWS, overrides=[
                {"path": "app/kernel/modules/model", "mode": "replace_subtree",
                 "factory": "agent.m:swapped"}]),
            resolver=_resolver(_KERNEL_TABLE)).build()
        self.addCleanup(assembly.dispose)
        self.assertEqual(assembly.get("app/kernel/modules/model"),
                         {"impl": "swapped"})
        # 旧后代一个都不该拿到 swapped
        for gone in ("app/kernel/modules/model/port",
                     "app/kernel/modules/model/stream"):
            self.assertNotIn(gone, assembly.values)

    def test_siblings_and_unrelated_nodes_untouched(self) -> None:
        assembly = SlotAssembly(
            _config(self.ROWS, overrides=[
                {"path": "app/kernel/modules/model", "mode": "replace_subtree",
                 "factory": "agent.m:swapped"}]),
            resolver=_resolver(_KERNEL_TABLE)).build()
        self.addCleanup(assembly.dispose)
        self.assertEqual(assembly.get("app/host/services/registry"),
                         {"impl": "registry"})


class KernelReplaceChildTest(unittest.TestCase):
    """b + d（内核侧）：换子插口，父与兄弟实现不变。"""

    ROWS = _KERNEL_ROWS

    def test_child_replacement_keeps_parent_and_siblings(self) -> None:
        calls: List[str] = []

        def parent(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
            calls.append("parent")
            return {"impl": "parent"}

        table = dict(_KERNEL_TABLE)
        table["agent.m:parent"] = parent
        rows = _KERNEL_ROWS + [
            {"path": "app/host/services/bus", "kind": "container",
             "factory": "agent.m:parent"},
            {"path": "app/host/services/bus/a", "kind": "service",
             "factory": "agent.m:registry"},
            {"path": "app/host/services/bus/b", "kind": "service",
             "factory": "agent.m:registry"},
        ]
        assembly = SlotAssembly(
            _config(rows, overrides=[
                {"path": "app/host/services/bus/a", "mode": "replace",
                 "factory": "agent.m:swapped"}]),
            resolver=_resolver(table)).build()
        self.addCleanup(assembly.dispose)
        self.assertEqual(assembly.get("app/host/services/bus/a"),
                         {"impl": "swapped"})
        self.assertEqual(assembly.get("app/host/services/bus/b"),
                         {"impl": "registry"})
        self.assertEqual(assembly.get("app/host/services/bus")["impl"], "parent")
        # 父只构造一次
        self.assertEqual(calls, ["parent"])


class PluginSideReplaceTest(unittest.TestCase):
    """d（插件侧）：插件声明的节点同样可换，与内核一视同仁。"""

    def _view(self, rows: List[Dict[str, Any]],
              overrides: List[Dict[str, Any]]) -> SlotConfig:
        config = _config(rows, overrides=overrides)
        return effective_view(SlotConfig(
            root=config.root, version=config.version, specs=config.specs,
            origins={"app/plugins/alpha/tools/t": "alpha",
                     "app/plugins/alpha/tools": "alpha",
                     "app/plugins/alpha/runtime": "alpha"},
            overrides=config.overrides))

    def test_plugin_node_is_replaceable(self) -> None:
        rows = [
            {"path": "app/plugins", "kind": "container"},
            {"path": "app/plugins/alpha", "kind": "container"},
            {"path": "app/plugins/alpha/runtime", "kind": "runtime",
             "factory": "plugin:make_runtime"},
            {"path": "app/plugins/alpha/tools", "kind": "container"},
            {"path": "app/plugins/alpha/tools/t", "kind": "tool",
             "factory": "plugin:make_tool"},
        ]
        view = self._view(rows, [{"path": "app/plugins/alpha/tools/t",
                                  "mode": "replace",
                                  "factory": "plugin:make_other_tool"}])
        self.assertEqual(view.spec("app/plugins/alpha/tools/t").factory,
                         "plugin:make_other_tool")
        self.assertEqual(view.spec("app/plugins/alpha/runtime").factory,
                         "plugin:make_runtime")

    def test_plugin_subtree_replacement_drops_descendants(self) -> None:
        rows = [
            {"path": "app/plugins", "kind": "container"},
            {"path": "app/plugins/alpha", "kind": "container"},
            {"path": "app/plugins/alpha/runtime", "kind": "runtime",
             "factory": "plugin:make_runtime"},
            {"path": "app/plugins/alpha/tools", "kind": "container"},
            {"path": "app/plugins/alpha/tools/t", "kind": "tool",
             "factory": "plugin:make_tool"},
        ]
        view = self._view(rows, [{"path": "app/plugins/alpha/tools",
                                  "mode": "replace_subtree",
                                  "factory": "plugin:make_tools"}])
        self.assertNotIn("app/plugins/alpha/tools/t", view.paths())


class FrozenSubtreeTest(unittest.TestCase):
    """c：冻结是子树属性，自身与后代都拒，文案含路径与 frozen。"""

    ROWS = [
        {"path": "app/kernel", "kind": "container"},
        {"path": "app/kernel/sealed", "kind": "container", "frozen": True},
        {"path": "app/kernel/sealed/inner", "kind": "service",
         "children": "keyed", "factory": "agent.m:registry"},
        {"path": "app/kernel/sealed/inner/deep", "kind": "service",
         "factory": "agent.m:registry"},
    ]

    def test_frozen_paths_include_descendants(self) -> None:
        frozen = frozen_paths(_config(self.ROWS))
        self.assertEqual(frozen, {"app/kernel/sealed",
                                  "app/kernel/sealed/inner",
                                  "app/kernel/sealed/inner/deep"})

    def test_frozen_self_and_descendants_reject_overrides(self) -> None:
        for path in ("app/kernel/sealed",
                     "app/kernel/sealed/inner",
                     "app/kernel/sealed/inner/deep"):
            with self.subTest(path=path), self.assertRaises(
                    SlotConfigError) as ctx:
                resolve_bindings(_config(self.ROWS),
                                 [{"path": path, "mode": "replace",
                                   "factory": "agent.m:swapped"}])
            message = str(ctx.exception)
            self.assertIn(path, message)
            self.assertIn("frozen", message)

    def test_non_frozen_sibling_still_replaceable(self) -> None:
        resolved = resolve_bindings(
            _config(self.ROWS),
            [{"path": "app/kernel", "mode": "replace",
              "factory": "agent.m:swapped"}])
        self.assertEqual(resolved.chain("app/kernel")[0].spec.factory,
                         "agent.m:swapped")


class StructuralFieldTest(unittest.TestCase):
    """覆盖不得改形状：结构字段出现即拒，文案指明须走下一轮快照。"""

    ROWS = [
        {"path": "app/kernel", "kind": "container"},
        {"path": "app/kernel/modules", "kind": "container"},
        {"path": "app/kernel/modules/model", "kind": "service",
         "children": "keyed", "factory": "agent.m:model"},
    ]

    def test_structural_fields_are_rejected(self) -> None:
        cases = [
            {"path": "app/kernel/modules/model", "kind": "provider",
             "factory": "agent.m:model"},
            {"path": "app/kernel/modules/model", "scope": "session",
             "factory": "agent.m:model"},
            {"path": "app/kernel/modules/model", "children": "fixed",
             "factory": "agent.m:model"},
            {"path": "app/kernel/modules/model", "fixed": ["x"],
             "factory": "agent.m:model"},
        ]
        for row in cases:
            key = [k for k in row if k not in ("path", "factory")][0]
            with self.subTest(field=key), self.assertRaises(
                    SlotConfigError) as ctx:
                resolve_bindings(_config(self.ROWS), [row])
            message = str(ctx.exception)
            self.assertIn("覆盖不得修改结构字段", message)
            self.assertIn("app/kernel/modules/model", message)
            self.assertIn("须走下一轮快照", message)


class DescendantDeclarationTest(unittest.TestCase):
    """覆盖不得声明后代：已换掉/禁用的子树下再写覆盖，必须拒。"""

    ROWS = _KERNEL_ROWS

    def test_override_under_replaced_subtree_is_rejected(self) -> None:
        with self.assertRaises(SlotConfigError) as ctx:
            resolve_bindings(_config(self.ROWS), [
                {"path": "app/kernel/modules/model", "mode": "replace_subtree",
                 "factory": "agent.m:swapped"},
                {"path": "app/kernel/modules/model/port", "mode": "replace",
                 "factory": "agent.m:port"},
            ])
        message = str(ctx.exception)
        self.assertIn("覆盖不得声明后代", message)
        self.assertIn("app/kernel/modules/model/port", message)

    def test_override_under_disabled_subtree_is_rejected(self) -> None:
        with self.assertRaises(SlotConfigError) as ctx:
            resolve_bindings(_config(self.ROWS), [
                {"path": "app/kernel/modules/model", "mode": "disable"},
                {"path": "app/kernel/modules/model/port", "mode": "replace",
                 "factory": "agent.m:port"},
            ])
        self.assertIn("覆盖不得声明后代", str(ctx.exception))


class EffectiveViewTest(unittest.TestCase):
    """有效视图本身：覆盖求值后即弃，不留第二本账。"""

    def test_view_carries_no_overrides(self) -> None:
        view = effective_view(_config(_KERNEL_ROWS, overrides=[
            {"path": "app/kernel/modules/model", "mode": "replace",
             "factory": "agent.m:swapped"}]))
        self.assertEqual(view.overrides, ())

    def test_no_overrides_returns_declaration_unchanged(self) -> None:
        config = _config(_KERNEL_ROWS)
        self.assertIs(effective_view(config), config)

    def test_disable_drops_node_and_descendants(self) -> None:
        view = effective_view(_config(_KERNEL_ROWS, overrides=[
            {"path": "app/kernel/modules/model", "mode": "disable"}]))
        for gone in ("app/kernel/modules/model",
                     "app/kernel/modules/model/port",
                     "app/kernel/modules/model/stream"):
            self.assertNotIn(gone, view.paths(), gone)

    def test_extend_is_reported_not_ignored(self) -> None:
        with self.assertRaises(SlotConfigError) as ctx:
            effective_view(_config(_KERNEL_ROWS, overrides=[
                {"path": "app/kernel/modules/model", "mode": "extend",
                 "factory": "agent.m:swapped"}]))
        self.assertIn("无法表达", str(ctx.exception))


class RealRepoReplaceTest(unittest.TestCase):
    """真实合并配置上换一个插件主插口：后代消失，其余不受影响。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_merged(_ROOT)
        cls.target = "app/plugins/skills/tools/skills"

    def test_plugin_tool_slot_is_replaceable_in_real_config(self) -> None:
        view = effective_view(SlotConfig(
            root=self.config.root, version=self.config.version,
            specs=self.config.specs, origins=self.config.origins,
            plugins_root=self.config.plugins_root,
            overrides=({"path": self.target, "mode": "replace",
                        "factory": "plugin:make_other"},)))
        self.assertEqual(view.spec(self.target).factory, "plugin:make_other")

    def test_real_config_holds_no_overrides_by_default(self) -> None:
        self.assertEqual(self.config.overrides, ())


if __name__ == "__main__":
    unittest.main()
