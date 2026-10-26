# -*- coding: utf-8 -*-
"""鉴权组合根：装配密码、会话、Token、策略与审计依赖。"""
from __future__ import annotations

import ipaddress
import sys
from pathlib import Path
from typing import Any, Optional

from agent.core.error_report import report_error
from agent.shell.web.auth import config as auth_config
from agent.shell.web.auth.audit import AuthAudit
from agent.shell.web.auth.authenticator import Authenticator
from agent.shell.web.auth.authorizer import Authorizer
from agent.shell.web.auth.bootstrap import DesktopBootstrap
from agent.shell.web.auth.credentials import CredentialStore
from agent.shell.web.auth.providers import load_provider
from agent.shell.web.auth.rate_limit import LoginLimiter
from agent.shell.web.auth.routes import AuthRoutes
from agent.shell.web.auth.security import (
    AuthSecurityError,
    ensure_auth_dir,
    secure_path,
)
from agent.shell.web.auth.sessions import LoginSessionStore
from agent.shell.web.auth.tokens import TokenStore


def _resolve_auth_dir(root: Path, value: str) -> Path:
    raw = Path(str(value or "auth"))
    if raw.is_absolute():
        raise auth_config.AuthConfigError("auth_dir 必须是 data 根下的相对路径")
    base = Path(root).resolve()
    target = (base / raw).resolve()
    if target == base or base not in target.parents:
        raise auth_config.AuthConfigError("auth_dir 必须位于 data 根内")
    return target


_AUTH_FALLBACK_NAMES = tuple(f"auth{index}" for index in range(2, 10))


def _auth_dir_usable(path: Path) -> bool:
    try:
        ensure_auth_dir(path)
        return True
    except AuthSecurityError:
        return False


def _select_auth_dir(root: Path) -> tuple[Path, str]:
    configured = _resolve_auth_dir(root, "auth")
    if _auth_dir_usable(configured):
        return configured, ""
    for name in _AUTH_FALLBACK_NAMES:
        candidate = _resolve_auth_dir(root, name)
        if not _auth_dir_usable(candidate):
            continue
        reason = f"{configured} 不可用，已回退到 {candidate}"
        print(f"[auth] {reason}", file=sys.stderr, flush=True)
        report_error("agent.shell.web.auth.runtime.fallback", reason)
        return candidate, str(configured)
    raise AuthSecurityError(f"鉴权目录及回退目录均不可用：{configured}")


def is_loopback_address(host: str) -> bool:
    try:
        return ipaddress.ip_address(str(host).strip("[]")).is_loopback
    except ValueError:
        return str(host).strip().lower() in ("localhost",)


class AuthRuntime:
    def __init__(self, *, root: Path, config: auth_config.AuthConfig,
                 local_bypass: bool, provider: Any = None,
                 provider_error: str = "") -> None:
        self.data_root = Path(root)
        self.config = config
        self.local_bypass = bool(local_bypass) and config.mode != "required"
        self.provider = provider
        self.provider_error = str(provider_error or "")
        self.bootstrap = DesktopBootstrap.from_env(config.desktop_auto_login)
        self.auth_dir, self.auth_fallback_from = _select_auth_dir(
            self.data_root)
        for name in ("credentials.json", "tokens.json", "tokens.json.lock",
                     "initial-password.txt", "auth.log"):
            candidate = self.auth_dir / name
            if candidate.exists():
                try:
                    secure_path(candidate)
                except AuthSecurityError as exc:
                    report_error(
                        "agent.shell.web.auth.runtime.existing_file", exc)
                    raise
        self.audit = AuthAudit(self.auth_dir / "auth.log")
        self.credentials = CredentialStore(self.auth_dir / "credentials.json")
        self.sessions = LoginSessionStore(ttl_seconds=config.session_seconds)
        self.tokens = TokenStore(self.auth_dir / "tokens.json")
        self.limiter = LoginLimiter(
            max_failures=config.max_failures,
            lock_seconds=config.lock_seconds,
        )
        self.authenticator = Authenticator(
            self.sessions, self.tokens,
            local_bypass=self.local_bypass,
            providers=[provider] if provider is not None else [],
        )
        self.authorizer = Authorizer()
        self.secure_cookie = bool(config.secure_cookie)
        self.routes = AuthRoutes(self)

    @classmethod
    def load(cls, root: Path, *, config_path: Optional[Path] = None,
             host: str = "127.0.0.1") -> "AuthRuntime":
        cfg = auth_config.load_config(config_path)
        provider = None
        provider_error = ""
        if cfg.provider_module:
            provider = load_provider(cfg.provider_module, Path(root), cfg)
            if provider is None:
                provider_error = f"auth provider unavailable: {cfg.provider_module}"
        loopback = is_loopback_address(host)
        return cls(
            root=Path(root),
            config=cfg,
            local_bypass=loopback,
            provider=provider,
            provider_error=provider_error,
        )

    def set_password(self, password: str) -> None:
        self.credentials.set_password(password)

    def issue_token(self, name: str, scopes: Any = None) -> str:
        return self.tokens.issue(name, scopes or ["read"])

    def revoke_token(self, name: str) -> bool:
        return self.tokens.revoke(name)
