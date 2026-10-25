# -*- coding: utf-8 -*-
"""更新 manifest 解析与哈希校验。"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List

from agent.update.version import Version

MAX_MANIFEST_BYTES = 256 * 1024
MAX_ASSET_BYTES = 1024 * 1024 * 1024


@dataclass(frozen=True)
class UpdateManifest:
    version: Version
    channel: str
    asset_name: str
    asset_size: int
    asset_sha256: str
    published_at: str
    notes: List[str]
    raw: bytes

    @property
    def signature(self) -> str:
        return ""


def _text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"manifest 缺少 {name}")
    return text


def _hash(value: Any) -> str:
    text = _text(value, "asset.sha256").lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError("manifest asset.sha256 必须是 64 位十六进制")
    return text


def parse_manifest(raw: bytes) -> UpdateManifest:
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("manifest 超过大小上限")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"manifest 不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise ValueError("manifest schema 必须为 1")
    asset = data.get("asset")
    if not isinstance(asset, dict):
        raise ValueError("manifest 缺少 asset")
    try:
        size = int(asset.get("size") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("manifest asset.size 必须是整数") from exc
    if size <= 0 or size > MAX_ASSET_BYTES:
        raise ValueError("manifest asset.size 超出范围")
    notes = data.get("notes")
    return UpdateManifest(
        version=Version.parse(_text(data.get("version"), "version")),
        channel=_text(data.get("channel"), "channel"),
        asset_name=Path(_text(asset.get("name"), "asset.name")).name,
        asset_size=size,
        asset_sha256=_hash(asset.get("sha256")),
        published_at=str(data.get("published_at") or ""),
        notes=[str(item) for item in notes] if isinstance(notes, list) else [],
        raw=raw,
    )


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def manifest_digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def verify_asset(path: Path, manifest: UpdateManifest) -> None:
    actual_size = path.stat().st_size
    if actual_size != manifest.asset_size:
        raise ValueError(f"更新包大小不符：{actual_size} != {manifest.asset_size}")
    actual_hash = sha256_file(path)
    if actual_hash != manifest.asset_sha256:
        raise ValueError("更新包 SHA-256 校验失败")
