# -*- coding: utf-8 -*-
"""鉴权文件安全：目录、原子写入与平台权限校验。"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent.shell.web.auth import security
from agent.shell.web.auth.audit import AuthAudit
from agent.shell.web.auth.security import (
    AuthSecurityError,
    atomic_write_text,
    ensure_auth_dir,
    read_text,
    verify_path,
)


class AuthSecurityTest(unittest.TestCase):
    def test_directory_and_atomic_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "auth"
            ensure_auth_dir(root)
            verify_path(root, directory=True)
            target = root / "credentials.json"
            atomic_write_text(target, "secret")
            self.assertEqual(read_text(target), "secret")
            verify_path(target)
            if os.name != "nt":
                self.assertEqual(root.stat().st_mode & 0o077, 0)
                self.assertEqual(target.stat().st_mode & 0o077, 0)

    def test_missing_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(AuthSecurityError):
                verify_path(Path(tmp) / "missing", directory=False)

    def test_atomic_failure_leaves_no_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "auth"
            ensure_auth_dir(root)
            target = root / "credentials.json"
            with mock.patch.object(security, "verify_path",
                                   side_effect=AuthSecurityError("acl fail")):
                with self.assertRaises(AuthSecurityError):
                    atomic_write_text(target, "secret")
            self.assertFalse(target.exists())
            self.assertEqual(list(root.glob(".auth-*")), [])

    def test_audit_hot_path_does_not_spawn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            audit = AuthAudit(Path(tmp) / "auth" / "auth.log")
            audit.write("first", remote_ip="127.0.0.1")
            with mock.patch.object(security.subprocess, "run",
                                   side_effect=AssertionError("spawned")):
                audit.write("second", remote_ip="127.0.0.1")

    @unittest.skipUnless(os.name == "nt", "Windows ACL only")
    def test_widened_acl_is_rejected_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "auth"
            ensure_auth_dir(root)
            target = root / "credentials.json"
            atomic_write_text(target, "secret")
            subprocess.run(
                ["icacls", str(target), "/grant", "*S-1-1-0:R"],
                capture_output=True, check=False)
            with self.assertRaises(AuthSecurityError):
                read_text(target)

    @unittest.skipUnless(os.name == "nt", "Windows ACL only")
    def test_widened_directory_is_repaired(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "auth"
            ensure_auth_dir(root)
            subprocess.run(
                ["icacls", str(root), "/grant", "*S-1-1-0:R"],
                capture_output=True, check=False)
            ensure_auth_dir(root)
            verify_path(root, directory=True)

    @unittest.skipUnless(os.name == "nt", "Windows ACL only")
    def test_windows_timeout_is_security_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "auth"
            root.mkdir()
            security._WINDOWS_SID = ""
            with mock.patch.object(
                    security.subprocess, "run",
                    side_effect=subprocess.TimeoutExpired("icacls", 30)):
                with self.assertRaises(AuthSecurityError):
                    security.secure_path(root, directory=True)
