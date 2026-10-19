# -*- coding: utf-8 -*-
"""首次启动向导：无模型启动、保存配置、热加载。"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.entry import web as entry_web  # noqa: E402
from agent.shell import onboarding  # noqa: E402
from agent.shell.web import create_server  # noqa: E402
from tests.testkit import no_plugins  # noqa: E402


class OnboardingTest(unittest.TestCase):
    def setUp(self) -> None:
        no_plugins(self)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self._prev = os.environ.get("AI_AGENT_DATA_ROOT")
        os.environ["AI_AGENT_DATA_ROOT"] = str(self.root)
        self.addCleanup(self._restore_env)
        with mock.patch.object(
            entry_web,
            "get_model_reasoning",
            return_value={"api_key": "", "api_base_url": "", "model": ""},
        ):
            self.app = entry_web.build_shell_app(data_root=self.root)
        self.addCleanup(self.app.dispose)
        self.config = self.root / "config.ini"

    def _restore_env(self) -> None:
        if self._prev is None:
            os.environ.pop("AI_AGENT_DATA_ROOT", None)
        else:
            os.environ["AI_AGENT_DATA_ROOT"] = self._prev

    def test_missing_model_can_start_and_save_without_restart(self) -> None:
        self.assertEqual(self.app.model_config_state, "none")
        code, payload = onboarding.save(
            self.app,
            {
                "api_base_url": "https://api.deepseek.com",
                "api_key": "sk-test",
                "model": "deepseek-flash",
                "context_window": "128000",
            },
            config_path=self.config,
        )
        self.assertEqual(code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(self.app.model_config_state, "config")
        text = self.config.read_text(encoding="utf-8")
        self.assertIn("[model_reasoning]", text)
        self.assertIn("api_key = sk-test", text)
        self.assertTrue(onboarding.status(self.app, config_path=self.config)["configured"])

    def test_placeholder_and_empty_key_are_rejected(self) -> None:
        code, payload = onboarding.save(
            self.app,
            {"api_base_url": "https://api.deepseek.com", "api_key": "sk-请替换"},
            config_path=self.config,
        )
        self.assertEqual(code, 400)
        self.assertIn("占位", payload["error"])
        code, payload = onboarding.save(
            self.app,
            {"api_base_url": "https://api.deepseek.com", "api_key": ""},
            config_path=self.config,
        )
        self.assertEqual(code, 400)
        self.assertIn("API Key", payload["error"])

    def test_root_redirects_to_setup_when_model_missing(self) -> None:
        server, _shell = create_server(self.app, host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        conn = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        self.addCleanup(conn.close)
        conn.request("GET", "/")
        response = conn.getresponse()
        response.read()
        self.assertEqual(response.status, 302)
        self.assertEqual(response.getheader("Location"), "/setup")
        conn.request("GET", "/setup")
        page = conn.getresponse()
        body = page.read()
        self.assertEqual(page.status, 200)
        self.assertIn(b"/api/setup", body)
        conn.request("GET", "/?setup=skip")
        classic = conn.getresponse()
        classic.read()
        self.assertEqual(classic.status, 200)

    def test_setup_page_is_shipped(self) -> None:
        page = _ROOT / "agent" / "shell" / "web_assets" / "setup.html"
        text = page.read_text(encoding="utf-8")
        self.assertIn("/api/setup", text)
        self.assertIn("保存并开始", text)


if __name__ == "__main__":
    unittest.main()
