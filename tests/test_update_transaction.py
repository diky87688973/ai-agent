"""更新事务：新增配置节、执行器归属及失败恢复。"""
from __future__ import annotations

import configparser
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.update import apply, install, recover
from agent.update.config_merge import merge_ini
from agent.update.logs import tail
from agent.update.state import read_state, write_state


class UpdateTransactionTest(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, Path]:
        (root / "VERSION").write_text("0.2.0\n", encoding="utf-8")
        (root / "agent").mkdir()
        (root / "agent" / "old.py").write_text("original", encoding="utf-8")
        (root / "plugins.ini").write_text(
            "[plugin:web_ui]\nenabled=0\ncustom=user\n", encoding="utf-8")
        staging = root / "updates" / "staging" / "0.2.1"
        payload = staging / "payload"
        (payload / "agent").mkdir(parents=True)
        (payload / "agent" / "new.py").write_text("new", encoding="utf-8")
        (payload / "plugins.ini").write_text(
            "[plugin:web_ui]\nenabled=1\n[plugin:ai_cosplay]\nenabled=1\n",
            encoding="utf-8")
        (staging / ".ready").touch()
        request = root / "updates" / "apply.json"
        request.write_text(json.dumps({"version": "0.2.1", "staging": str(staging)}),
                           encoding="utf-8")
        return staging, request

    def test_new_sections_and_bom_keep_user_values(self) -> None:
        for preserve in (False, True):
            with self.subTest(preserve=preserve), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                existing, template = root / "user.ini", root / "template.ini"
                existing.write_text("[old]\nkeep=user\ncustom=user\n", encoding="utf-8-sig")
                template.write_text("[old]\nkeep=default\n[new]\nenabled=1\n",
                                    encoding="utf-8-sig")
                merge_ini(existing, template, preserve_user_keys=preserve)
                parsed = configparser.ConfigParser()
                parsed.read(existing, encoding="utf-8")
                self.assertEqual(parsed.get("new", "enabled"), "1")
                self.assertEqual(parsed.get("old", "keep"), "user")
                self.assertEqual(parsed.has_option("old", "custom"), preserve)

    def test_upgrade_adds_plugin_section_and_cleans_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging, request = self._fixture(root)
            with patch.object(apply.sys, "argv", ["updater"]), \
                    patch.object(apply, "install_root", return_value=root), \
                    patch.object(apply, "health_check", return_value=True), \
                    patch.object(apply, "stop_old_launcher", return_value=[]), \
                    patch.object(apply, "cleanup_after_success",
                                 wraps=install.cleanup_after_success) as cleanup:
                self.assertEqual(apply.main(), 0)
            parsed = configparser.ConfigParser()
            parsed.read(root / "plugins.ini", encoding="utf-8")
            self.assertEqual(parsed.get("plugin:ai_cosplay", "enabled"), "1")
            self.assertEqual(parsed.get("plugin:web_ui", "enabled"), "0")
            self.assertEqual(parsed.get("plugin:web_ui", "custom"), "user")
            self.assertEqual(read_state(root)["phase"], "healthy")
            self.assertEqual((root / "VERSION").read_text().strip(), "0.2.1")
            cleanup.assert_called_once_with(root, "0.2.1")
            self.assertFalse(request.exists())
            self.assertFalse(staging.exists())
            self.assertNotIn("apply_state_cleanup_failed", [row["event"] for row in tail(root)])

    def test_copy_failure_restores_old_files_and_records_terminal_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging, request = self._fixture(root)
            original = (root / "plugins.ini").read_bytes()
            copy_program = install._copy_program
            def fail_after_copy(source, target):
                copy_program(source, target)
                raise OSError("injected copy failure")
            with patch.object(apply.sys, "argv", ["updater"]), \
                    patch.object(apply, "install_root", return_value=root), \
                    patch.object(install, "_copy_program", side_effect=fail_after_copy):
                self.assertEqual(apply.main(), 1)
            self.assertEqual(read_state(root)["phase"], "rolled_back")
            self.assertEqual((root / "plugins.ini").read_bytes(), original)
            self.assertEqual((root / "VERSION").read_text().strip(), "0.2.0")
            self.assertFalse((root / "agent" / "new.py").exists())
            self.assertFalse(request.exists())
            self.assertFalse(staging.exists())

    def test_failed_rollback_keeps_request_and_staging(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging, request = self._fixture(root)
            with patch.object(apply.sys, "argv", ["updater"]), \
                    patch.object(apply, "install_root", return_value=root), \
                    patch.object(install, "_copy_program", side_effect=OSError("copy failure")), \
                    patch.object(apply, "restore_backup", return_value=False):
                self.assertEqual(apply.main(), 1)
            self.assertEqual(read_state(root)["phase"], "switching")
            self.assertTrue(request.exists())
            self.assertTrue(staging.exists())
            self.assertIn("apply_rollback_failed", [row["event"] for row in tail(root)])

    def test_bootstrap_does_not_finalize_delegated_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging, request = self._fixture(root)
            with patch.object(apply.sys, "argv", ["updater"]), \
                    patch.object(apply, "install_root", return_value=root), \
                    patch.object(apply, "_run_new_updater", return_value=1), \
                    patch.object(apply, "cleanup_after_success") as cleanup, \
                    patch.object(apply, "restore_backup") as restore:
                self.assertEqual(apply.main(), 1)
            cleanup.assert_not_called()
            restore.assert_not_called()
            self.assertTrue(request.exists())
            self.assertTrue(staging.exists())

    def test_recovery_does_not_accept_healthy_old_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            install._backup_root(root, "0.2.0")
            write_state(root, "switching", "0.2.0", "0.2.1")
            with patch.object(recover, "install_root", return_value=root), \
                    patch.object(recover, "health_check", return_value=True) as health:
                self.assertEqual(recover.main(), 0)
            health.assert_not_called()
            self.assertEqual(read_state(root)["phase"], "rolled_back")

    def test_recovery_keeps_switching_when_backup_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            write_state(root, "switching", "0.2.0", "0.2.1")
            with patch.object(recover, "install_root", return_value=root):
                self.assertEqual(recover.main(), 1)
            self.assertEqual(read_state(root)["phase"], "switching")
