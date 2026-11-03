# -*- coding: utf-8 -*-
"""插件 UI 子树：把 JSON 节点注册到 UI PathRegistry。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List

from agent.core.app_path import app_path


def register_ui_tree(ctx: Any, path: Path) -> List[Any]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    data = raw.get("ui", raw) if isinstance(raw, dict) else {}
    disposers: List[Any] = []
    for row in data.get("slots", []):
        disposers.append(ctx.add_ui_slot(
            row["path"], kind="container", children=row.get("children", "none"),
            fixed_children=tuple(row.get("fixed", ())), owner="*",
            replace=bool(row.get("replace", False))))
    for row in data.get("actions", []):
        action_id = str(row["id"])
        disposers.append(ctx.add_ui_item(
            app_path("shell", "web-ui", "actions", action_id.replace(".", "_")),
            kind="action", props={"label": row.get("label", ""), "action": action_id}))
    for row in data.get("items", []):
        disposers.append(ctx.add_ui_item(
            row["path"], kind="button", props=dict(row.get("props") or {}),
            order=row.get("order"), replace=bool(row.get("replace", False))))
    for row in data.get("tool_shells", []):
        disposers.append(ctx.add_ui_item(
            row["path"], kind="tool-shell", props=dict(row.get("props") or {}),
            replace=bool(row.get("replace", False))))
    return disposers


__all__ = ["register_ui_tree"]
