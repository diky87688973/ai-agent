# -*- coding: utf-8 -*-
"""插件设置子树：面板、条目与 UI 按钮由 JSON 描述。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, List


def register_settings_tree(ctx: Any, path: Path,
                           load: Callable[[dict], Any],
                           save: Callable[[dict, Any], Any]) -> List[Any]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    data = raw.get("settings", raw) if isinstance(raw, dict) else {}
    disposers: List[Any] = []
    for panel in data.get("panels", []):
        disposers.append(ctx.add_settings_panel(
            panel["id"], panel["title"],
            replace=bool(panel.get("replace", False))))
    for field in data.get("fields", []):
        def _save(value: Any, item: dict = field) -> Any:
            return save(item, value)
        disposers.append(ctx.add_settings_item(
            field["panel"], field["key"], kind=field["kind"],
            label=field["label"], default=field["default"],
            options=tuple(field.get("options", ())), hint=field.get("hint", ""),
            save=_save, load=lambda item=field: load(item),
            replace=bool(field.get("replace", False))))
    for item in data.get("ui_items", []):
        disposers.append(ctx.add_ui_item(
            item["path"], kind=item.get("kind", "button"),
            props=dict(item.get("props") or {}), order=item.get("order")))
    return disposers


__all__ = ["register_settings_tree"]
