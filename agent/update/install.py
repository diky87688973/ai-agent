# -*- coding: utf-8 -*-
"""版本化安装目录、指针与更新应用。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

from agent.update.state import write_state

POINTER_NAME = "launcher.json"


def install_root() -> Path:
    module = Path(__file__).resolve()
    base = module.parents[2]
    if base.parent.name == "versions":
        return base.parent.parent
    return base


def read_pointer(root: Optional[Path] = None) -> Dict[str, str]:
    base = Path(root) if root is not None else install_root()
    path = base / POINTER_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def write_pointer(root: Path, current: str, previous: str = "") -> None:
    path = Path(root) / POINTER_NAME
    path.write_text(json.dumps({"current": current, "previous": previous},
                               ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def payload_root(root: Optional[Path] = None) -> Path:
    base = Path(root) if root is not None else install_root()
    current = read_pointer(base).get("current", "")
    candidate = base / "versions" / current
    if current and (candidate / "agent").is_dir():
        return candidate
    return base


def apply_staged(root: Path, staging: Path, version: str) -> Path:
    root = Path(root).resolve()
    staging = Path(staging).resolve()
    if not (staging / ".ready").is_file():
        raise ValueError("staging 未完成")
    source = staging / "payload" if (staging / "payload").is_dir() else staging
    previous = read_pointer(root).get("current", "")
    write_state(root, "switching", previous, version)
    target = root / "versions" / version
    if target.exists():
        raise ValueError(f"版本目录已存在：{target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    if temporary.exists():
        shutil.rmtree(temporary)
    shutil.copytree(source, temporary)
    temporary.replace(target)
    from agent.update.config_merge import merge_plugin_configs, merge_templates
    merge_templates(root, target / "templates")
    merge_plugin_configs(root, target)
    write_pointer(root, version, previous)
    return target


def rollback_pointer(root: Path) -> None:
    pointer = read_pointer(root)
    previous = pointer.get("previous", "")
    if previous and (Path(root) / "versions" / previous).is_dir():
        write_pointer(root, previous, "")
    else:
        path = Path(root) / POINTER_NAME
        if path.exists():
            path.unlink()


def health_check(payload: Path) -> bool:
    env = dict(os.environ)
    env["AI_AGENT_HEALTH_ROOT"] = str(install_root())
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
