# -*- coding: utf-8 -*-
"""更新核心：版本、manifest、安全解压。"""
from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from agent.update.assets import is_local_secret, is_sensitive_plugin_config
from agent.update.checker import check
from agent.update.config_merge import merge_ini, merge_plugin_configs
from agent.update.install import apply_staged, payload_root, read_pointer, rollback_pointer
from agent.update.manifest import manifest_digest, parse_manifest, sha256_file
from agent.update.stage import UpdateArchiveError, _safe_name, stage_package
from agent.update.state import read_state, write_state
from agent.update.version import Version, is_newer


class VersionTest(unittest.TestCase):
    def test_semver_compare(self) -> None:
        self.assertTrue(is_newer(Version.parse("0.2.0"), Version.parse("0.1.9")))
        self.assertFalse(is_newer(Version.parse("0.1.0"), Version.parse("0.1.0")))
        self.assertTrue(is_newer(Version.parse("0.1.1"), Version.parse("0.1.0-beta")))
        self.assertFalse(is_newer(Version.parse("0.1.0-beta"), Version.parse("0.1.0")))

    def test_invalid_version(self) -> None:
        with self.assertRaises(ValueError):
            Version.parse("v0.1")


class ManifestTest(unittest.TestCase):
    def _raw(self) -> bytes:
        return json.dumps({
            "schema": 1,
            "version": "0.2.0",
            "channel": "stable",
            "published_at": "2026-10-24T00:00:00Z",
            "asset": {"name": "app.zip", "size": 10, "sha256": "a" * 64},
            "notes": ["x"],
        }).encode()

    def test_parse_and_digest(self) -> None:
        raw = self._raw()
        item = parse_manifest(raw)
        self.assertEqual(str(item.version), "0.2.0")
        self.assertEqual(item.asset_name, "app.zip")
        self.assertEqual(len(manifest_digest(raw)), 64)

    def test_bad_schema(self) -> None:
        with self.assertRaises(ValueError):
            parse_manifest(b"{}")

    def test_check_disabled_without_url(self) -> None:
        status = check(url="")
        self.assertFalse(status.available)
        self.assertEqual(status.detail, "disabled")

    def test_stage_package_from_local_asset(self) -> None:
        from agent.update.manifest import parse_manifest, sha256_file

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset = root / "app.zip"
            with zipfile.ZipFile(asset, "w") as bundle:
                bundle.writestr("payload/agent/__init__.py", "")
            raw = json.dumps({
                "schema": 1, "version": "0.2.0", "channel": "stable",
                "asset": {"name": "app.zip", "size": asset.stat().st_size,
                          "sha256": sha256_file(asset)},
            }).encode()
            manifest = parse_manifest(raw)
            def fake_download(url: str, target: Path, expected: int) -> None:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(asset.read_bytes())
            with patch("agent.update.stage._download", side_effect=fake_download):
                staged = stage_package(manifest, manifest_url="https://example/x",
                                       updates_dir=root / "updates")
            self.assertTrue((staged / ".ready").is_file())
            self.assertTrue((staged / "payload" / "agent" / "__init__.py").is_file())

    def test_zip_paths(self) -> None:
        self.assertEqual(_safe_name("payload/agent/a.py"), "payload/agent/a.py")
        for bad in ("../x", "/x", "C:/x", "a/../x"):
            with self.assertRaises(UpdateArchiveError):
                _safe_name(bad)


class InstallLayoutTest(unittest.TestCase):
    def test_apply_staged_and_config_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config.ini").write_text("[agent]\nkeep = user\n", encoding="utf-8")
            staging = root / "updates" / "staging" / "0.2.0"
            payload = staging / "payload"
            (payload / "agent").mkdir(parents=True)
            (payload / "agent" / "__init__.py").write_text("", encoding="utf-8")
            templates = payload / "templates"
            templates.mkdir()
            (templates / "config.ini.example").write_text(
                "[agent]\nkeep = default\nnew_key = default\n", encoding="utf-8")
            (staging / ".ready").write_text("0.2.0", encoding="utf-8")
            target = apply_staged(root, staging, "0.2.0")
            self.assertTrue((target / "agent" / "__init__.py").is_file())
            self.assertEqual(read_pointer(root)["current"], "0.2.0")
            self.assertEqual(payload_root(root), target)
            text = (root / "config.ini").read_text(encoding="utf-8")
            self.assertIn("keep = user", text)
            self.assertIn("new_key = default", text)

    def test_merge_removes_deleted_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing = root / "config.ini"
            template = root / "template.ini"
            existing.write_text("[s]\nold = 1\nkeep = user\n", encoding="utf-8")
            template.write_text("[s]\nkeep = default\nnew = 2\n", encoding="utf-8")
            merge_ini(existing, template)
            text = existing.read_text(encoding="utf-8")
            self.assertNotIn("old", text)
            self.assertIn("keep = user", text)
            self.assertIn("new = 2", text)

    def test_rollback_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "versions" / "0.1.0").mkdir(parents=True)
            from agent.update.install import write_pointer
            write_pointer(root, "0.2.0", "0.1.0")
            rollback_pointer(root)
            self.assertEqual(read_pointer(root)["current"], "0.1.0")


