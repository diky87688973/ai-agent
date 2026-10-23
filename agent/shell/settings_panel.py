# -*- coding: utf-8 -*-
"""设置页的宿主配置：回显、校验、写回与进程内生效，以及页面路由分派。

宿主配置按节回显，按键写回原来的 ini，注释行留在原处。
保存之后更新当前进程里已经拿着的配置。
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent.config import (
    DEFAULT_CONFIG_PATH,
    get_backup_retention_days,
    get_context,
    get_max_passes,
    get_reasoning_effort,
)
from agent.core.error_report import report_error
from agent.shell.plugin_settings import (
    list_plugins,
    read_plugin_config,
    set_plugin_enabled,
    write_plugin_config,
)
from agent.shell.settings_io import (
    LOCK,
    append_ini_section,
    read_text,
    remove_ini_section,
    update_ini_keys,
    write_text,
)
from agent.shell.web.web_ui_config import WEB_UI_CONFIG_PATH, get_web_ui

__all__ = [
    "append_ini_section",
    "apply_host",
    "handle_get",
    "handle_post",
    "host_catalog",
    "list_plugins",
    "pick_directory",
    "read_plugin_config",
    "remove_ini_section",
    "save_host",
    "set_plugin_enabled",
    "update_ini_keys",
    "write_plugin_config",
]

#: 数字字段的下界。缺下界表示任意整数。
_NUMBER_MIN = {
    "max_passes": 1,
    "backup_retention_days": 0,
    "full_user_rounds": 0,
    "summary_output_max_chars": 1,
    "reasoning_replay_tokens": -1,
}


def _fields() -> List[Dict[str, Any]]:
    """宿主设置的节与控件。值在读取时填，这里只放控件形状。"""
    return [
        {
            "id": "agent",
            "file": "config.ini",
            "title": "Agent",
            "fields": [
                {"key": "reasoning_effort", "kind": "enum", "label": "推理档位",
                 "options": [{"value": "high", "label": "high"},
                             {"value": "max", "label": "max"}]},
                {"key": "max_passes", "kind": "number", "label": "每回合往返上限",
                 "hint": "每回合往返上限≠每回合工具调用次数上限，每次往返可调用 0 个或多个工具",
                 },
                {"key": "backup_retention_days", "kind": "number",
                 "label": "AI 修改文件时的备份保存天数",
                 },
            ],
        },
        {
            "id": "context",
            "file": "config.ini",
            "title": "上下文",
            "fields": [
                {"key": "full_user_rounds", "kind": "number", "label": "压缩时保留最近对话轮数",
                 },
                {"key": "summary_output_max_chars", "kind": "number", "label": "摘要字数上限",
                 },
                {"key": "reasoning_replay_tokens", "kind": "number", "label": "思维链回传预算",
                 },
                {"key": "image_turns", "kind": "number", "label": "带图用户轮数",
                 },
                {"key": "image_max", "kind": "number", "label": "带图张数上限",
                 },
            ],
        },
        {
            "id": "web-ui",
            "file": "web-ui-config.ini",
            "title": "界面",
            "fields": [
                {"key": "display_tool_items", "kind": "bool", "label": "工作区展示工具步骤",
                 },
                {"key": "display_tool_steps", "kind": "bool", "label": "侧边栏展示工具步骤",
                 },
            ],
        },
    ]


def _effective_values(config_path: Path, web_ui_path: Path) -> Dict[str, Dict[str, str]]:
    """表单回显用的当前值：文件里有的用文件的，没有的用运行时缺省。"""
    ctx = get_context(config_path)
    web = get_web_ui(web_ui_path)
    return {
        "agent": {
            "reasoning_effort": get_reasoning_effort(config_path),
            "max_passes": str(get_max_passes(config_path)),
            "backup_retention_days": str(get_backup_retention_days(config_path)),
        },
        "context": {
            "full_user_rounds": str(ctx["full_user_rounds"]),
            "summary_output_max_chars": str(ctx["summary_output_max_chars"]),
            "reasoning_replay_tokens": str(ctx["reasoning_replay_tokens"]),
            "image_turns": str(ctx["image_turns"]),
            "image_max": str(ctx["image_max"]),
        },
        "web-ui": {
            "display_tool_items": "1" if web["display_tool_items"] else "0",
            "display_tool_steps": "1" if web["display_tool_steps"] else "0",
        },
    }


def host_catalog(config_path: Optional[Path] = None,
                 web_ui_path: Optional[Path] = None) -> Dict[str, Any]:
    """设置页左侧各节和当前值。"""
    config_target = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
    web_target = Path(web_ui_path) if web_ui_path is not None else WEB_UI_CONFIG_PATH
    current = _effective_values(config_target, web_target)
    sections = []
    for spec in _fields():
        fields = []
        for field in spec["fields"]:
            stored = str(current.get(spec["id"], {}).get(field["key"], ""))
            item = {
                "key": field["key"],
                "kind": field["kind"],
                "label": field["label"],
                "value": stored,
                "hint": field.get("hint") or "",
                "placeholder": field.get("placeholder") or "",
            }
            if field["kind"] == "secret":
                # 回显只说明有没有配过。明文密钥不出接口。
                configured = bool(stored.strip())
                item["value"] = ""
                item["configured"] = configured
                item["placeholder"] = (
                    "已设置秘钥,可重新设置并替换" if configured
                    else (field.get("placeholder") or "未配置秘钥")
                )
            if field.get("options"):
                item["options"] = list(field["options"])
            fields.append(item)
        sections.append({"id": spec["id"], "title": spec["title"], "fields": fields})
    return {"ok": True, "sections": sections}


def _as_text(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value if value is not None else "").strip()


def _check_value(field: Dict[str, Any], raw: str) -> str:
    kind = field["kind"]
    if "\n" in raw or "\r" in raw:
        raise ValueError(f"{field['label']}不能换行")
    if kind == "bool":
        if raw in ("1", "true", "True", "on"):
            return "1"
        if raw in ("0", "false", "False", "off", ""):
            return "0"
        raise ValueError(f"{field['label']}只能是开或关")
    if kind == "enum":
        allowed = [str(item["value"]) for item in field.get("options") or []]
        if raw not in allowed:
            raise ValueError(f"{field['label']}不在可选范围内")
        return raw
    if kind == "number":
        try:
            number = int(raw)
        except (TypeError, ValueError):
            raise ValueError(f"{field['label']}要填整数") from None
        floor = _NUMBER_MIN.get(field["key"])
        if floor is not None and number < floor:
            raise ValueError(f"{field['label']}不能小于 {floor}")
        return str(number)
    limit = 2000
    if len(raw) > limit:
        raise ValueError(f"{field['label']}过长")
    return raw


def save_host(values: Any, app: Any = None, *,
              config_path: Optional[Path] = None,
              web_ui_path: Optional[Path] = None) -> Dict[str, Any]:
    """校验并写回宿主配置，然后让当前进程用上新值。"""
    if not isinstance(values, dict):
        return {"ok": False, "error": "缺少配置内容"}
    config_target = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
    web_target = Path(web_ui_path) if web_ui_path is not None else WEB_UI_CONFIG_PATH
    grouped: Dict[str, Dict[str, Dict[str, str]]] = {}
    try:
        for spec in _fields():
            incoming = values.get(spec["id"])
            if incoming is None:
                continue
            if not isinstance(incoming, dict):
                return {"ok": False, "error": f"{spec['title']}的内容格式不对"}
            bucket = grouped.setdefault(spec["file"], {})
            section_updates = bucket.setdefault(spec["id"], {})
            known = {field["key"]: field for field in spec["fields"]}
            for key, value in incoming.items():
                field = known.get(str(key))
                if field is None:
                    continue
                checked = _check_value(field, _as_text(value))
                # 密码框留空表示不改。有内容才覆盖原来的密钥。
                if field["kind"] == "secret" and not checked:
                    continue
                section_updates[field["key"]] = checked
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    with LOCK:
        config_text = read_text(config_target)
        web_text = read_text(web_target)
        for filename, sections in grouped.items():
            target_text = config_text if filename == "config.ini" else web_text
            for section, updates in sections.items():
                if updates:
                    target_text = update_ini_keys(target_text, section, updates)
            if filename == "config.ini":
                config_text = target_text
            else:
                web_text = target_text
        if "config.ini" in grouped:
            write_text(config_target, config_text)
        if "web-ui-config.ini" in grouped:
            write_text(web_target, web_text)
        applied = apply_host(app, config_path=config_target) if app is not None else {}
    payload = {"ok": True, "web_ui": get_web_ui(web_target)}
    if applied.get("error"):
        payload["reload_error"] = applied["error"]
    elif applied.get("note"):
        payload["reload_note"] = applied["note"]
    return payload


def apply_host(app: Any, *, config_path: Optional[Path] = None) -> Dict[str, str]:
    """把已经落盘的宿主配置写进当前进程拿着的对象。

    启动期抄进对象的副本在这里补：推理档位、图片上限、往返上限。
    模型由多模型插件维护。
    """
    if app is None:
        return {}
    target = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
    applied: Dict[str, str] = {}
    try:
        state = getattr(app, "live_state", None)
        if state is not None:
            state.default_effort = get_reasoning_effort(target)
        ctx = get_context(target)
        defaults = getattr(app, "context_defaults", None)
        if isinstance(defaults, dict):
            defaults.update({
                "full_user_rounds": int(ctx["full_user_rounds"]),
                "reasoning_replay_tokens": int(ctx["reasoning_replay_tokens"]),
            })
        if hasattr(app, "image_turns"):
            app.image_turns = int(ctx["image_turns"])
        if hasattr(app, "image_max"):
            app.image_max = int(ctx["image_max"])
        if hasattr(app, "max_passes"):
            app.max_passes = get_max_passes(target)
    except Exception as exc:
        report_error("agent.shell.settings_panel.apply_host", exc)
        return {"error": f"{type(exc).__name__}: {exc}"}
    return applied


def pick_directory() -> Dict[str, Any]:
    """弹出系统目录选择窗口。取消时不报错，只表示没选。"""
    if os.name != "nt":
        return {"ok": False, "error": "当前系统没有目录选择窗口"}
    script = (
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n"
        "Add-Type -AssemblyName System.Windows.Forms\n"
        "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog\n"
        "$dialog.Description = '选择目录'\n"
        "$dialog.ShowNewFolderButton = $true\n"
        "if ($dialog.ShowDialog() -eq 'OK') { [Console]::Out.WriteLine($dialog.SelectedPath) }\n"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command", script],
            capture_output=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "目录选择超时"}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    chosen = proc.stdout.decode("utf-8", errors="replace").strip()
    if not chosen:
        if proc.returncode not in (0, None):
            detail = proc.stderr.decode("utf-8", errors="replace").strip()
            return {"ok": False, "error": detail or "目录选择失败"}
        return {"ok": False, "cancelled": True}
    return {"ok": True, "path": chosen}


def handle_get(path: str, query: Dict[str, str],
               app: Any = None) -> Tuple[int, Dict[str, Any]]:
    if path == "/api/settings":
        return 200, host_catalog()
    if path == "/api/settings/plugins":
        return 200, list_plugins()
    if path == "/api/settings/plugin-file":
        payload = read_plugin_config(query.get("name", ""))
        return (200 if payload.get("ok") else 400), payload
    return 404, {"ok": False, "error": "not found"}


def handle_post(path: str, body: Dict[str, Any], app: Any) -> Tuple[int, Dict[str, Any]]:
    if path == "/api/settings":
        payload = save_host(body.get("values"), app)
        return (200 if payload.get("ok") else 400), payload
    if path == "/api/settings/plugins":
        enabled = body.get("enabled")
        if not isinstance(enabled, bool):
            return 400, {"ok": False, "error": "enabled 要是布尔值"}
        payload = set_plugin_enabled(str(body.get("name") or ""), enabled, app)
        return (200 if payload.get("ok") else 400), payload
    if path == "/api/settings/plugin-file":
        payload = write_plugin_config(
            str(body.get("name") or ""), body.get("text"), body.get("groups"),
            body.get("fields"), app)
        return (200 if payload.get("ok") else 400), payload
    if path == "/api/settings/pick-dir":
        payload = pick_directory()
        return (200 if payload.get("ok") or payload.get("cancelled") else 400), payload
    return 404, {"ok": False, "error": "not found"}
