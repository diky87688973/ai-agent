# -*- coding: utf-8 -*-
"""基础设置插件的面板与条目契约（片段侧）。

旧口径是「调 `register(ctx)` 后看 ctx 收到了什么」；`register` 已删，
口径改为装配产物：合并后的 `app/settings/**` 节点逐条核对。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.core.slot_fragments import load_merged  # noqa: E402
from agent.core.slot_spec import parent_path  # noqa: E402

OWNER = "base_settings"

#: 本插件声明的面板，一个不多一个不少。
PANELS = (
    "app/settings/agent",
    "app/settings/context",
    "app/settings/interface",
    "app/settings/plugin",
)

#: 本插件声明的条目，以及每条归属的面板。
ITEMS = {
    "app/settings/agent/reasoning_effort": "app/settings/agent",
    "app/settings/agent/max_passes": "app/settings/agent",
    "app/settings/agent/backup_retention_days": "app/settings/agent",
    "app/settings/context/full_user_rounds": "app/settings/context",
    "app/settings/context/summary_output_max_chars": "app/settings/context",
    "app/settings/context/reasoning_replay_tokens": "app/settings/context",
    "app/settings/context/image_turns": "app/settings/context",
    "app/settings/context/image_max": "app/settings/context",
    "app/settings/interface/display_tool_items": "app/settings/interface",
    "app/settings/interface/display_tool_steps": "app/settings/interface",
}


class BaseSettingsFragmentTest(unittest.TestCase):
    """面板恰 4 条、条目恰 10 条、每条归属正确。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_merged(ROOT)
        owned = {path: spec for path, spec in cls.config.specs.items()
                 if spec.kind == "setting" and cls.config.origin_of(path) == OWNER}
        cls.owned = owned
        #: 面板是 `props.kind` 为空的 setting 节点；条目带 kind。
        cls.panels = {path for path, spec in owned.items() if not spec.props.get("kind")}
        cls.items = {path for path, spec in owned.items() if spec.props.get("kind")}

    def test_panels_are_exactly_the_four(self) -> None:
        self.assertEqual(sorted(self.panels), sorted(PANELS))

    def test_items_are_exactly_the_ten(self) -> None:
        self.assertEqual(sorted(self.items), sorted(ITEMS))

    def test_each_item_belongs_to_its_panel(self) -> None:
        for item, panel in ITEMS.items():
            with self.subTest(item=item):
                self.assertIn(item, self.owned)
                self.assertEqual(parent_path(item, "app"), panel)
                self.assertIn(panel, self.panels)

    def test_items_use_field_factories(self) -> None:
        """条目由 `make_field_*` 造（带 save/load 闭包），面板由 `make_panel_*` 造。"""
        for item in ITEMS:
            with self.subTest(item=item):
                self.assertTrue(self.owned[item].factory.endswith(
                    tuple(f":make_field_{kind}" for kind in
                          ("agent_select", "agent_number", "context_number",
                           "web_ui_checkbox"))), self.owned[item].factory)
        for panel in PANELS:
            with self.subTest(panel=panel):
                self.assertIn(":make_panel_", self.owned[panel].factory)

    def test_retention_setting_has_a_one_round_floor(self) -> None:
        item = self.owned["app/settings/context/full_user_rounds"]
        self.assertEqual(item.props["min"], 1)

    def test_does_not_register_model_panel(self) -> None:
        """模型设置面板归 multi_model，不归本插件。"""
        self.assertNotIn("app/settings/model", self.panels)
        self.assertEqual(self.config.origin_of("app/settings/model"), "multi_model")


if __name__ == "__main__":
    unittest.main()
