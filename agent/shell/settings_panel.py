# -*- coding: utf-8 -*-
"""设置页的宿主配置：回显、校验、写回与进程内生效，以及页面路由分派。

宿主配置按节回显，按键写回原来的 ini，注释行留在原处。
保存之后更新当前进程里已经拿着的配置。
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

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
    read_text,
    update_ini_keys,
    write_text,
)
from agent.shell.web.web_ui_config import WEB_UI_CONFIG_PATH, get_web_ui

__all__ = [
    "apply_host",
    "handle_get",
    "handle_post",
    "host_catalog",
    "list_plugins",
    "pick_directory",
    "read_plugin_config",
    "set_plugin_enabled",
    "update_ini_keys",
    "write_plugin_config",
]

def read_host_value(section: str, key: str) -> str:
    """读取宿主配置的单个值，供内置设置插件回填。"""
    if section == "web-ui":
        value = get_web_ui(WEB_UI_CONFIG_PATH).get(key, "")
        return "1" if value else "0"
    if section == "agent":
        getters = {
            "reasoning_effort": get_reasoning_effort,
            "max_passes": get_max_passes,
            "backup_retention_days": get_backup_retention_days,
        }
        getter = getters.get(key)
        return str(getter(DEFAULT_CONFIG_PATH)) if getter is not None else ""
    ctx = get_context(DEFAULT_CONFIG_PATH)
    return str(ctx.get(key, ""))


def save_host_value(section: str, key: str, value: Any, app: Any = None) -> Dict[str, Any]:
    """写入宿主配置的单个值；调用方负责字段校验。"""
    raw = _as_text(value)
    if "\n" in raw or "\r" in raw:
        return {"ok": False, "error": "设置值不能换行"}
    target = WEB_UI_CONFIG_PATH if section == "web-ui" else DEFAULT_CONFIG_PATH
    old = read_host_value(section, key)
    with LOCK:
        text = update_ini_keys(read_text(target), section, {key: raw})
        write_text(target, text)
        if section != "web-ui" and app is not None:
            applied = apply_host(app)
            if applied.get("error"):
                restore = update_ini_keys(read_text(target), section, {key: old})
                write_text(target, restore)
                apply_host(app)
                return {"ok": False, "error": applied["error"]}
    return {"ok": True}


def host_catalog(config_path: Optional[Path] = None,
                 web_ui_path: Optional[Path] = None,
                 app: Any = None) -> Dict[str, Any]:
    """设置页面的面板和条目；内容只来自插件设置注册表。"""
    host = getattr(app, "plugin_host", None) if app is not None else None
    registry = getattr(host, "settings", None) if host is not None else None
    sections = []
    if registry is not None:
        for panel in registry.panels_in_order():
            fields = []
            for item in registry.items_of(panel.panel_id):
                try:
                    value = item.load() if item.load is not None else item.default
                except Exception as exc:
                    report_error("agent.shell.settings_panel.item_load", exc,
                                 item=item.item_id)
                    value = item.default
                data = item.as_dict()
                data["key"] = item.item_id
                data["value"] = value if value is not None else ""
                data["plugin"] = True
                fields.append(data)
            if fields:
                sections.append({"id": panel.panel_id, "title": panel.title, "fields": fields})
    return {"ok": True, "sections": sections}

def _as_text(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value if value is not None else "").strip()


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
        if hasattr(app, "apply_agent_loop"):
            app.apply_agent_loop(
                image_turns=int(ctx["image_turns"]),
                image_max=int(ctx["image_max"]),
                max_passes=get_max_passes(target))
        elif hasattr(app, "image_turns"):
            app.image_turns = int(ctx["image_turns"])
            app.image_max = int(ctx["image_max"])
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
        return 200, host_catalog(app=app)
    if path == "/api/settings/plugins":
        return 200, list_plugins()
    if path == "/api/settings/plugin-file":
        payload = read_plugin_config(query.get("name", ""))
        return (200 if payload.get("ok") else 400), payload
    return 404, {"ok": False, "error": "not found"}


def handle_post(path: str, body: Dict[str, Any], app: Any) -> Tuple[int, Dict[str, Any]]:
    if path == "/api/settings":
        host = getattr(app, "plugin_host", None) if app is not None else None
        registry = getattr(host, "settings", None) if host is not None else None
        plugin_values = body.get("pluginValues")
        if plugin_values:
            if registry is None:
                return 400, {"ok": False, "error": "插件设置注册表未接入"}
            try:
                registry.save(plugin_values)
            except Exception as exc:
                report_error("agent.shell.settings_panel.plugin_save", exc)
                return 400, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return 200, {"ok": True, "items": {}}
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
