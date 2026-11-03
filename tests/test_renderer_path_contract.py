# -*- coding: utf-8 -*-
"""工具 renderer 路径绑定契约。"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class RendererPathContractTest(unittest.TestCase):
    def test_diff_path_is_exposed(self) -> None:
        tree = (ROOT / "plugins" / "web_ui" / "plugin-ui.json").read_text(
            encoding="utf-8")
        self.assertIn('"app/shell/web-ui/chat/messages/tools/diff"', tree)

    def test_action_registry_is_exposed(self) -> None:
        tree = (ROOT / "plugins" / "web_ui" / "plugin-ui.json").read_text(
            encoding="utf-8")
        helper = (ROOT / "agent" / "capabilities" / "plugin_ui_tree.py").read_text(
            encoding="utf-8")
        self.assertIn('"app/shell/web-ui/actions"', tree)
        self.assertIn('action_id.replace(".", "_")', helper)
        self.assertIn(
            'app_path("shell", "web-ui", "actions", action_id.replace(".", "_"))',
            helper,
        )
        js = (ROOT / "plugins" / "web_ui" / "ui" / "classic" / "js" /
              "core" / "ui-catalog.js").read_text(encoding="utf-8")
        self.assertIn("window.aiAgentUiActions", js)
        self.assertIn("customActions[action]", js)

    def test_renderer_replacement_restores_previous(self) -> None:
        js = (ROOT / "plugins" / "web_ui" / "ui" / "classic" / "js" /
              "chat-tool-views.js").read_text(encoding="utf-8")
        self.assertIn("function replaceChatToolView(", js)
        self.assertIn("view._restore=restore", js)
        self.assertIn("replace:replaceChatToolView", js)

    def test_thinking_renderer_is_path_replaceable(self) -> None:
        js = (ROOT / "plugins" / "web_ui" / "ui" / "classic" / "js" /
              "chat-tool-views.js").read_text(encoding="utf-8")
        self.assertIn('uiRoot()+"/chat/messages/thinking"', js)
        self.assertIn("window.__webUi.ui_root", js)
        self.assertIn("window.aiAgentRenderers", js)
        self.assertIn("replace:replacePathRenderer", js)

    def test_ui_catalog_has_no_hardcoded_tree_paths(self) -> None:
        js = (ROOT / "plugins" / "web_ui" / "ui" / "classic" / "js" /
              "core" / "ui-catalog.js").read_text(encoding="utf-8")
        self.assertNotIn("app/shell/web-ui", js)

    def test_tool_view_prefers_path_override(self) -> None:
        js = (ROOT / "plugins" / "web_ui" / "ui" / "classic" / "js" /
              "chat-tool-views.js").read_text(encoding="utf-8")
        self.assertIn("function chatToolViewPath(", js)
        self.assertIn("chatToolViews[i].path===path", js)
        self.assertIn("unregister:unregisterChatToolView", js)


if __name__ == "__main__":
    unittest.main()
