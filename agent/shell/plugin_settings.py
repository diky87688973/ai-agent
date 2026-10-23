# -*- coding: utf-8 -*-
"""插件设置：清单开关、目录解析、插件配置读写与重装。

插件是否进入装载候选看 `plugins.ini` 里有没有 `[plugin:<名字>]`。
开关在 `plugins.ini`，名字、描述、图标、版本在 `plugin-meta.json`。
插件自己的键在同一配置文件的 `[config]`，整份当文本编辑。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.capabilities.plugins import plugin_config_fields, resolve_plugin_root
from agent.config import DEFAULT_PLUGINS_PATH, get_plugins
from agent.shell.ini_sections import section_span
from agent.shell.plugin_editor import build_editor, merge_fields, merge_groups, merge_text
from agent.shell.service_keys import SERVICE_CLASSIC_ADAPTER
from agent.shell.settings_io import (
    LOCK,
    PLUGINS_DIR,
    append_ini_section,
    read_text,
    update_ini_keys,
    write_text,
)

_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def _valid_name(name: str) -> bool:
    return bool(_NAME_RE.fullmatch(str(name or "")))


def _version_label(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if text[0] in "vV":
        return "v" + text[1:]
    return "v" + text


def _plugin_folder(
    name: str,
    *,
    plugins_dir: Optional[Path] = None,
    plugins_path: Optional[Path] = None,
    app: Any = None,
) -> Path:
    """解析某插件目录：优先已装载的 plugin_root，否则与 PluginHost 同一套 path 解析。"""
    plugin = str(name or "").strip()
    host = getattr(app, "plugin_host", None) if app is not None else None
    if host is not None:
        lookup = getattr(host, "plugin_root", None)
        if callable(lookup):
            tracked = lookup(plugin)
            if tracked is not None:
                return Path(tracked)
    base = Path(plugins_dir) if plugins_dir is not None else (
        Path(getattr(host, "plugins_dir", PLUGINS_DIR)) if host is not None else PLUGINS_DIR
    )
    path_raw = ""
    manifest = Path(plugins_path) if plugins_path is not None else DEFAULT_PLUGINS_PATH
    for item in get_plugins(manifest):
        if str(item.get("name") or "") == plugin:
            path_raw = str(item.get("path") or "").strip()
            break
    resolve = getattr(host, "resolve_plugin_root", None) if host is not None else None
    if callable(resolve):
        return resolve(plugin, path_raw)
    return resolve_plugin_root(base, plugin, path_raw)


def list_plugins(plugins_path: Optional[Path] = None,
                 plugins_dir: Optional[Path] = None,
                 app: Any = None) -> Dict[str, Any]:
    """插件卡片：目录里有入口的都列出，清单里有但目录没了的也列出以便关掉。"""
    manifest_path = Path(plugins_path) if plugins_path is not None else DEFAULT_PLUGINS_PATH
    root = Path(plugins_dir) if plugins_dir is not None else PLUGINS_DIR
    listed = {str(item["name"]): item for item in get_plugins(manifest_path)}
    found: Dict[str, Path] = {}
    if root.is_dir():
        for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
            if not child.is_dir() or child.name.startswith((".", "_")):
                continue
            entry = child / "plugin.py"
            if entry.is_file() and _valid_name(child.name):
                found[child.name] = entry
    for name, _item in listed.items():
        if name in found or not _valid_name(name):
            continue
        folder = _plugin_folder(
            name, plugins_dir=root, plugins_path=manifest_path, app=app)
        entry = folder / "plugin.py"
        if entry.is_file():
            found[name] = entry
    names = list(found)
    for name in sorted(listed):
        if name not in found and _valid_name(name):
            names.append(name)
    cards = []
    for name in names:
        entry = found.get(name)
        meta = plugin_config_fields(entry.parent) if entry is not None else {
            "name": "", "desc": "", "enable": "0", "icon": "", "version": "",
        }
        declared = meta["version"]
        on = (name in listed
              and str(listed[name].get("enabled", "1")) != "0")
        cards.append({
            "name": name,
            "title": meta["name"] or name,
            "description": meta["desc"],
            "icon": meta["icon"],
            "enabled": on,
            "version": _version_label(declared),
            "configurable": entry is not None and str(meta.get("config", "1")) != "0",
            "settings_tab": str(meta.get("settings_tab") or ""),
        })
    cards.sort(key=lambda item: (not item["enabled"], item["title"]))
    return {"ok": True, "plugins": cards}


def set_plugin_enabled(name: str, enabled: bool, app: Any = None, *,
                       plugins_path: Optional[Path] = None,
                       plugins_dir: Optional[Path] = None) -> Dict[str, Any]:
    """把插件清单节的 `enabled` 写成 1 或 0，再按它装载或卸下。"""
    plugin = str(name or "").strip()
    if not _valid_name(plugin):
        return {"ok": False, "error": "插件名不合法"}
    manifest_path = Path(plugins_path) if plugins_path is not None else DEFAULT_PLUGINS_PATH
    root = Path(plugins_dir) if plugins_dir is not None else PLUGINS_DIR
    folder = _plugin_folder(
        plugin, plugins_dir=root, plugins_path=manifest_path, app=app)
    if enabled and not (folder / "plugin.py").is_file():
        return {"ok": False, "error": "插件目录里没有 plugin.py"}
    with LOCK:
        text = read_text(manifest_path)
        section = f"plugin:{plugin}"
        flag = "1" if enabled else "0"
        if section_span(text.splitlines(keepends=True), section) is None:
            if enabled:
                text = append_ini_section(text, section, [("enabled", flag)])
                write_text(manifest_path, text)
        else:
            write_text(
                manifest_path, update_ini_keys(text, section, {"enabled": flag}))
        reports = sync_plugins(
            app, plugins_path=manifest_path, plugins_dir=root) if app is not None else []
    return {"ok": True, "reports": reports}


def sync_plugins(app: Any, *, plugins_path: Optional[Path] = None,
                 plugins_dir: Optional[Path] = None) -> List[Dict[str, str]]:
    """卸掉未开启的插件，再装载清单里 `enabled` 不是 0 的。"""
    host = getattr(app, "plugin_host", None) if app is not None else None
    if host is None:
        return []
    desired = [
        item for item in get_plugins(plugins_path)
        if str(item.get("enabled", "1")) != "0"
    ]
    wanted = {str(item["name"]) for item in desired}
    for name in list(host.loaded_names()):
        if name not in wanted:
            host.unload(name)
    reports = []
    for report in host.load_manifest(desired):
        reports.append({
            "name": str(report.name),
            "status": str(report.status),
            "message": str(report.message or ""),
        })
    # 目录贡献随插件装卸而来去；不重算权威，停用后路由仍指着已注销的条目。
    refresh = getattr(app, "refresh_model_config", None)
    if callable(refresh):
        note = str(refresh() or "")
        if note:
            reports.append({"name": "", "status": "note", "message": note})
    _announce_plugins(app, host.loaded_names())
    return reports


def _announce_plugins(app: Any, loaded: List[str]) -> None:
    """把已装载插件名推进经典界面的事件流。没有适配层时不发。"""
    context = getattr(app, "context", None)
    has = getattr(context, "has", None)
    if context is None or not callable(has) or not has(SERVICE_CLASSIC_ADAPTER):
        return
    classic = context.get(SERVICE_CLASSIC_ADAPTER)
    announce = getattr(classic, "announce_plugins", None)
    if callable(announce):
        announce(loaded)


def _config_file(plugin_root: Path) -> Path:
    root = Path(plugin_root).resolve()
    if not (root / "plugin.py").is_file():
        raise ValueError("插件目录里没有 plugin.py")
    return root / "plugin-config.ini"


def read_plugin_config(name: str, *, plugins_dir: Optional[Path] = None,
                       plugins_path: Optional[Path] = None,
                       app: Any = None) -> Dict[str, Any]:
    """读插件配置的编辑视图；真实文件不存在时返回空表单。

    `editor` 只包含插件自己的节；身份与开关不在插件配置里。
    """
    plugin = str(name or "").strip()
    if not _valid_name(plugin):
        return {"ok": False, "error": "插件名不合法"}
    root = Path(plugins_dir) if plugins_dir is not None else PLUGINS_DIR
    try:
        folder = _plugin_folder(
            plugin, plugins_dir=root, plugins_path=plugins_path, app=app)
        path = _config_file(folder)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    exists = path.is_file()
    text = read_text(path) if exists else ""
    return {
        "ok": True,
        "name": plugin,
        "exists": exists,
        "editor": build_editor(text, folder),
    }


def write_plugin_config(name: str, text: Any = None, groups: Any = None,
                        fields: Any = None,
                        app: Any = None, *,
                        plugins_dir: Optional[Path] = None,
                        plugins_path: Optional[Path] = None) -> Dict[str, Any]:
    """只写插件自己的节；身份与开关不在插件配置里。

    插件正在装载时卸下再装，让它重新读文件。
    """
    root = Path(plugins_dir) if plugins_dir is not None else PLUGINS_DIR
    plugin = str(name or "").strip()
    if not _valid_name(plugin):
        return {"ok": False, "error": "插件名不合法"}
    try:
        folder = _plugin_folder(
            plugin, plugins_dir=root, plugins_path=plugins_path, app=app)
        path = _config_file(folder)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    base_text = _plugin_config_source(path)
    editor = build_editor(base_text, folder)
    if editor["kind"] == "sections":
        if not isinstance(groups, list):
            return {"ok": False, "error": "这份配置要用表单提交"}
        merged, error = merge_groups(base_text, groups, editor["schema"])
    elif editor["kind"] == "fields":
        if not isinstance(fields, dict):
            return {"ok": False, "error": "这份配置要用字段表单提交"}
        merged, error = merge_fields(base_text, fields, editor["schema"])
    else:
        if not isinstance(text, str):
            return {"ok": False, "error": "配置内容要是文本"}
        merged, error = merge_text(base_text, text, editor["sections"])
    if error:
        return {"ok": False, "error": error}
    final = str(merged or "")
    if len(final.encode("utf-8")) > 512 * 1024:
        return {"ok": False, "error": "配置文件过大"}
    with LOCK:
        write_text(path, final)
        reports: List[Dict[str, str]] = []
        host = getattr(app, "plugin_host", None) if app is not None else None
        if host is not None and plugin in list(host.loaded_names()):
            host.unload(plugin)
            reports = sync_plugins(app)
    return {"ok": True, "reports": reports}


def _plugin_config_source(path: Path) -> str:
    """只读真实插件配置；文件不存在时从空文本开始生成。"""
    return read_text(path) if path.is_file() else ""
