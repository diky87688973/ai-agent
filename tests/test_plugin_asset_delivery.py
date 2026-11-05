# -*- coding: utf-8 -*-
"""插件资产只有一条交付路径：片段声明 → 绑定器登记。

旧 `register(ctx)` 路径已经删除，因此对账基线改为装配产物本身：
  每一类插口节点数，必须与绑定器登记出来的该类资产数逐类相等
  （少 = 绑定器漏登，多 = 双份注册）；
  同一个 plugin.py 在 `sys.modules` 里只有一份；
  任何插件模块都不得再定义 `register`；
  `plugins.ini` 的 `enabled = 0` 仍然生效（无节点、无资产、无装载报告）。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.app import build_app  # noqa: E402
from agent.capabilities.plugins import plugin_module_name  # noqa: E402

DISABLED_PLUGIN = "visual_operator"

#: 绑定器按 kind 分派的 UI 条目类（`ui-slot` 走 add_slot，不在此列）。
_UI_ITEM_KINDS = ("ui-action", "ui-control", "ui-tool-shell")


def _of_kind(config, kinds) -> int:
    return sum(1 for spec in config.specs.values() if spec.kind in kinds)


def _plugin_tools(app) -> int:
    """只数带 owner 的工具：无 owner 的是内核内置工具，不经绑定器登记。"""
    return len([owner for owner in app.registry._owners.values() if owner])


class SingleDeliveryPathTest(unittest.TestCase):
    """片段节点数与绑定器登记的资产数逐类相等。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(prefix="delivery-")
        cls.app = build_app(data_root=Path(cls._tmp.name))
        cls.host = cls.app.plugin_host
        cls.config = cls.app._slot_assembly.config

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.dispose()
        cls._tmp.cleanup()

    def test_tools_match_tool_nodes(self) -> None:
        nodes = [spec for path, spec in self.config.specs.items()
                 if spec.kind == "tool" and path.startswith("app/plugins/")]
        self.assertEqual(_plugin_tools(self.app), len(nodes))

    def test_routes_match_route_nodes(self) -> None:
        self.assertEqual(len(self.host.contributions.routes),
                         _of_kind(self.config, ("route",)))

    def test_ui_items_match_ui_item_nodes(self) -> None:
        self.assertEqual(len(self.host.ui.catalog()["entries"]),
                         _of_kind(self.config, _UI_ITEM_KINDS))

    def test_settings_match_setting_nodes(self) -> None:
        self.assertEqual(len(self.host.settings.panels) + len(self.host.settings.items),
                         _of_kind(self.config, ("setting",)))

    def test_prompt_assets_match_provider_nodes(self) -> None:
        """provider 节点里带 `prompt/` 的：注入源 / 提示词段 / 模式尾部。"""
        nodes = [spec for path, spec in self.config.specs.items()
                 if spec.kind == "provider" and "/prompt/" in path]
        sources = len(self.app.context.get("context_sources")._sources)
        sections = len(self.app.context.get("prompt_sections")._sources)
        sections += len(self.app.context.get("prompt_sections")._after_sources)
        tails = len(self.app.context.get("prompt_tail")._sources)
        hooks = len(self.app.context.get("context_hooks")._hooks)
        self.assertEqual(sources + sections + tails + hooks, len(nodes))

    def test_events_match_event_nodes(self) -> None:
        subs = self.app.context.get("event_bus")._subs
        self.assertEqual(sum(len(items) for items in subs.values()),
                         _of_kind(self.config, ("event",)))

    def test_hooks_match_provider_user_message_nodes(self) -> None:
        """装配钩子在片段里是 `provider` 且路径带 `prompt/user-messages/`。"""
        nodes = [spec for path, spec in self.config.specs.items()
                 if spec.kind == "provider" and "/prompt/user-messages/" in path]
        self.assertEqual(len(self.app.context.get("context_hooks")._hooks),
                         len(nodes))

    def test_no_plugin_module_defines_register(self) -> None:
        """旧注册面已清：插件入口只剩片段，模块里不得再有 `register`。

        纯声明插件（无 `plugin.py`）本来就不应有模块，一并核。
        """
        checked = 0
        for name in self.host.ranks():
            module = sys.modules.get(plugin_module_name(name))
            if module is None:
                self.assertFalse(
                    (Path(_ROOT) / "plugins" / name / "plugin.py").exists(), name)
                continue
            self.assertFalse(hasattr(module, "register"), name)
            checked += 1
        self.assertGreater(checked, 0)

    def test_single_module_per_plugin(self) -> None:
        """同一 plugin.py 只有一份模块对象：不存在 `...plugin` 这种第二份。"""
        loaded = [key for key in sys.modules if key.startswith("fan_agent_plugins.")]
        self.assertTrue(loaded)
        duplicates = [key for key in loaded if key.endswith(".plugin")]
        self.assertEqual(duplicates, [])

    def test_runtime_is_reachable_by_plugin_name(self) -> None:
        """壳层按插件名取到的是装配结果里那个 runtime 节点值（同一对象）。"""
        checked = 0
        for name in self.host.ranks():
            node = f"app/plugins/{name}/runtime"
            if node not in self.config.specs:
                continue
            expected = self.app._slot_assembly.values[node]
            self.assertIs(self.host.runtime(name), expected, name)
            checked += 1
        self.assertGreater(checked, 0)


class DisabledPluginTest(unittest.TestCase):
    """`enabled = 0` 的插件：无节点、无资产、不出现在装载报告里。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(prefix="disabled-")
        cls.app = build_app(data_root=Path(cls._tmp.name))
        cls.host = cls.app.plugin_host

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.dispose()
        cls._tmp.cleanup()

    def test_no_nodes_declared(self) -> None:
        config = self.app._slot_assembly.config
        prefix = f"app/plugins/{DISABLED_PLUGIN}/"
        self.assertEqual([path for path in config.specs if path.startswith(prefix)], [])

    def test_no_assets_registered(self) -> None:
        self.assertNotIn(DISABLED_PLUGIN, {owner for owner in self.app.registry._owners.values()})
        self.assertNotIn(DISABLED_PLUGIN,
                         {route.plugin for route in self.host.contributions.routes.values()})
        self.assertNotIn(DISABLED_PLUGIN,
                         {entry["owner"] for entry in self.host.ui.catalog()["entries"]})
        self.assertIsNone(self.host.runtime(DISABLED_PLUGIN))

    def test_not_reported_as_loaded(self) -> None:
        self.assertNotIn(DISABLED_PLUGIN, [report.name for report in self.host.reports()])
        self.assertNotIn(DISABLED_PLUGIN, self.host.ranks())


if __name__ == "__main__":
    unittest.main()
