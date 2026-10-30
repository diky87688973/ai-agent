# -*- coding: utf-8 -*-
"""基础设置插件：宿主内置设置面板与配置项。"""
from __future__ import annotations

from typing import Any, Dict, List

from agent.shell.settings_panel import read_host_value, save_host_value

PANELS = (
    ("settings/agent", "Agent"),
    ("settings/context", "上下文"),
    ("settings/interface", "界面"),
    ("settings/plugin", "插件设置"),
)

FIELDS = (
    {
        "panel": "settings/agent", "key": "reasoning_effort", "section": "agent", "kind": "select",
        "label": "推理档位", "default": "high",
        "options": ({"value": "high", "label": "high"},
                    {"value": "max", "label": "max"}),
    },
    {
        "panel": "settings/agent", "key": "max_passes", "section": "agent", "kind": "number",
        "label": "每回合往返上限", "default": "512",
        "hint": "每回合往返上限≠每回合工具调用次数上限，每次往返可调用 0 个或多个工具",
        "min": 1,
    },
    {
        "panel": "settings/agent", "key": "backup_retention_days", "section": "agent", "kind": "number",
        "label": "AI 修改文件时的备份保存天数", "default": "7", "min": 0,
    },
    {
        "panel": "settings/context", "key": "full_user_rounds", "section": "context", "kind": "number",
        "label": "压缩时保留最近对话轮数", "default": "5", "min": 0,
    },
    {
        "panel": "settings/context", "key": "summary_output_max_chars", "section": "context", "kind": "number",
        "label": "摘要字数上限", "default": "5000", "min": 1,
    },
    {
        "panel": "settings/context", "key": "reasoning_replay_tokens", "section": "context", "kind": "number",
        "label": "思维链回传预算", "default": "8000", "min": -1,
    },
    {
        "panel": "settings/context", "key": "image_turns", "section": "context", "kind": "number",
        "label": "带图用户轮数", "default": "1", "min": 0,
    },
    {
        "panel": "settings/context", "key": "image_max", "section": "context", "kind": "number",
        "label": "带图张数上限", "default": "8", "min": 0,
    },
    {
        "panel": "settings/interface", "key": "display_tool_items", "kind": "checkbox",
        "label": "工作区展示工具步骤", "default": "1", "section": "web-ui",
    },
    {
        "panel": "settings/interface", "key": "display_tool_steps", "kind": "checkbox",
        "label": "侧边栏展示工具步骤", "default": "0", "section": "web-ui",
    },
)


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
        raw = str(number)
    elif kind == "select":
        allowed = {str(option["value"]) for option in field.get("options", ())}
        if raw not in allowed:
            return {"ok": False, "error": f"{field['label']}不在可选范围内"}
    return save_host_value(
        _section(field), field["key"], raw, getattr(ctx, "app", None))


def register(ctx: Any) -> List[Any]:
    disposers: List[Any] = []
    for panel_id, title in PANELS:
        disposers.append(ctx.add_settings_panel(panel_id, title))
    for field in FIELDS:
        def save(value: Any, item: Dict[str, Any] = field) -> Dict[str, Any]:
            return _save(item, ctx, value)

        disposers.append(ctx.add_settings_item(
            field["panel"], field["key"], kind=field["kind"],
            label=field["label"], default=field["default"],
            options=field.get("options", ()), hint=field.get("hint", ""),
            save=save, load=lambda item=field: _load(item),
        ))
    disposers.append(ctx.add_ui_item(
        "web-ui/nav/buttons/settings", kind="button",
        props={"label": "设置", "action": "settings.open"}, order=-1))
    return disposers


PLUGIN_VERSION = "1.0"
