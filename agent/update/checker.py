# -*- coding: utf-8 -*-
"""远端 manifest 检查。"""
from __future__ import annotations

import os
import urllib.request
from dataclasses import dataclass
from typing import Optional

from agent.core.error_report import report_error
from agent.update.manifest import MAX_MANIFEST_BYTES, UpdateManifest, parse_manifest
from agent.update.version import current_version, is_newer

MANIFEST_ENV = "AI_AGENT_UPDATE_MANIFEST_URL"
DEFAULT_MANIFEST_URL = (
    "https://github.com/diky87688973/ai-agent/releases/latest/download/manifest.json"
)
DEFAULT_TIMEOUT_SEC = 45.0


@dataclass(frozen=True)
class UpdateStatus:
    available: bool
    current: str
    remote: str
    channel: str
    manifest: Optional[UpdateManifest]
    detail: str = ""


def manifest_url() -> str:
    return str(os.environ.get(MANIFEST_ENV) or DEFAULT_MANIFEST_URL).strip()


def fetch_manifest(url: str, timeout: float = DEFAULT_TIMEOUT_SEC) -> UpdateManifest:
    if not url.lower().startswith("https://"):
        raise ValueError("更新地址必须是 HTTPS")
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_MANIFEST_BYTES + 1)
    return parse_manifest(raw)


def check(root=None, url: Optional[str] = None) -> UpdateStatus:
    local = current_version(root)
    target = str(url if url is not None else manifest_url()).strip()
    if not target:
        return UpdateStatus(False, str(local), "", "", None, "disabled")
    try:
        manifest = fetch_manifest(target)
    except Exception as exc:
        report_error("agent.update.checker.check", exc)
        return UpdateStatus(False, str(local), "", "", None, f"check_failed: {type(exc).__name__}")
    if manifest.channel != "stable":
        return UpdateStatus(False, str(local), str(manifest.version), manifest.channel,
                            None, "channel_mismatch")
    available = is_newer(manifest.version, local)
    return UpdateStatus(
        available,
        str(local),
        str(manifest.version),
        manifest.channel,
        manifest,
        "available" if available else "up_to_date",
    )
