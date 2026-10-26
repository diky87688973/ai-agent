# -*- coding: utf-8 -*-
"""鉴权配置：只读取 [auth] 节，不把 auth 键带进 core。"""
from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from agent.config_schema import AUTH_DEFAULTS
from agent.core.error_report import report_error

MODES = ("auto", "required", "local")


class AuthConfigError(ValueError):
    """配置不可读或非法；鉴权配置不能静默降级。"""


@dataclass(frozen=True)
class AuthConfig:
    mode: str = AUTH_DEFAULTS["mode"]
    session_hours: int = int(AUTH_DEFAULTS["session_hours"])
    max_failures: int = int(AUTH_DEFAULTS["max_failures"])
    lock_seconds: int = int(AUTH_DEFAULTS["lock_seconds"])
    trusted_proxies: Tuple[str, ...] = ()
    allowed_hosts: Tuple[str, ...] = tuple(
        AUTH_DEFAULTS["allowed_hosts"].split(","))
    cookie_secure: str = AUTH_DEFAULTS["cookie_secure"]
    provider_module: str = AUTH_DEFAULTS["provider_module"]
    desktop_auto_login: bool = AUTH_DEFAULTS["desktop_auto_login"] == "1"

    @property
    def session_seconds(self) -> int:
        return max(1, int(self.session_hours)) * 3600

    @property
    def secure_cookie(self) -> bool:
        return str(self.cookie_secure).strip().lower() in ("1", "true", "yes", "on")


def load_config(path: Optional[Path] = None) -> AuthConfig:
    """读取 [auth]；文件存在但无法解析时停止，不回落为免登录模式。"""
    target = Path(path) if path is not None else Path("config.ini")
    if not target.exists():
        return AuthConfig()
    if not target.is_file():
        raise AuthConfigError(f"鉴权配置不是文件：{target}")
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        text = target.read_text(encoding="utf-8-sig")
        parser.read_string(text, source=str(target))
    except (OSError, UnicodeError, configparser.Error) as exc:
        raise AuthConfigError(f"鉴权配置无法读取：{target}：{exc}") from exc
    section = parser["auth"] if parser.has_section("auth") else None

    def _text(key: str, default: str) -> str:
        if section is None:
            return default
        try:
            return str(section.get(key, fallback=default)).strip()
        except Exception as exc:
            report_error("agent.shell.web.auth.config.read", exc)
            return default

    def _int(key: str, default: int, low: int) -> int:
        try:
            return max(low, int(_text(key, str(default))))
        except (TypeError, ValueError) as exc:
            raise AuthConfigError(f"[auth] {key} 必须是整数") from exc

    def _bool(key: str, default: bool) -> bool:
        value = _text(key, "1" if default else "0").lower()
        return value in ("1", "true", "yes", "on")

    mode = _text("mode", AUTH_DEFAULTS["mode"]).lower()
    if mode not in MODES:
        raise AuthConfigError(f"[auth] mode 非法：{mode}")
    proxies = tuple(
        item.strip() for item in _text("trusted_proxies", "").split(",")
        if item.strip()
    )
    hosts = tuple(
        item.strip() for item in _text(
            "allowed_hosts", AUTH_DEFAULTS["allowed_hosts"]).split(",")
        if item.strip()
    )
    return AuthConfig(
        mode=mode,
        session_hours=_int("session_hours", int(AUTH_DEFAULTS["session_hours"]), 1),
        max_failures=_int("max_failures", int(AUTH_DEFAULTS["max_failures"]), 1),
        lock_seconds=_int("lock_seconds", int(AUTH_DEFAULTS["lock_seconds"]), 1),
        trusted_proxies=proxies,
        allowed_hosts=hosts,
        cookie_secure=_text("cookie_secure", AUTH_DEFAULTS["cookie_secure"]),
        provider_module=_text("provider_module", AUTH_DEFAULTS["provider_module"]),
        desktop_auto_login=_bool("desktop_auto_login", AUTH_DEFAULTS["desktop_auto_login"] == "1"),
    )
