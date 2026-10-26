# -*- coding: utf-8 -*-
"""HTTP 可信边界：代理后的来源地址、HTTPS 判定与 Host 校验。"""
from __future__ import annotations

import ipaddress
from typing import Any, Iterable, Optional, Tuple
from urllib.parse import urlsplit

from agent.core.error_report import report_error


def _ip(value: str) -> Optional[ipaddress._BaseAddress]:
    try:
        return ipaddress.ip_address(str(value).strip())
    except ValueError:
        return None


def _networks(values: Iterable[str]) -> Tuple[Any, ...]:
    result = []
    for value in values:
        try:
            result.append(ipaddress.ip_network(str(value).strip(), strict=False))
        except ValueError as exc:
            report_error("agent.shell.web.auth.request.trusted_proxy", exc)
            continue
    return tuple(result)


def _trusted(remote_ip: str, trusted_proxies: Iterable[str]) -> bool:
    address = _ip(remote_ip)
    if address is None:
        return False
    return any(address in network for network in _networks(trusted_proxies))


def client_ip(headers: Any, remote_ip: str,
              trusted_proxies: Iterable[str]) -> str:
    if not _trusted(remote_ip, trusted_proxies):
        return str(remote_ip)
    forwarded = str(headers.get("X-Forwarded-For") or "")
    for item in forwarded.split(","):
        candidate = item.strip()
        if _ip(candidate) is not None:
            return candidate
    return str(remote_ip)


def secure_request(headers: Any, remote_ip: str,
                   trusted_proxies: Iterable[str], is_tls: bool) -> bool:
    if is_tls:
        return True
    if not _trusted(remote_ip, trusted_proxies):
        return False
    return str(headers.get("X-Forwarded-Proto") or "").strip().lower() == "https"


def _host_name(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit("//" + raw)
        return str(parsed.hostname or "").strip().lower()
    except ValueError:
        return ""


def host_allowed(host_header: str, allowed_hosts: Iterable[str]) -> bool:
    host = _host_name(host_header)
    if not host:
        return False
    allowed = {_host_name(item) for item in allowed_hosts}
    allowed.discard("")
    return host in allowed
