# -*- coding: utf-8 -*-
"""会话运行态的目录布局。"""
from __future__ import annotations

from pathlib import Path


def session_root(data_root: Path) -> Path:
    return Path(data_root) / "session"


def state_dir(data_root: Path) -> Path:
    return session_root(data_root) / "state"


def raw_dir(data_root: Path) -> Path:
    return session_root(data_root) / "raw"


def titles_dir(data_root: Path) -> Path:
    return session_root(data_root) / "titles"


def ensure_layout(data_root: Path) -> None:
    """建立会话目录；旧布局不读取、不复制、不保留标记。"""
    root = Path(data_root)
    for target in (state_dir(root), raw_dir(root), titles_dir(root)):
        target.mkdir(parents=True, exist_ok=True)
