# -*- coding: utf-8 -*-
"""视觉操作 2.0 的宿主装配面。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.app import build_app
from agent.mechanisms.session_store import SessionStore


class VisualAppAssemblyTest(unittest.TestCase):
    def test_visual_plugin_is_loaded_with_kernel_hooks(self) -> None:
        with tempfile.TemporaryDirectory(prefix="visual-app-") as tmp:
            root = Path(tmp)
            app = build_app(
                store=SessionStore(root / "sessions"),
                data_root=root,
                config_ready=True,
            )
            try:
                self.assertIsNotNone(app.context_hooks)
                self.assertIsNotNone(app.context_sources)
                self.assertIn("vision_request_open", app.registry.names())
                actions = [
                    a.as_dict() for a in app.plugin_host.contributions.all_actions()
                    if a.plugin == "visual_operator_2"
                ]
                self.assertEqual(actions[0]["placement"], "after:knowledge:kb")
                self.assertEqual(
                    actions[0]["click_url"],
                    "/api/plugin/visual_operator_2/eye-consent/revoke",
                )
                self.assertTrue(app.context.has("context_hooks"))
            finally:
                app.dispose()


if __name__ == "__main__":
    unittest.main()
