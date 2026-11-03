# -*- coding: utf-8 -*-
"""版本读取与 SemVer 比较。"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import total_ordering
from pathlib import Path
from typing import Optional

_VERSION_RE = re.compile(r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)(?:-(?P<pre>[0-9A-Za-z.-]+))?$")


def _compare_prerelease(left: str, right: str) -> int:
    """SemVer 2.0 预发布优先级；返回 -1 / 0 / 1。"""
    if not left and not right:
        return 0
    if not left:
        return 1                  # 正式版高于同版本预发布
    if not right:
        return -1
    lparts = left.split(".")
    rparts = right.split(".")
    for lpart, rpart in zip(lparts, rparts):
        ln, rn = lpart.isdigit(), rpart.isdigit()
        if ln and rn:
            li, ri = int(lpart), int(rpart)
            if li != ri:
                return -1 if li < ri else 1
        elif ln != rn:
            return -1 if ln else 1   # 数字标识符低于字母标识符
        elif lpart != rpart:
            return -1 if lpart < rpart else 1
    if len(lparts) != len(rparts):
        return -1 if len(lparts) < len(rparts) else 1
    return 0


@total_ordering
@dataclass(frozen=True)
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

    def _core(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        if self._core() != other._core():
            return self._core() < other._core()
        return _compare_prerelease(self.prerelease, other.prerelease) < 0

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


def is_dev_checkout(root: Optional[Path] = None) -> bool:
    if str(os.environ.get("AI_AGENT_DEV") or "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    base = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    return (base / ".git").exists()


def is_newer(remote: Version, local: Version) -> bool:
    """SemVer 优先级：主次补丁优先，预发布按标识符规则比较。"""
    if remote.major != local.major:
        return remote.major > local.major
    if remote.minor != local.minor:
        return remote.minor > local.minor
    if remote.patch != local.patch:
        return remote.patch > local.patch
    return _compare_prerelease(remote.prerelease, local.prerelease) > 0
