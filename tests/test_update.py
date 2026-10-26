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
from agent.update.config_merge import merge_ini
from agent.update.install import apply_staged, restore_backup
from agent.update.manifest import manifest_digest, parse_manifest, sha256_file
from agent.update.stage import UpdateArchiveError, _safe_name, stage_package
from agent.update.state import read_state, write_state
from agent.update.version import Version, is_newer
from scripts.pack_common import project_files


class PackagingBlacklistTest(unittest.TestCase):
    def test_blacklist_keeps_nested_plugin_data_but_drops_root_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = {
                "agent/keep.py": "keep",
                "plugins/demo/data/asset.txt": "asset",
                "data/root.txt": "data",
                "Data/ROOT.txt": "data",
                "updates/state.json": "state",
                "tmp/probe.txt": "tmp",
                "artifacts/shot.png": "shot",
                "ai_agent.egg-info/PKG-INFO": "meta",
                "docs/readme.md": "doc",
                "tests/test_x.py": "test",
                "plugins/demo/__pycache__/x.pyc": "cache",
                "plugins/demo/plugin-config.ini": "[x]\na = b\n",
                "plugins/multi_model/plugin-config.ini": "[model:x]\napi_key = secret\n",
                ".env": "secret",
                "debug.log": "log",
            }
            for name, body in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body, encoding="utf-8")
            found = {path.relative_to(root).as_posix() for path in project_files(root)}
            self.assertIn("agent/keep.py", found)
            self.assertIn("plugins/demo/data/asset.txt", found)
            self.assertIn("plugins/demo/plugin-config.ini", found)
            for name in ("data/root.txt", "Data/ROOT.txt", "updates/state.json",
                         "tmp/probe.txt", "artifacts/shot.png",
                         "ai_agent.egg-info/PKG-INFO", "docs/readme.md",
                         "tests/test_x.py", "plugins/demo/__pycache__/x.pyc",
                         "plugins/multi_model/plugin-config.ini", ".env", "debug.log"):
                self.assertNotIn(name, found)

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
    def test_apply_staged_updates_root_and_keeps_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "VERSION").write_text("0.1.0", encoding="utf-8")
            (root / "config.ini").write_text("[agent]\nkeep = user\n", encoding="utf-8")
            (root / "agent").mkdir()
            (root / "agent" / "old.py").write_text("old", encoding="utf-8")
            (root / "rules").mkdir()
            (root / "rules" / "SYSTEM.md").write_text("old rule", encoding="utf-8")
            staging = root / "updates" / "staging" / "0.2.0"
            payload = staging / "payload"
            (payload / "agent").mkdir(parents=True)
            (payload / "agent" / "new.py").write_text("new", encoding="utf-8")
            (payload / "rules").mkdir()
            (payload / "rules" / "SYSTEM.md").write_text("new rule", encoding="utf-8")
            (payload / "scripts").mkdir()
            (payload / "scripts" / "tool.py").write_text("new tool", encoding="utf-8")
            (payload / "config.ini").write_text(
                "[agent]\nkeep = default\nnew = version\n", encoding="utf-8")
            (payload / "VERSION").write_text("0.2.0", encoding="utf-8")
            (staging / ".ready").write_text("0.2.0", encoding="utf-8")
            target = apply_staged(root, staging, "0.2.0")
            self.assertEqual(target, root)
            self.assertTrue((root / "agent" / "new.py").is_file())
            self.assertTrue((root / "rules" / "SYSTEM.md").is_file())
            self.assertEqual((root / "rules" / "SYSTEM.md").read_text(encoding="utf-8"), "new rule")
            self.assertEqual((root / "scripts" / "tool.py").read_text(encoding="utf-8"), "new tool")
            self.assertEqual((root / "config.ini").read_text(encoding="utf-8"),
                             "[agent]\nkeep = user\nnew = version\n\n")
            self.assertEqual((root / "VERSION").read_text(encoding="utf-8").strip(), "0.2.0")
            self.assertTrue((root / "updates" / "backup" / "0.1.0" / "agent" / "old.py").is_file())

    def test_nested_runtime_named_dir_is_backed_up(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "VERSION").write_text("0.1.0", encoding="utf-8")
            (root / "plugins" / "demo" / "data").mkdir(parents=True)
            (root / "plugins" / "demo" / "data" / "keep.txt").write_text(
                "old", encoding="utf-8")
            (root / "data").mkdir()
            (root / "data" / "user.txt").write_text("user", encoding="utf-8")
            staging = root / "updates" / "staging" / "0.2.0"
            payload = staging / "payload"
            (payload / "agent").mkdir(parents=True)
            (payload / "agent" / "__init__.py").write_text("", encoding="utf-8")
            (payload / "plugins" / "demo" / "data").mkdir(parents=True)
            (payload / "plugins" / "demo" / "data" / "keep.txt").write_text(
                "new", encoding="utf-8")
            (payload / "VERSION").write_text("0.2.0", encoding="utf-8")
            (staging / ".ready").write_text("0.2.0", encoding="utf-8")
            apply_staged(root, staging, "0.2.0")
            self.assertEqual(
                (root / "plugins" / "demo" / "data" / "keep.txt").read_text(
                    encoding="utf-8"), "new")
            self.assertTrue(restore_backup(root, "0.1.0"))
            self.assertEqual(
                (root / "plugins" / "demo" / "data" / "keep.txt").read_text(
                    encoding="utf-8"), "old")
            self.assertEqual(
                (root / "data" / "user.txt").read_text(encoding="utf-8"), "user")

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

    def test_restore_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backup = root / "updates" / "backup" / "0.1.0"
            (backup / "agent").mkdir(parents=True)
            (backup / "agent" / "old.py").write_text("old", encoding="utf-8")
            (backup / "VERSION").write_text("0.1.0", encoding="utf-8")
            (root / "agent").mkdir()
            (root / "agent" / "new.py").write_text("new", encoding="utf-8")
            self.assertTrue(restore_backup(root, "0.1.0"))
            self.assertTrue((root / "agent" / "old.py").is_file())
            self.assertFalse((root / "agent" / "new.py").exists())


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

    def test_controller_uses_root_version(self) -> None:
        from agent.update.controller import UpdateController
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "VERSION").write_text("0.2.0", encoding="utf-8")
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

    def test_update_log_tail(self) -> None:
        from agent.update.logs import log_event, tail
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_event(root, "check_result", available=True, version="0.1.2")
            rows = tail(root)
            self.assertEqual(rows[0]["event"], "check_result")
            self.assertTrue(rows[0]["available"])

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
            (root / "VERSION").write_text("0.2.0", encoding="utf-8")
            backup = root / "updates" / "backup" / "0.1.0"
            (backup / "agent").mkdir(parents=True)
            (backup / "agent" / "old.py").write_text("old", encoding="utf-8")
            (backup / "VERSION").write_text("0.1.0", encoding="utf-8")
            write_state(root, "switching", "0.1.0", "0.2.0")
            with patch("agent.update.recover.install_root", return_value=root), \
                    patch("agent.update.recover.health_check", return_value=False):
                recover.main()
            self.assertEqual((root / "VERSION").read_text(encoding="utf-8").strip(), "0.1.0")


