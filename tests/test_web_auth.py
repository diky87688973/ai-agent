# -*- coding: utf-8 -*-
"""HTTP 鉴权：密码、会话、Token、策略与来源判定。"""
from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from unittest import mock

from agent.config_schema import AUTH_DEFAULTS, SCHEMA
from agent.shell.web import server as web_server
from agent.shell.web.auth import AuthRuntime, password, policy
from agent.shell.web.auth import request as auth_request
from agent.shell.web.auth.config import load_config
from agent.shell.web.auth.credentials import CredentialStore
from agent.shell.web.auth.models import ALL_SCOPES
from agent.shell.web.auth.security import verify_path
from agent.shell.web.auth.sessions import LoginSessionStore
from agent.shell.web.auth.startup import can_start_public
from agent.shell.web.auth.tokens import TokenStore
from agent.shell.web.web_routes import Handler


class PasswordTest(unittest.TestCase):
    def test_hash_roundtrip_and_wrong_password(self) -> None:
        record = password.hash_password("correct horse battery")
        self.assertTrue(password.verify_password("correct horse battery", record))
        self.assertFalse(password.verify_password("wrong", record))


class CredentialTest(unittest.TestCase):
    def test_store_and_verify(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CredentialStore(Path(tmp) / "auth" / "credentials.json")
            store.set_password("abcdefghijkl")
            self.assertTrue(store.exists())
            record = store.password_record()
            self.assertTrue(password.verify_password("abcdefghijkl", record))
            self.assertFalse(password.verify_password("bad", record))


class SessionTest(unittest.TestCase):
    def test_create_validate_and_revoke(self) -> None:
        store = LoginSessionStore(ttl_seconds=2)
        token, session = store.create()
        self.assertIsNotNone(store.get(token))
        self.assertEqual(store.get(token).csrf, session.csrf)
        store.revoke(token)
        self.assertIsNone(store.get(token))

    def test_expiry(self) -> None:
        store = LoginSessionStore(ttl_seconds=1)
        token, _ = store.create()
        time.sleep(1.1)
        self.assertIsNone(store.get(token))


class TokenTest(unittest.TestCase):
    def test_duplicate_token_name_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = TokenStore(Path(tmp) / "auth" / "tokens.json")
            first = store.issue("same", ["read"])
            with self.assertRaises(ValueError):
                store.issue("same", ["read"])
            self.assertIsNotNone(store.verify(first))

    def test_cross_process_issue_keeps_all_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "auth" / "tokens.json"
            code = (
                "import sys; from pathlib import Path; "
                "from agent.shell.web.auth.tokens import TokenStore; "
                "TokenStore(Path(sys.argv[1])).issue(sys.argv[2], ['read'])"
            )
            processes = [
                subprocess.Popen(
                    [sys.executable, "-c", code, str(path), f"p{index}"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                for index in range(2)
            ]
            for process in processes:
                _, stderr = process.communicate(timeout=30)
                self.assertEqual(process.returncode, 0, stderr.decode("utf-8", "replace"))
            store = TokenStore(path)
            self.assertEqual(len(store._read()), 2)

    def test_threaded_issue_keeps_all_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = TokenStore(Path(tmp) / "auth" / "tokens.json")
            barrier = threading.Barrier(12)

            def issue(index: int) -> str:
                barrier.wait()
                return store.issue(f"t{index}", ["read"])

            with ThreadPoolExecutor(max_workers=12) as pool:
                tokens = list(pool.map(issue, range(12)))
            self.assertEqual(len(store._read()), 12)
            for token in tokens:
                self.assertIsNotNone(store.verify(token))

    def test_issue_does_not_resurrect_revoked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = TokenStore(Path(tmp) / "auth" / "tokens.json")
            old = store.issue("old", ["read"])
            barrier = threading.Barrier(2)

            def issue() -> None:
                barrier.wait()
                store.issue("new", ["read"])

            def revoke() -> None:
                barrier.wait()
                store.revoke("old")

            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(lambda fn: fn(), [issue, revoke]))
            self.assertIsNone(store.verify(old))
            self.assertIsNotNone(store.verify(store.issue("probe", ["read"])))

    def test_issue_verify_and_revoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = TokenStore(Path(tmp) / "auth" / "tokens.json")
            token = store.issue("ci", ["read", "chat"])
            self.assertIn("ai_", token)
            principal = store.verify(token)
            self.assertIsNotNone(principal)
            self.assertEqual(principal.scopes, {"read", "chat"})
            verify_path(store.path.with_suffix(store.path.suffix + ".lock"))
            self.assertTrue(store.revoke("ci"))
            self.assertIsNone(store.verify(token))


class TokenCliTest(unittest.TestCase):
    def test_lock_failure_is_reported_without_traceback(self) -> None:
        from contextlib import redirect_stdout
        from io import StringIO
        from types import SimpleNamespace

        from agent.entry.web import _auth_cli

        auth = SimpleNamespace(
            auth_dir=Path("data") / "auth",
            issue_token=mock.Mock(side_effect=RuntimeError("跨进程锁不可用")),
            revoke_token=mock.Mock(side_effect=RuntimeError("跨进程锁不可用")),
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = StringIO()
            with mock.patch("agent.entry.web._load_auth", return_value=auth), redirect_stdout(output):
                issue_code = _auth_cli(
                    Path(tmp), SimpleNamespace(
                        set_password=False, issue_token="x", scope="read",
                        revoke_token=None))
                revoke_code = _auth_cli(
                    Path(tmp), SimpleNamespace(
                        set_password=False, issue_token=None, scope="",
                        revoke_token="x"))
        self.assertEqual(issue_code, 2)
        self.assertEqual(revoke_code, 2)
        self.assertIn("跨进程锁不可用", output.getvalue())


class PolicyTest(unittest.TestCase):
    def test_public_and_scope(self) -> None:
        self.assertTrue(policy.is_public("GET", "/login"))
        self.assertTrue(policy.is_public("GET", "/healthz"))
        self.assertTrue(policy.is_public("POST", "/auth/login"))
        self.assertFalse(policy.is_public("GET", "/health"))
        self.assertEqual(policy.required_scope("GET", "/api/chat/history"), "read")
        self.assertEqual(policy.required_scope("POST", "/api/chat/send"), "chat")
        self.assertEqual(policy.required_scope("GET", "/api/settings"), "admin")
        self.assertEqual(
            policy.required_scope("GET", "/api/plugin/knowledge/_asset/theme.css"),
            "read",
        )
        self.assertEqual(
            policy.required_scope("POST", "/api/plugin/knowledge/_asset/theme.css"),
            "admin",
        )
        self.assertTrue(policy.allows(ALL_SCOPES, "admin"))
        self.assertFalse(policy.allows(frozenset({"read"}), "admin"))


class RuntimeTest(unittest.TestCase):
    def test_public_without_password_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config.ini"
            config.write_text("[auth]\nmode = auto\n", encoding="utf-8")
            runtime = AuthRuntime.load(root, config_path=config, host="0.0.0.0")
            self.assertFalse(can_start_public(runtime))
            runtime.set_password("abcdefghijkl")
            self.assertTrue(can_start_public(runtime))

    def test_config_reads_auth_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.ini"
            config.write_text(
                "[auth]\nmode = required\nsession_hours = 2\nmax_failures = 3\n",
                encoding="utf-8",
            )
            cfg = load_config(config)
            self.assertEqual(cfg.mode, "required")
            self.assertEqual(cfg.session_hours, 2)
            self.assertEqual(cfg.max_failures, 3)

    @unittest.skipUnless(os.name == "nt", "Windows ACL fallback")
    def test_unusable_auth_dir_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            auth = root / "auth"
            auth.mkdir()
            subprocess.run(
                ["icacls", str(auth), "/deny", "*S-1-1-0:(R)"],
                capture_output=True, check=False,
            )
            config = root / "config.ini"
            config.write_text("[auth]\nmode = required\n", encoding="utf-8")
            try:
                runtime = AuthRuntime.load(root, config_path=config, host="0.0.0.0")
                self.assertEqual(runtime.auth_dir, (root / "auth2").resolve())
                runtime.set_password("abcdefghijkl")
                self.assertTrue((root / "auth2" / "credentials.json").is_file())
            finally:
                subprocess.run(
                    ["takeown", "/f", str(auth), "/r", "/d", "Y"],
                    capture_output=True, check=False,
                )
                subprocess.run(
                    ["icacls", str(auth), "/reset", "/T", "/C"],
                    capture_output=True, check=False,
                )

    def test_login_issues_session_and_csrf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config.ini"
            config.write_text("[auth]\nmode = required\n", encoding="utf-8")
            runtime = AuthRuntime.load(root, config_path=config, host="0.0.0.0")
            runtime.set_password("abcdefghijkl")
            status, payload, headers = runtime.routes.login("wrong", "127.0.0.1")
            self.assertEqual(status, 401)
            with mock.patch.object(
                    runtime.credentials, "read",
                    side_effect=__import__(
                        "agent.shell.web.auth.security", fromlist=["AuthSecurityError"]).AuthSecurityError("bad acl")):
                status, payload, headers = runtime.routes.login(
                    "abcdefghijkl", "127.0.0.1")
            self.assertEqual(status, 503)
            self.assertEqual(payload["error"], "auth_unavailable")
            status, payload, headers = runtime.routes.login("abcdefghijkl", "127.0.0.1")
            self.assertEqual(status, 200)
            self.assertIn("Set-Cookie", headers)
            self.assertTrue(payload["csrf"])
            cookie = headers["Set-Cookie"].split(";", 1)[0]
            identity = runtime.authenticator.authenticate(
                {"Cookie": cookie}, "127.0.0.1")
            self.assertIsNotNone(identity)
            self.assertEqual(identity.principal.scopes, ALL_SCOPES)
            self.assertEqual(runtime.routes.csrf(identity)[0], 200)
            audit = root / "auth" / "auth.log"
            self.assertTrue(audit.is_file())
            self.assertNotIn("abcdefghijkl", audit.read_text(encoding="utf-8"))


class DesktopBootstrapTest(unittest.TestCase):
    def test_one_time_loopback_bootstrap_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config.ini"
            config.write_text(
                "[auth]\nmode = required\ndesktop_auto_login = 1\n",
                encoding="utf-8",
            )
            import os
            old_gui = os.environ.get("AI_AGENT_GUI")
            old_token = os.environ.get("AI_AGENT_GUI_BOOTSTRAP")
            os.environ["AI_AGENT_GUI"] = "1"
            os.environ["AI_AGENT_GUI_BOOTSTRAP"] = "bootstrap-secret"
            try:
                runtime = AuthRuntime.load(root, config_path=config, host="127.0.0.1")
                runtime.set_password("abcdefghijkl")
                self.assertEqual(runtime.routes.desktop_login(
                    "bootstrap-secret", "203.0.113.9")[0], 403)
                self.assertEqual(runtime.routes.desktop_login(
                    "wrong", "127.0.0.1")[0], 403)
                status, _, headers = runtime.routes.desktop_login(
                    "bootstrap-secret", "127.0.0.1")
                self.assertEqual(status, 200)
                cookie = headers["Set-Cookie"].split(";", 1)[0]
                identity = runtime.authenticator.authenticate(
                    {"Cookie": cookie}, "127.0.0.1")
                self.assertIsNotNone(identity)
                self.assertEqual(identity.principal.kind, "session")
                self.assertEqual(runtime.routes.desktop_login(
                    "bootstrap-secret", "127.0.0.1")[0], 403)
            finally:
                if old_gui is None:
                    os.environ.pop("AI_AGENT_GUI", None)
                else:
                    os.environ["AI_AGENT_GUI"] = old_gui
                if old_token is None:
                    os.environ.pop("AI_AGENT_GUI_BOOTSTRAP", None)
                else:
                    os.environ["AI_AGENT_GUI_BOOTSTRAP"] = old_token


class GuiAutoProvisionTest(unittest.TestCase):
    def test_gui_startup_creates_initial_password(self) -> None:

        from agent.shell.web import server
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.dict("os.environ", {
                    "AI_AGENT_GUI": "1",
                    "AI_AGENT_GUI_BOOTSTRAP": "bootstrap-secret",
            }, clear=False):
                runtime = server._startup_auth(
                    root, "127.0.0.1", None, None, False)
            self.assertIsNotNone(runtime)
            self.assertTrue((root / "auth" / "credentials.json").is_file())
            self.assertTrue((root / "auth" / "initial-password.txt").is_file())


class SchemaDefaultTest(unittest.TestCase):
    def test_schema_uses_copy_not_alias(self) -> None:
        self.assertIsNot(SCHEMA["auth"], AUTH_DEFAULTS)
        self.assertEqual(SCHEMA["auth"], AUTH_DEFAULTS)


class ProviderExtensionTest(unittest.TestCase):
    def test_provider_module_can_supply_principal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module = root / "auth_probe.py"
            module.write_text(
                "from agent.shell.web.auth.models import Principal, ALL_SCOPES\n"
                "class P:\n"
                "    def authenticate(self, headers, remote_ip):\n"
                "        if headers.get('X-Probe-Auth') == 'yes':\n"
                "            return Principal('probe', 'provider', ALL_SCOPES)\n"
                "        return None\n"
                "def build_provider(data_root, config):\n"
                "    return P()\n",
                encoding="utf-8",
            )
            config = root / "config.ini"
            config.write_text(
                "[auth]\nmode = required\nprovider_module = auth_probe\n",
                encoding="utf-8",
            )
            import sys
            sys.path.insert(0, str(root))
            try:
                runtime = AuthRuntime.load(root, config_path=config, host="0.0.0.0")
                self.assertTrue(can_start_public(runtime))
                identity = runtime.authenticator.authenticate(
                    {"X-Probe-Auth": "yes"}, "203.0.113.5")
                self.assertIsNotNone(identity)
                self.assertEqual(identity.principal.subject, "probe")
            finally:
                sys.path.remove(str(root))


class WebAuthHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        config = root / "config.ini"
        config.write_text("[auth]\nmode = required\n", encoding="utf-8")
        self.auth = AuthRuntime.load(root, config_path=config, host="0.0.0.0")
        self.auth.set_password("abcdefghijkl")
        class Bound(Handler):
            shell = object()
            assets_dir = root
            auth_runtime = self.auth
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Bound)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)

    def request(self, method: str, path: str, body: str = "",
                headers: Optional[dict] = None) -> tuple:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request(method, path, body=body or None, headers=headers or {})
        response = conn.getresponse()
        raw = response.read()
        result = (response.status, dict(response.getheaders()), raw)
        conn.close()
        return result

    def test_healthz_reports_fallback_target(self) -> None:
        root = Path(self.tmp.name)
        self.auth.auth_fallback_from = str(root / "auth")
        self.auth.auth_dir = root / "auth2"
        status, _, raw = self.request("GET", "/healthz")
        self.assertEqual(status, 200)
        payload = json.loads(raw.decode("utf-8"))
        self.assertTrue(payload["auth_fallback"])
        self.assertEqual(payload["auth_fallback_to"], "auth2")

    def test_login_page_has_window_close(self) -> None:
        status, _, raw = self.request("GET", "/login")
        self.assertEqual(status, 200)
        body = raw.decode("utf-8")
        self.assertIn('id="win-close"', body)
        self.assertIn("pywebview.api.close", body)

    def test_guard_login_csrf_and_logout(self) -> None:
        status, headers, _ = self.request("GET", "/")
        self.assertEqual(status, 302)
        self.assertTrue(headers["Location"].startswith("/login"))
        status, _, _ = self.request("GET", "/api/chat/sessions")
        self.assertEqual(status, 401)
        status, _, _ = self.request("GET", "/healthz")
        self.assertEqual(status, 200)
        status, _, _ = self.request("GET", "/login")
        self.assertEqual(status, 200)
        status, _, _ = self.request(
            "GET", "/healthz", headers={"Host": "evil.example"})
        self.assertEqual(status, 400)

        status, _, _ = self.request(
            "POST", "/auth/login",
            json.dumps({"password": "wrong"}),
            {"Content-Type": "application/json"},
        )
        self.assertEqual(status, 401)
        status, headers, raw = self.request(
            "POST", "/auth/login",
            json.dumps({"password": "abcdefghijkl"}),
            {"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        body = json.loads(raw.decode("utf-8"))
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.assertTrue(cookie)
        status, _, _ = self.request(
            "GET", "/auth/csrf", headers={"Cookie": cookie})
        self.assertEqual(status, 200)
        status, _, _ = self.request(
            "POST", "/auth/logout", "", {"Cookie": cookie})
        self.assertEqual(status, 403)
        status, _, _ = self.request(
            "POST", "/auth/logout", "",
            {"Cookie": cookie, "X-CSRF-Token": body["csrf"]},
        )
        self.assertEqual(status, 200)


class RequestBoundaryTest(unittest.TestCase):
    def test_trusted_proxy_and_host(self) -> None:
        trusted = ("10.0.0.0/8",)
        self.assertEqual(
            auth_request.client_ip(
                {"X-Forwarded-For": "203.0.113.9, 10.1.2.3"},
                "10.1.2.3", trusted),
            "203.0.113.9",
        )
        self.assertEqual(
            auth_request.client_ip(
                {"X-Forwarded-For": "203.0.113.9"}, "198.51.100.2", trusted),
            "198.51.100.2",
        )
        self.assertTrue(auth_request.secure_request(
            {"X-Forwarded-Proto": "https"}, "10.1.2.3", trusted, False))
        self.assertFalse(auth_request.secure_request(
            {"X-Forwarded-Proto": "https"}, "198.51.100.2", trusted, False))
        self.assertTrue(auth_request.host_allowed(
            "example.com:443", ("example.com",)))
        self.assertFalse(auth_request.host_allowed(
            "evil.example", ("example.com",)))


class TlsGuardTest(unittest.TestCase):
    def test_tls_wraps_socket_and_reports_failure(self) -> None:
        server = SimpleNamespace(socket=object(), server_close=mock.Mock())
        with mock.patch.object(web_server.ssl, "SSLContext") as context:
            self.assertTrue(web_server._apply_tls(server, "cert.pem", "key.pem"))
            context.return_value.load_cert_chain.assert_called_once_with(
                "cert.pem", "key.pem")
        with mock.patch.object(web_server.ssl, "SSLContext") as context:
            context.return_value.load_cert_chain.side_effect = OSError("bad cert")
            self.assertFalse(web_server._apply_tls(server, "cert.pem", "key.pem"))


class CreateServerAuthTest(unittest.TestCase):
    def test_required_mode_has_no_embedded_bypass(self) -> None:
        from agent.app import build_app
        from agent.shell.web.server import create_server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "plugins.ini"
            manifest.write_text("", encoding="utf-8")
            app = build_app(data_root=root, plugins_path=manifest)
            server = None
            try:
                with self.assertRaises(TypeError):
                    create_server(app, host="127.0.0.1", port=0)
                auth = AuthRuntime.load(root, config_path=Path("config.ini"),
                                        host="127.0.0.1")
                server, _ = create_server(
                    app, host="127.0.0.1", port=0, auth=auth)
                auth = server.RequestHandlerClass.auth_runtime
                self.assertFalse(auth.local_bypass)
            finally:
                if server is not None:
                    server.server_close()
                app.dispose()


class StreamSessionTest(unittest.TestCase):
    def test_stream_drops_revoked_session(self) -> None:
        from agent.shell.web.web_routes import Handler
        authenticator = mock.Mock()
        runtime = SimpleNamespace(
            authenticator=authenticator,
            config=SimpleNamespace(trusted_proxies=()),
        )
        handler = object.__new__(Handler)
        handler.auth_runtime = runtime
        handler.headers = {}
        handler.client_address = ("127.0.0.1", 0)
        identity = SimpleNamespace(session=object())
        authenticator.authenticate.return_value = None
        self.assertFalse(handler._stream_session_valid(identity))
        authenticator.authenticate.return_value = identity
        self.assertTrue(handler._stream_session_valid(identity))
        token_identity = SimpleNamespace(
            session=None, api_token=True, principal=object())
        authenticator.authenticate.return_value = token_identity
        self.assertTrue(handler._stream_session_valid(token_identity))
        authenticator.authenticate.return_value = None
        self.assertFalse(handler._stream_session_valid(token_identity))
