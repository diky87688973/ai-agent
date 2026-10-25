# -*- coding: utf-8 -*-
"""项目文件枚举：穷举非项目目录与文件，其余全部打包。"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from agent.update.assets import is_local_secret, is_sensitive_plugin_config

NON_PROJECT_DIRS = {
    ".git",
    ".github",
    ".venv",
    "venv",
    "env",
    "data",
    "tests",
    "docs",
    "updates",
    "versions",
    "dist",
    "build",
    "__pycache__",
    ".ruff_cache",
    ".pytest_cache",
    ".mypy_cache",
    ".locks",
    "coverage_html",
    "htmlcov",
}
NON_PROJECT_NAMES = {".coverage", ".DS_Store", "Thumbs.db", "_PRIVATE_RULE.md"}
NON_PROJECT_SUFFIXES = (
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


def project_files(root: Path) -> Iterator[Path]:
    base = Path(root)
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(base)
        if any(part in NON_PROJECT_DIRS for part in relative.parts[:-1]):
            continue
        if path.name in NON_PROJECT_NAMES:
            continue
        if path.name.endswith(NON_PROJECT_SUFFIXES):
            continue
        if is_local_secret(path) or is_sensitive_plugin_config(path):
            continue
        yield path
