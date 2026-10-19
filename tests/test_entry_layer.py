# -*- coding: utf-8 -*-
"""入口层（`agent/entry/`）：装配与参数解析的契约。

入口层存在的全部理由：壳层不许导入装配根（A2）。所以这里逐条钉住
"谁建 app、谁解析参数、谁把 app 交给壳"——任何一条退回去都会让环重新长出来。
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.config import default_data_root  # noqa: E402
from agent.core.events import Event  # noqa: E402
from agent.entry import cli as entry_cli  # noqa: E402
from agent.entry import headless as entry_headless  # noqa: E402
from agent.entry import web as entry_web  # noqa: E402
from agent.mechanisms.session_store import SessionStore  # noqa: E402
from tests.testkit import no_plugins  # noqa: E402


class _TempDataRoot(unittest.TestCase):
    """把 `AI_AGENT_DATA_ROOT` 指到临时目录：入口装配会真的落盘。

    同时不装任何插件：本文件断言的是入口装配，而插件会改变装配结果
    （多模型插件有有效条目时目录接管模型，`model_config_state` 就不再是 `none`）。
    """

    def setUp(self) -> None:
        no_plugins(self)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self._prev = os.environ.get("AI_AGENT_DATA_ROOT")
        os.environ["AI_AGENT_DATA_ROOT"] = str(self.root)
        self.addCleanup(self._restore_env)

    def _restore_env(self) -> None:
        if self._prev is None:
            os.environ.pop("AI_AGENT_DATA_ROOT", None)
        else:
            os.environ["AI_AGENT_DATA_ROOT"] = self._prev

    def _store(self) -> SessionStore:
        return SessionStore(self.root / "sessions")


class BuildShellAppTest(_TempDataRoot):
    """`build_shell_app`：默认按配置建 provider；给了就原样用。"""

    def test_given_provider_and_store_are_used(self) -> None:
        provider = object()
        app = entry_web.build_shell_app(
            provider=provider, store=self._store(), data_root=self.root
        )
        self.addCleanup(app.dispose)
        self.assertIs(app.provider.default_provider, provider)

    def test_missing_config_starts_in_setup_mode(self) -> None:
        with mock.patch.object(entry_web, "get_model_reasoning",
                               return_value={"api_key": "", "api_base_url": "", "model": ""}):
            app = entry_web.build_shell_app(data_root=self.root)
        self.addCleanup(app.dispose)
        self.assertEqual(app.model_config_state, "none")

    def test_placeholder_key_also_starts_in_setup_mode(self) -> None:
        with mock.patch.object(entry_web, "get_model_reasoning",
                               return_value={"api_key": "sk-请替换",
                                             "api_base_url": "https://api.deepseek.com",
                                             "model": "m"}):
            app = entry_web.build_shell_app(data_root=self.root)
        self.addCleanup(app.dispose)
        self.assertEqual(app.model_config_state, "none")

    def test_provider_is_built_from_config(self) -> None:
        cfg = {"api_key": "k", "api_base_url": "http://example.invalid", "model": "m"}
        built = []

        class _Provider:
            def __init__(self, **kwargs):
                built.append(kwargs)

        with mock.patch.object(entry_web, "get_model_reasoning", return_value=cfg), \
                mock.patch.object(entry_web, "OpenAICompatibleProvider", _Provider):
            app = entry_web.build_shell_app(store=self._store(), data_root=self.root)
        self.addCleanup(app.dispose)
        self.assertEqual(built[0]["model"], "m")
        self.assertEqual(built[0]["base_url"], "http://example.invalid")

    def test_default_data_root_is_used_when_omitted(self) -> None:
        self.assertEqual(Path(str(default_data_root())), self.root)


class WebMainTest(_TempDataRoot):
    """`agent.entry.web.main`：解析参数 → 装配 → 交给壳；真正的装配故障返回 2。"""

    def test_unexpected_build_error_returns_2(self) -> None:
        out = io.StringIO()
        with mock.patch.object(entry_web, "build_shell_app",
                               side_effect=RuntimeError("缺少配置")), \
                redirect_stdout(out):
            code = entry_web.main([])
        self.assertEqual(code, 2)
        self.assertIn("缺少配置", out.getvalue())

    def test_open_flag_uses_setup_url_without_model(self) -> None:
        app = mock.MagicMock()
        app.model_config_state = "none"
        captured = {}

        def _serve(_app, **kwargs):
            captured.update(kwargs)
            return 0

        with mock.patch.object(entry_web, "build_shell_app", return_value=app), \
                mock.patch.object(entry_web, "serve", _serve):
            code = entry_web.main(["--open", "--data-root", str(self.root)])
        self.assertEqual(code, 0)
        self.assertEqual(captured["open_url"], "http://127.0.0.1:8765/setup")

    def test_args_are_forwarded_to_shell_serve(self) -> None:
        app = mock.MagicMock()
        captured = {}

        def _serve(target, **kwargs):
            captured["app"] = target
            captured.update(kwargs)
            return 0

        with mock.patch.object(entry_web, "build_shell_app", return_value=app), \
                mock.patch.object(entry_web, "serve", _serve):
            code = entry_web.main(["--host", "0.0.0.0", "--port", "9999",
                                   "--data-root", str(self.root),
                                   "--fs-root", str(self.root),
                                   "--media-root", str(self.root / "media")])
        self.assertEqual(code, 0)
        self.assertIs(captured["app"], app)
        self.assertEqual((captured["host"], captured["port"]), ("0.0.0.0", 9999))
        self.assertEqual(captured["data_root"], self.root)
        self.assertEqual(captured["fs_root"], [self.root])
        self.assertEqual(captured["media_root"], self.root / "media")

    def test_empty_fs_root_passes_none(self) -> None:
        captured = {}

        def _serve(_app, **kwargs):
            captured.update(kwargs)
            return 0

        with mock.patch.object(entry_web, "build_shell_app", return_value=mock.MagicMock()), \
                mock.patch.object(entry_web, "serve", _serve):
            entry_web.main(["--data-root", str(self.root)])
        self.assertIsNone(captured["fs_root"])
        self.assertIsNone(captured["media_root"])


class CliEntryTest(_TempDataRoot):
    """`agent.entry.cli`：配置检查在入口做，`chat.main` 只拿到 app 工厂。"""

    def test_missing_config_returns_none(self) -> None:
        with mock.patch.object(entry_cli, "get_model_reasoning",
                               return_value={"api_key": "", "api_base_url": "", "model": ""}):
            self.assertIsNone(entry_cli.build_app_from_config())

    def test_builds_app_with_provider_from_config(self) -> None:
        cfg = {"api_key": "k", "api_base_url": "http://example.invalid", "model": "m"}

        class _Provider:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        with mock.patch.object(entry_cli, "get_model_reasoning", return_value=cfg), \
                mock.patch.object(entry_cli, "OpenAICompatibleProvider", _Provider):
            app = entry_cli.build_app_from_config()
        self.addCleanup(app.dispose)
        self.assertEqual(app.provider.default_provider.kwargs["model"], "m")

    def test_main_delegates_to_chat_main(self) -> None:
        seen = {}

        def _fake_main(argv, *, app_factory):
            seen["argv"] = argv
            seen["factory"] = app_factory
            return 7

        with mock.patch.object(entry_cli.chat, "main", _fake_main):
            code = entry_cli.main(["--session", "cid"])
        self.assertEqual(code, 7)
        self.assertEqual(seen["argv"], ["--session", "cid"])
        self.assertIs(seen["factory"], entry_cli.build_app_from_config)


class HeadlessEntryTest(unittest.TestCase):
    """`agent.entry.headless`：装配在入口，壳只负责跑一轮并打印。"""

    def test_run_prints_one_line_per_event(self) -> None:
        class _App:
            def run_turn(self, text):
                self.text = text
                yield Event("started", {"text": "hi"})
                yield Event("done", {"ok": True})

        out = io.StringIO()
        with redirect_stdout(out):
            code = entry_headless.headless.run(_App(), "问题")
        self.assertEqual(code, 0)
        lines = out.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("[started]", lines[0])
        self.assertIn("[done]", lines[1])

    def test_main_passes_first_argument_and_uses_factory(self) -> None:
        seen = {}

        class _App:
            def run_turn(self, text):
                seen["text"] = text
                return iter(())

        out = io.StringIO()
        with redirect_stdout(out):
            code = entry_headless.main(["只跑一轮"], app_factory=lambda: _App())
        self.assertEqual(code, 0)
        self.assertEqual(seen["text"], "只跑一轮")

    def test_main_defaults_to_smoke_text(self) -> None:
        seen = {}

        class _App:
            def run_turn(self, text):
                seen["text"] = text
                return iter(())

        with redirect_stdout(io.StringIO()):
            entry_headless.main([], app_factory=lambda: _App())
        self.assertTrue(seen["text"])


if __name__ == "__main__":
    unittest.main()