class ControllerTest(unittest.TestCase):
    def test_controller_disabled_and_guards(self) -> None:
        from agent.update.controller import UpdateController
        with tempfile.TemporaryDirectory() as tmp, \
                patch("agent.update.controller.manifest_url", return_value=""):
            (Path(tmp) / "VERSION").write_text("0.1.0", encoding="utf-8")
            controller = UpdateController(Path(tmp))
            status = controller.check()
            self.assertFalse(status["available"])
            with self.assertRaises(ValueError):
                controller.download()
            with self.assertRaises(ValueError):
                controller.apply()

    def test_controller_uses_payload_version(self) -> None:
        from agent.update.controller import UpdateController
        from agent.update.install import write_pointer
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "VERSION").write_text("0.1.0", encoding="utf-8")
            target = root / "versions" / "0.2.0"
            (target / "agent").mkdir(parents=True)
            (target / "VERSION").write_text("0.2.0", encoding="utf-8")
            write_pointer(root, "0.2.0", "0.1.0")
            with patch("agent.update.controller.manifest_url", return_value=""):
                controller = UpdateController(root)
                self.assertEqual(controller.check()["current"], "0.2.0")

    def test_dev_checkout_disables_update(self) -> None:
        from agent.update.controller import UpdateController
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            (root / "VERSION").write_text("0.1.0", encoding="utf-8")
            controller = UpdateController(root)
            self.assertEqual(controller.check()["detail"], "dev_checkout")

    def test_apply_without_state(self) -> None:
        from agent.update.apply import main
        with tempfile.TemporaryDirectory() as tmp, \
                patch("agent.update.apply.install_root", return_value=Path(tmp)):
            self.assertEqual(main(), 0)


class PluginConfigTest(unittest.TestCase):
    def test_sensitive_config_is_not_default_distribution(self) -> None:
        self.assertTrue(is_sensitive_plugin_config(Path("plugins/multi_model/plugin-config.ini")))
        self.assertFalse(is_sensitive_plugin_config(Path("plugins/knowledge/plugin-config.ini")))

    def test_plugin_config_merge_and_sensitive_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "versions" / "0.2.0"
            (root / "plugins" / "knowledge").mkdir(parents=True)
            (target / "plugins" / "knowledge").mkdir(parents=True)
            (root / "plugins" / "knowledge" / "plugin-config.ini").write_text(
                "[config]\nkeep = user\nold = 1\n", encoding="utf-8")
            (target / "plugins" / "knowledge" / "plugin-config.ini").write_text(
                "[config]\nkeep = default\nnew = 2\n", encoding="utf-8")
            (root / "plugins" / "multi_model").mkdir(parents=True)
            (root / "plugins" / "multi_model" / "plugin-config.ini").write_text(
                "[secret]\nkey = local\n", encoding="utf-8")
            merge_plugin_configs(root, target)
            text = (target / "plugins" / "knowledge" / "plugin-config.ini").read_text(encoding="utf-8")
            self.assertIn("keep = user", text)
            self.assertIn("new = 2", text)
            self.assertNotIn("old", text)
            self.assertTrue((target / "plugins" / "multi_model" / "plugin-config.ini").is_file())

    def test_state_read_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_state(root, "switching", "0.1.0", "0.2.0")
            self.assertEqual(read_state(root)["phase"], "switching")

    def test_local_secret_filter(self) -> None:
        self.assertTrue(is_local_secret(Path("plugins/x/plugin-config.local.ini")))
        self.assertTrue(is_local_secret(Path("plugins/x/token.pem")))
        self.assertFalse(is_local_secret(Path("plugins/x/plugin-config.ini")))

    def test_recover_rolls_back_unhealthy_target(self) -> None:
        from agent.update import recover
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "versions" / "0.1.0").mkdir(parents=True)
            (root / "versions" / "0.2.0").mkdir(parents=True)
            from agent.update.install import write_pointer
            write_pointer(root, "0.2.0", "0.1.0")
            write_state(root, "switching", "0.1.0", "0.2.0")
            with patch("agent.update.recover.install_root", return_value=root), \
                    patch("agent.update.recover.health_check", return_value=False):
                recover.main()
            self.assertEqual(read_pointer(root)["current"], "0.1.0")


class FileHashTest(unittest.TestCase):
    def test_sha256_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.txt"
            path.write_text("hello", encoding="utf-8")
            self.assertEqual(len(sha256_file(path)), 64)
