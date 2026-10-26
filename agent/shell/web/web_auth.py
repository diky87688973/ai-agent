# -*- coding: utf-8 -*-
"""Web 鉴权中间层：Handler 与 auth 运行时之间的 HTTP 边界。"""
from __future__ import annotations

import ssl
from typing import Any
from urllib.parse import quote

from agent.core.error_report import report_error
from agent.shell.web.auth import csrf as auth_csrf
from agent.shell.web.auth.authenticator import cookie_token
from agent.shell.web.auth.request import client_ip, host_allowed, secure_request


class AuthMiddleware:
    # ── 鉴权边界 ──────────────────────────────────

    def _client_ip(self) -> str:
        remote = str(self.client_address[0] if self.client_address else "")
        runtime = getattr(self, "auth_runtime", None)
        if runtime is None:
            return remote
        return client_ip(self.headers, remote, runtime.config.trusted_proxies)

    def _secure_request(self) -> bool:
        runtime = getattr(self, "auth_runtime", None)
        if runtime is None:
            return False
        if runtime.secure_cookie:
            return True
        remote = str(self.client_address[0] if self.client_address else "")
        return secure_request(
            self.headers, remote, runtime.config.trusted_proxies,
            isinstance(self.connection, ssl.SSLSocket),
        )

    def _host_guard(self) -> bool:
        runtime = getattr(self, "auth_runtime", None)
        if runtime is None:
            return True
        if host_allowed(self.headers.get("Host", ""), runtime.config.allowed_hosts):
            return True
        try:
            runtime.audit.write("host_rejected", host=str(self.headers.get("Host") or ""))
        except Exception as exc:
            report_error("agent.shell.web.web_routes.host_audit", exc)
        self._json(400, {"ok": False, "error": "invalid_host"})
        return False

    def _identity(self) -> Any:
        runtime = getattr(self, "auth_runtime", None)
        if runtime is None:
            return None
        try:
            return runtime.authenticator.authenticate(self.headers, self._client_ip())
        except Exception as exc:
            report_error("agent.shell.web.web_routes.Handler.identity", exc)
            return None

    def _html(self, body: str) -> None:
        raw = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _redirect_login(self) -> None:
        target = "/login?next=" + quote(self.path, safe="")
        self.send_response(302)
        self.send_header("Location", target)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _auth_gate(self, method: str, path: str) -> bool:
        runtime = getattr(self, "auth_runtime", None)
        if runtime is None:
            return True
        identity = self._identity()
        decision = runtime.authorizer.decide(identity, method, path)
        if not decision.allowed:
            if decision.status == 401 and not (
                    path.startswith("/api/") or path.startswith("/auth/")
                    or path.startswith("/assets/")):
                self._redirect_login()
            else:
                self._json(decision.status, {"ok": False, "error": decision.error})
            return False
        if identity is not None and identity.session is not None:
            token = str(self.headers.get(auth_csrf.CSRF_HEADER) or "")
            if auth_csrf.required(method, identity.session) and not auth_csrf.verify(
                    identity.session, token):
                try:
                    runtime.audit.write("csrf_failed", path=path, method=method)
                except Exception as exc:
                    report_error("agent.shell.web.web_routes.csrf_audit", exc)
                self._json(403, {"ok": False, "error": "csrf_failed"})
                return False
        self._auth_identity = identity
        return True

    def _auth_public_get(self, path: str) -> bool:
        runtime = getattr(self, "auth_runtime", None)
        if runtime is None:
            return False
        if path == "/login":
            self._html(runtime.routes.page())
            return True
        if path == "/desktop-login":
            self._html(runtime.routes.desktop_page())
            return True
        if path == "/healthz":
            payload = {"ok": True, "service": "agent.web"}
            if runtime.auth_fallback_from:
                payload["auth_fallback"] = True
                payload["auth_fallback_to"] = runtime.auth_dir.name
            self._json(200, payload)
            return True
        if path == "/auth/status":
            status, payload, headers = runtime.routes.status(self._identity())
            self._json(status, payload, headers=headers)
            return True
        return False

    def _auth_post_login(self, path: str) -> bool:
        runtime = getattr(self, "auth_runtime", None)
        if runtime is None:
            return False
        if path == "/auth/login":
            body = self._read_body()
            status, payload, headers = runtime.routes.login(
                str(body.get("password") or ""), self._client_ip(),
                secure=self._secure_request())
            self._json(status, payload, headers=headers)
            return True
        if path == "/auth/desktop":
            body = self._read_body()
            status, payload, headers = runtime.routes.desktop_login(
                str(body.get("token") or ""), self._client_ip(),
                secure=self._secure_request())
            self._json(status, payload, headers=headers)
            return True
        return False

    def _auth_logout(self, path: str) -> bool:
        runtime = getattr(self, "auth_runtime", None)
        if runtime is None or path != "/auth/logout":
            return False
        identity = getattr(self, "_auth_identity", None)
        status, payload, headers = runtime.routes.logout(
            identity, cookie_token(self.headers), secure=self._secure_request())
        self._json(status, payload, headers=headers)
        return True
