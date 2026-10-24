# -*- coding: utf-8 -*-
"""更新切换状态。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

STATE_NAME = "updates/state.json"


def state_path(root: Path) -> Path:
    return Path(root) / STATE_NAME


def read_state(root: Path) -> Dict[str, str]:
    try:
        data = json.loads(state_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def write_state(root: Path, phase: str, from_version: str = "",
                to_version: str = "", detail: str = "") -> None:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": phase,
        "from_version": from_version,
        "to_version": to_version,
        "detail": detail,
    }
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def clear_state(root: Path) -> None:
    try:
        state_path(root).unlink()
    except FileNotFoundError:
        return
