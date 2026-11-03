# -*- coding: utf-8 -*-
"""基础设置插件：从 plugin-ui.json 注册面板与条目。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from agent.capabilities.plugin_settings_tree import register_settings_tree
from agent.shell.settings_panel import read_host_value, save_host_value


def _section(field: Dict[str, Any]) -> str:
    return str(field.get("section") or "config")


def _load(field: Dict[str, Any]) -> str:
    return read_host_value(_section(field), field["key"])


def _save(field: Dict[str, Any], ctx: Any, value: Any) -> Dict[str, Any]:
    raw = "1" if value is True else ("0" if value is False else str(value or "").strip())
    kind = field["kind"]
    if kind == "checkbox":
        if raw in ("1", "true", "True", "on"):
            raw = "1"
        elif raw in ("0", "false", "False", "off", ""):
            raw = "0"
        else:
            return {"ok": False, "error": f"{field['label']}只能是开或关"}
    elif kind == "number":
        try:
            number = int(raw)
        except (TypeError, ValueError):
            return {"ok": False, "error": f"{field['label']}要填整数"}
        floor = field.get("min")
        if floor is not None and number < floor:
            return {"ok": False, "error": f"{field['label']}不能小于 {floor}"}
        ceiling = field.get("max")
        if ceiling is not None and number > ceiling:
            return {"ok": False, "error": f"{field['label']}不能大于 {ceiling}"}
        raw = str(number)
    elif kind == "select":
        allowed = {str(option["value"]) for option in field.get("options", ())}
        if raw not in allowed:
            return {"ok": False, "error": f"{field['label']}不在可选范围内"}
    return save_host_value(
        _section(field), field["key"], raw, getattr(ctx, "app", None))


def register(ctx: Any) -> List[Any]:
    return register_settings_tree(
        ctx, Path(__file__).with_name("plugin-ui.json"),
        load=_load, save=lambda field, value: _save(field, ctx, value))


PLUGIN_VERSION = "1.0"
