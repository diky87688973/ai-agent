# -*- coding: utf-8 -*-
"""项目文件枚举：穷举非项目目录与文件，其余全部打包。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

from agent.update.assets import is_local_secret, is_sensitive_plugin_config

# 黑名单：只列不打包的内容；未列出的文件默认打包。
# 根目录黑名单只匹配安装根第一级，插件目录内同名资产不会被误伤。
BLACKLIST_ROOT_DIRS = {
    "data",
    "updates",
    "versions",
    "dist",
    "build",
    "archive",
    "tmp",
    "artifacts",
    "screenshots",
    "logs",
    "docs",
    "tests",
}
# 任意层级都排除的目录；缓存、版本库、虚拟环境没有业务资产。
BLACKLIST_ANY_DIRS = {
    ".git",
    ".github",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".ruff_cache",
    ".pytest_cache",
    ".mypy_cache",
    ".locks",
    "coverage_html",
    "htmlcov",
}
BLACKLIST_DIR_SUFFIXES = (".egg-info",)
BLACKLIST_FILE_NAMES = {".coverage", ".DS_Store", "Thumbs.db", "_PRIVATE_RULE.md"}
BLACKLIST_SUFFIXES = (
    ".pyc",
    ".pyo",
    ".raw",
    ".log",
    ".tmp",
    ".bak",
    ".orig",
    ".rej",
    ".obj",
    ".res",
    ".o",
    ".pdb",
    ".example",
)


def _fold(value: Any) -> str:
    return str(value or "").casefold()


def blacklist_reason(relative: Path) -> str:
    """返回不打包原因；空串表示应打包。规则只看黑名单。"""
    parts = Path(relative).parts
    if not parts:
        return "empty path"
    dirs = [_fold(part) for part in parts[:-1]]
    if dirs and dirs[0] in {_fold(item) for item in BLACKLIST_ROOT_DIRS}:
        return f"root dir {parts[0]}"
    any_dirs = {_fold(item) for item in BLACKLIST_ANY_DIRS}
    for part in dirs:
        if part in any_dirs:
            return f"directory {part}"
        if any(part.endswith(_fold(suffix)) for suffix in BLACKLIST_DIR_SUFFIXES):
            return f"directory {part}"
    name = _fold(parts[-1])
    if name in {_fold(item) for item in BLACKLIST_FILE_NAMES}:
        return f"file {name}"
    if any(name.endswith(_fold(suffix)) for suffix in BLACKLIST_SUFFIXES):
        return f"file suffix {Path(name).suffix}"
    if is_local_secret(Path(relative)) or is_sensitive_plugin_config(Path(relative)):
        return "sensitive config"
    return ""


def project_files(root: Path) -> Iterator[Path]:
    base = Path(root)
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(base)
        if blacklist_reason(relative):
            continue
        yield path
