# -*- coding: utf-8 -*-
"""基础设置插件：提供面板与条目的装配工厂。"""
from __future__ import annotations

from typing import Any, Dict

from agent.core.error_report import report_error
from agent.core.slot_spec import (
    SettingDecl,
    SlotAssemblyError,
    SlotConfigError,
)
from agent.shell.settings_panel import read_host_value, save_host_value


def _section(field: Dict[str, Any]) -> str:
    return str(field.get("section") or "config")


def _load(field: Dict[str, Any]) -> Any:
    """读取边界：开关在 ini 里是 0/1，交给界面的一律是布尔。

    缺省时不能直接 bool(default)：config_schema 里的 default 是文本 "0"，
    bool("0") 为真，开关会被误当成开。
    """
    raw = str(read_host_value(_section(field), field["key"]) or "").strip()
    if field["kind"] != "checkbox":
        return raw
    text = raw
    if not text:
        fallback = field.get("default")
        if isinstance(fallback, bool):
            return fallback
        text = str(fallback or "").strip()
        if not text:
            return False
    if text == "1":
        return True
    if text == "0":
        return False
    raise ValueError(f"{field['label']} 只接受 0 或 1，收到 {raw!r}")


def _save(field: Dict[str, Any], app: Any, value: Any) -> Dict[str, Any]:
    kind = field["kind"]
    if kind == "checkbox":
        # 开关只接受真布尔，写进 ini 一律 0/1。
        if value is True:
            raw = "1"
        elif value is False:
            raw = "0"
        else:
            return {"ok": False, "error": f"{field['label']}只能是开或关"}
    else:
        raw = str(value or "").strip()
    if kind == "number":
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
    result = save_host_value(
        _section(field), field["key"], raw, app)
    if not isinstance(result, dict) or not result.get("ok"):
        return result if isinstance(result, dict) else {"ok": False, "error": "保存失败"}
    if kind != "checkbox":
        return result
    # 写后回读：写入被回滚或写到别处时这里能抓住，否则界面显示已保存而文件里还是旧值。
    try:
        stored = _load(field)
    except Exception as exc:
        report_error("plugin.base_settings.reload_check", exc, key=field["key"])
        return {"ok": False, "error": f"{field['label']}写入后回读失败：{exc}"}
    if stored is not value:
        return {"ok": False,
                "error": f"{field['label']}写入后回读不一致：期望 {value}，实际 {stored}"}
    return result


def _panel(ctx: Any) -> SettingDecl:
    """面板声明：标题取节点 props.title。"""
    return SettingDecl(kind="panel", label=str(ctx.spec.props.get("title") or ""))


def _field(ctx: Any, app: Any, kind: str) -> SettingDecl:
    """条目声明：展示字段全部取自节点 props，与 plugin-ui.json 同形。

    `save` / `load` 是函数，写不进 JSON，故只能在这里闭包捕获 App。
    App 缺失时直接报错：静默传入 None 会让保存默默失效。
    """
    props = dict(ctx.spec.props)
    if str(props.get("kind") or "") != kind:
        raise SlotConfigError(
            f"设置条目与工厂不匹配：{ctx.spec.path} 为 {props.get('kind')}，"
            f"期望 {kind}")
    if app is None:
        raise SlotAssemblyError(f"设置条目缺少 App：{ctx.spec.path}")
    return SettingDecl(
        kind=kind,
        label=str(props.get("label") or ""),
        default=str(props.get("default") or ""),
        options=tuple(props.get("options") or ()),
        hint=str(props.get("hint") or ""),
        save=lambda value: _save(props, app, value),
        load=lambda: _load(props),
    )


def make_panel_agent(ctx: Any) -> SettingDecl:
    return _panel(ctx)


def make_panel_context(ctx: Any) -> SettingDecl:
    return _panel(ctx)


def make_panel_interface(ctx: Any) -> SettingDecl:
    return _panel(ctx)


def make_panel_plugin(ctx: Any) -> SettingDecl:
    return _panel(ctx)


def make_field_agent_select(ctx: Any, app: Any = None) -> SettingDecl:
    return _field(ctx, app, "select")


def make_field_agent_number(ctx: Any, app: Any = None) -> SettingDecl:
    return _field(ctx, app, "number")


def make_field_agent_checkbox(ctx: Any, app: Any = None) -> SettingDecl:
    return _field(ctx, app, "checkbox")


def make_field_context_number(ctx: Any, app: Any = None) -> SettingDecl:
    return _field(ctx, app, "number")


def make_field_web_ui_checkbox(ctx: Any, app: Any = None) -> SettingDecl:
    return _field(ctx, app, "checkbox")
