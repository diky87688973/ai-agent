# -*- coding: utf-8 -*-
"""根目录原地更新：备份、覆盖、回滚与清理。"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from agent.update.config_merge import merge_ini
from agent.update.state import write_state

RUNTIME_DIRS = ("data", "updates")
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
    """备份根目录全部现有文件；data/ 与 updates/ 属于运行态，不备份。"""
    root = Path(root).resolve()
    base = Path(root) / BACKUP_DIR
    base.mkdir(parents=True, exist_ok=True)
    target = base / previous
    temporary = base / (previous + ".tmp")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    for source in root.rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(root)
        if relative.parts and relative.parts[0] in RUNTIME_DIRS:
            continue
        destination = temporary / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    for item in base.iterdir():
        if item != temporary:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    temporary.replace(target)
    return target


def restore_backup(root: Path, previous: str) -> bool:
    """恢复备份中的全部文件，并删除更新新增的文件。"""
    root = Path(root).resolve()
    backup = Path(root) / BACKUP_DIR / previous
    if not backup.is_dir():
        return False
    for source in backup.rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(backup)
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for current in root.rglob("*"):
        if not current.is_file():
            continue
        relative = current.relative_to(root)
        if relative.parts and relative.parts[0] in RUNTIME_DIRS:
            continue
        if not (backup / relative).is_file():
            current.unlink()
    return True


def _replace_locked_file(incoming: Path, target: Path, root: Path) -> None:
    """Windows 锁住正在运行的 exe 时，先改名归档，再写入新文件。

    agent-gui.exe 由它自己启动更新时仍被映射在进程里；Windows 允许改名，
    不允许直接覆盖。归档放在 updates/ 下，回滚不碰 runtime 目录。
    """
    archive_dir = Path(root) / "updates" / "launcher"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archived = archive_dir / f"{target.name}.old-{time.time_ns()}"
    target.rename(archived)
    try:
        shutil.copy2(incoming, target)
    except Exception:
        try:
            archived.rename(target)
        except OSError:
            pass
        raise


def _copy_program(source: Path, root: Path) -> None:
    """覆盖 payload 全部文件；*.ini 保留用户 key，其余原样覆盖；不删除。"""
    root = Path(root).resolve()
    for incoming in Path(source).rglob("*"):
        if not incoming.is_file() or "__pycache__" in incoming.parts:
            continue
        relative = incoming.relative_to(source)
        if relative.name == ".ready":
            continue
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if relative.suffix.lower() == ".ini":
            merge_ini(target, incoming)
        else:
            try:
                shutil.copy2(incoming, target)
            except OSError as exc:
                if getattr(exc, "winerror", None) not in (32, 33):
                    raise
                _replace_locked_file(incoming, target, root)


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
