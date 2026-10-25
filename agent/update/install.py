# -*- coding: utf-8 -*-
"""根目录原地更新：备份、覆盖、回滚与清理。"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from agent.update.state import write_state

PROGRAM_DIRS = ("agent", "assets")
ROOT_FILES = ("VERSION",)
CONFIG_FILES = ("config.ini", "plugins.ini", "web-ui-config.ini")
BACKUP_DIR = "updates/backup"
STAGING_DIR = "updates/staging"


def install_root() -> Path:
    injected = str(os.environ.get("AI_AGENT_INSTALL_ROOT") or "").strip()
    if injected:
        return Path(injected)
    return Path(__file__).resolve().parents[2]


def payload_root(root: Optional[Path] = None) -> Path:
    return Path(root) if root is not None else install_root()


def _backup_root(root: Path, previous: str) -> Path:
    base = Path(root) / BACKUP_DIR
    base.mkdir(parents=True, exist_ok=True)
    target = base / previous
    temporary = base / (previous + ".tmp")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    for name in PROGRAM_DIRS:
        source = Path(root) / name
        if source.is_dir():
            shutil.copytree(source, temporary / name)
    for name in ROOT_FILES + CONFIG_FILES:
        source = Path(root) / name
        if source.is_file():
            shutil.copy2(source, temporary / name)
    for item in base.iterdir():
        if item != temporary:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    temporary.replace(target)
    return target


def restore_backup(root: Path, previous: str) -> bool:
    backup = Path(root) / BACKUP_DIR / previous
    if not backup.is_dir():
        return False
    for name in PROGRAM_DIRS:
        target = Path(root) / name
        if target.is_dir():
            shutil.rmtree(target)
        source = backup / name
        if source.is_dir():
            shutil.copytree(source, target)
    for name in ROOT_FILES + CONFIG_FILES:
        source = backup / name
        if source.is_file():
            shutil.copy2(source, Path(root) / name)
    return True


def _copy_program(source: Path, root: Path) -> None:
    for name in PROGRAM_DIRS:
        target = Path(root) / name
        incoming = source / name
        if target.is_dir():
            shutil.rmtree(target)
        if incoming.is_dir():
            shutil.copytree(incoming, target)
    for name in ROOT_FILES:
        incoming = source / name
        if incoming.is_file():
            shutil.copy2(incoming, Path(root) / name)
    plugins_root = Path(root) / "plugins"
    incoming_plugins = source / "plugins"
    if incoming_plugins.is_dir():
        plugins_root.mkdir(parents=True, exist_ok=True)
        for incoming in incoming_plugins.rglob("*"):
            if not incoming.is_file() or "__pycache__" in incoming.parts:
                continue
            relative = incoming.relative_to(incoming_plugins)
            target = plugins_root / relative
            if incoming.name == "plugin-config.ini" and target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(incoming, target)


def _cleanup_staging(root: Path, version: str) -> None:
    for candidate in (Path(root) / STAGING_DIR / version, Path(root) / "updates" / "download"):
        if not candidate.exists():
            continue
        if candidate.is_dir():
            shutil.rmtree(candidate, ignore_errors=True)
        else:
            candidate.unlink(missing_ok=True)


def apply_staged(root: Path, staging: Path, version: str) -> Path:
    root = Path(root).resolve()
    staging = Path(staging).resolve()
    if not (staging / ".ready").is_file():
        raise ValueError("staging 未完成")
    source = staging / "payload" if (staging / "payload").is_dir() else staging
    if not (source / "agent").is_dir():
        raise ValueError("staging 缺少 agent 目录")
    previous = (root / "VERSION").read_text(encoding="utf-8").strip()
    write_state(root, "switching", previous, version)
    _backup_root(root, previous)
    _copy_program(source, root)
    from agent.update.config_merge import merge_ini
    for name in CONFIG_FILES:
        incoming = source / name
        if not incoming.is_file():
            continue
        current = root / name
        if current.is_file():
            merge_ini(current, incoming)
        else:
            shutil.copy2(incoming, current)
    (root / "VERSION").write_text(version + "\n", encoding="utf-8")
    return root


def health_check(payload: Path) -> bool:
    env = dict(os.environ)
    env["AI_AGENT_HEALTH_ROOT"] = str(payload)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "agent.update.health"],
            cwd=str(payload),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def cleanup_after_success(root: Path, version: str) -> None:
    _cleanup_staging(root, version)
