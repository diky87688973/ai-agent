# -*- coding: utf-8 -*-
"""版本读取与 SemVer 比较。"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_VERSION_RE = re.compile(r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)(?:-(?P<pre>[0-9A-Za-z.-]+))?$")


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: str = ""

    @classmethod
    def parse(cls, raw: str) -> "Version":
        text = str(raw or "").strip()
        match = _VERSION_RE.match(text)
        if match is None:
            raise ValueError(f"版本号不合法：{text}")
        return cls(
            int(match.group("major")),
            int(match.group("minor")),
            int(match.group("patch")),
            str(match.group("pre") or ""),
        )

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{self.prerelease}" if self.prerelease else base


def current_version(root: Optional[Path] = None) -> Version:
    """读取唯一版本源；环境变量仅用于构建/测试注入。"""
    injected = str(os.environ.get("AI_AGENT_VERSION") or "").strip()
    if injected:
        return Version.parse(injected)
    base = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    path = base / "VERSION"
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"读取版本文件失败：{path}") from exc
    if not raw:
        raise RuntimeError(f"版本文件为空：{path}")
    return Version.parse(raw)


def is_newer(remote: Version, local: Version) -> bool:
    """stable 语义：只接受更高版本；预发布不高于同版本正式版。"""
    if remote.major != local.major:
        return remote.major > local.major
    if remote.minor != local.minor:
        return remote.minor > local.minor
    if remote.patch != local.patch:
        return remote.patch > local.patch
    if not remote.prerelease:
        return bool(local.prerelease)
    if not local.prerelease:
        return False
    return remote.prerelease > local.prerelease