class CoverageRootTest(unittest.TestCase):
    def test_install_helpers(self) -> None:
        from agent.update.install import cleanup_after_success, restore_backup
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "VERSION").write_text("0.1.0", encoding="utf-8")
            (root / "agent").mkdir()
            (root / "agent" / "x.py").write_text("x", encoding="utf-8")
            (root / "updates" / "staging" / "0.2.0").mkdir(parents=True)
            (root / "updates" / "download").mkdir(parents=True)
            cleanup_after_success(root, "0.2.0")
            self.assertFalse((root / "updates" / "staging" / "0.2.0").exists())
            self.assertFalse((root / "updates" / "download").exists())
            self.assertFalse(restore_backup(root, "missing"))

    def test_apply_success_and_failure(self) -> None:
        from agent.update.apply import main
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "VERSION").write_text("0.1.0", encoding="utf-8")
            (root / "updates").mkdir()
            staging = root / "updates" / "staging" / "0.2.0"
            staging.mkdir(parents=True)
            (staging / ".ready").write_text("x", encoding="utf-8")
            (root / "updates" / "apply.json").write_text(
                json.dumps({"version": "0.2.0", "staging": str(staging)}), encoding="utf-8")
            with patch("agent.update.apply.install_root", return_value=root), \
                    patch("agent.update.apply.apply_staged", return_value=root), \
                    patch("agent.update.apply.health_check", return_value=True), \
                    patch("agent.update.apply.cleanup_after_success"):
                self.assertEqual(main(), 0)
            self.assertEqual(read_state(root)["phase"], "healthy")
            (root / "updates" / "apply.json").write_text(
                json.dumps({"version": "0.3.0", "staging": str(staging)}), encoding="utf-8")
            with patch("agent.update.apply.install_root", return_value=root), \
                    patch("agent.update.apply.apply_staged", return_value=root), \
                    patch("agent.update.apply.health_check", return_value=False), \
                    patch("agent.update.apply.restore_backup", return_value=True), \
                    patch("agent.update.apply.cleanup_after_success"):
                self.assertEqual(main(), 2)
            self.assertEqual(read_state(root)["phase"], "rolled_back")


class FileHashTest(unittest.TestCase):
    def test_sha256_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.txt"
            path.write_text("hello", encoding="utf-8")
            self.assertEqual(len(sha256_file(path)), 64)
