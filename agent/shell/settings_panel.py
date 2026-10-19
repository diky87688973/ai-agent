# -*- coding: utf-8 -*-
"""设置页的读写与生效。

宿主配置按节回显，按键写回原来的 ini，注释行留在原处。
插件是否进入装载候选看 `plugins.ini` 里有没有 `[plugin:<名字>]`。
开关、名字、描述、图标、版本写在插件 `plugin-config.ini` 的 `[base]`。
插件自己的键在同一文件的 `[ext]`。整份当文本编辑。
保存之后更新当前进程里已经拿着的配置，并按清单重新装载插件。
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from agent.capabilities.plugins import plugin_config_fields, resolve_plugin_root
from agent.config import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_PLUGINS_PATH,
    PROJECT_ROOT,
    get_backup_retention_days,
    get_context,
    get_max_passes,
    get_model_reasoning,
    get_plugins,
    get_reasoning_effort,
)
from agent.shell.ini_sections import (
    newline as _newline,
)
from agent.shell.ini_sections import (
    section_span as _section_span,
)
from agent.shell.plugin_editor import build_editor, merge_groups, merge_text
from agent.shell.service_keys import SERVICE_CLASSIC_ADAPTER
from agent.shell.web_ui_config import WEB_UI_CONFIG_PATH, get_web_ui

_LOCK = threading.Lock()
_PLUGINS_DIR = PROJECT_ROOT / "plugins"
_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
_KEY_RE = re.compile(r"^(\s*)([A-Za-z0-9_-]+)(\s*=\s*)(.*)$")

#: 数字字段的下界。缺下界表示任意整数。
_NUMBER_MIN = {
    "max_passes": 1,
    "backup_retention_days": 0,
    "summary_token_threshold": 1,
    "full_user_rounds": 0,
    "summary_output_max_chars": 1,
    "context_window": 1,
    "reasoning_replay_tokens": -1,
}


def _fields() -> List[Dict[str, Any]]:
    """宿主设置的节与控件。值在读取时填，这里只放控件形状。"""
    return [
        {
            "id": "model_reasoning",
            "file": "config.ini",
            "title": "模型",
            "fields": [
                {"key": "api_base_url", "kind": "text", "label": "网关地址"},
                {"key": "api_key", "kind": "secret", "label": "API 密钥"},
                {"key": "model", "kind": "text", "label": "默认模型"},
                {"key": "models", "kind": "text", "label": "可选模型",
                 "hint": "逗号分隔，同一网关下的模型名"},
                {"key": "context_window", "kind": "number", "label": "上下文窗口（token）",
                 "hint": "该模型的物理上限，界面按它算上下文占用率"},
            ],
        },
        {
            "id": "agent",
            "file": "config.ini",
            "title": "Agent",
            "fields": [
                {"key": "reasoning_effort", "kind": "enum", "label": "推理档位",
                 "options": [{"value": "high", "label": "high"},
                             {"value": "max", "label": "max"}]},
                {"key": "max_passes", "kind": "number", "label": "单回合模型往返上限",
                 "hint": "一趟 = 模型回复一次 + 这次回复里的工具调用全部执行完；一趟可含多个工具调用"},
                {"key": "backup_retention_days", "kind": "number",
                 "label": "AI 修改文件时的备份保存天数",
                 "hint": "下次启动时按这个天数清理更早的备份"},
            ],
        },
        {
            "id": "context",
            "file": "config.ini",
            "title": "上下文",
            "fields": [
                {"key": "summary_token_threshold", "kind": "number", "label": "压缩阈值（token）"},
                {"key": "full_user_rounds", "kind": "number", "label": "保留完整用户轮数"},
                {"key": "summary_output_max_chars", "kind": "number", "label": "摘要字数上限"},
                {"key": "reasoning_replay_tokens", "kind": "number", "label": "思维链回传预算",
                 "hint": "-1 全量回传，0 不回传，正数超出后取两头"},
                {"key": "image_turns", "kind": "number", "label": "带图用户轮数",
                 "hint": "最近多少轮用户发言里的图会发给模型；负数表示不剥"},
                {"key": "image_max", "kind": "number", "label": "带图张数上限"},
            ],
        },
        {
            "id": "web-ui",
            "file": "web-ui-config.ini",
            "title": "界面",
            "fields": [
                {"key": "display_tool_items", "kind": "bool", "label": "工作区展示工具步骤"},
                {"key": "display_tool_steps", "kind": "bool", "label": "侧边栏展示工具步骤"},
            ],
        },
    ]


def update_ini_keys(text: str, section: str, updates: Dict[str, str]) -> str:
    """在指定节里改键。已有的键换掉那一行，没有的键补在节尾。其它行不动。"""
    if not updates:
        return text
    pending = {str(key): str(value) for key, value in updates.items()}
    for value in pending.values():
        if "\n" in value or "\r" in value:
            raise ValueError("配置值不能换行")
    lines = text.splitlines(keepends=True)
    nl = _newline(text) if text else "\n"
    span = _section_span(lines, section)
    if span is None:
        block = [f"[{section}]{nl}"]
        for key, value in pending.items():
            block.append(f"{key} = {value}{nl}")
        if text and not text.endswith(("\n", "\r")):
            text += nl
        if text and not text.endswith(nl + nl):
            text += nl
        return text + "".join(block)
    start, end = span
    for index in range(start + 1, end):
        body = lines[index].rstrip("\r\n")
        matched = _KEY_RE.match(body)
        if matched is None:
            continue
        key = matched.group(2)
        found = None
        for want in pending:
            if want.lower() == key.lower():
                found = want
                break
        if found is None:
            continue
        ending = lines[index][len(body):] or nl
        lines[index] = f"{matched.group(1)}{key}{matched.group(3)}{pending.pop(found)}{ending}"
    if pending:
        insert_at = end
        while insert_at > start + 1 and lines[insert_at - 1].strip() == "":
            insert_at -= 1
        extra = [f"{key} = {value}{nl}" for key, value in pending.items()]
        lines[insert_at:insert_at] = extra
    return "".join(lines)


def remove_ini_section(text: str, section: str) -> str:
    """删掉一整个节（节头和节内的键）。注释行不是节头，不会被删。"""
    lines = text.splitlines(keepends=True)
    span = _section_span(lines, section)
    if span is None:
        return text
    start, end = span
    del lines[start:end]
    return "".join(lines)


def append_ini_section(text: str, section: str, items: Iterable[Tuple[str, str]]) -> str:
    """文件末尾加一节。节已经存在时不重复加。"""
    if _section_span(text.splitlines(keepends=True), section) is not None:
        return text
    nl = _newline(text) if text else "\n"
    pairs = list(items)
    for _key, value in pairs:
        if "\n" in value or "\r" in value:
            raise ValueError("配置值不能换行")
    block = f"[{section}]{nl}" + "".join(f"{key} = {value}{nl}" for key, value in pairs)
    if text and not text.endswith(("\n", "\r")):
        text += nl
    if text and not text.endswith(nl + nl):
        text += nl
    return text + block


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8-sig")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=str(path.parent), prefix=".settings-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(name, path)
    except Exception:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise


def _effective_values(config_path: Path, web_ui_path: Path) -> Dict[str, Dict[str, str]]:
    """表单回显用的当前值：文件里有的用文件的，没有的用运行时缺省。"""
    reasoning = get_model_reasoning(config_path)
    ctx = get_context(config_path)
    web = get_web_ui(web_ui_path)
    return {
        "model_reasoning": {
            "api_base_url": str(reasoning["api_base_url"]),
            "api_key": str(reasoning["api_key"]),
            "model": str(reasoning["model"]),
            "models": ",".join(str(item) for item in reasoning["models"]),
            "context_window": str(reasoning["context_window"]),
        },
        "agent": {
            "reasoning_effort": get_reasoning_effort(config_path),
            "max_passes": str(get_max_passes(config_path)),
            "backup_retention_days": str(get_backup_retention_days(config_path)),
        },
        "context": {
            "summary_token_threshold": str(ctx["summary_token_threshold"]),
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
                 web_ui_path: Optional[Path] = None,
                 *,
                 hide_model: bool = False) -> Dict[str, Any]:
    """设置页左侧各节和当前值。

    `hide_model`：模型目录权威时隐藏「模型」节 —— 条目由插件
    `plugin-config.ini` 维护，设置页继续编辑 `config.ini` 只会造成
    "改了却没生效"的错觉。保存接口照常写盘，但 `reload_model_config`
    会忽略模型节并在响应里给出说明。
    """
    config_target = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
    web_target = Path(web_ui_path) if web_ui_path is not None else WEB_UI_CONFIG_PATH
    current = _effective_values(config_target, web_target)
    sections = []
    for spec in _fields():
        if hide_model and spec["id"] == "model_reasoning":
            continue
        fields = []
        for field in spec["fields"]:
            stored = str(current.get(spec["id"], {}).get(field["key"], ""))
            item = {
                "key": field["key"],
                "kind": field["kind"],
                "label": field["label"],
                "value": stored,
                "hint": field.get("hint") or "",
            }
            if field["kind"] == "secret":
                # 回显只说明有没有配过。明文密钥不出接口。
                configured = bool(stored.strip())
                item["value"] = ""
                item["configured"] = configured
                item["placeholder"] = (
                    "已设置秘钥,可重新设置并替换" if configured else "未配置秘钥"
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
    with _LOCK:
        config_text = _read_text(config_target)
        web_text = _read_text(web_target)
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
            _write_text(config_target, config_text)
        if "web-ui-config.ini" in grouped:
            _write_text(web_target, web_text)
        applied = apply_host(app, config_path=config_target) if app is not None else {}
    payload = {"ok": True, "web_ui": get_web_ui(web_target)}
    if applied.get("error"):
        payload["reload_error"] = applied["error"]
    elif applied.get("note"):
        payload["reload_note"] = applied["note"]
    return payload


def apply_host(app: Any, *, config_path: Optional[Path] = None) -> Dict[str, str]:
    """把已经落盘的宿主配置写进当前进程拿着的对象。

    模型相关（网关 / 默认模型 / 可选清单）只能经 `app.reload_model_config()`
    重建，避免设置页和启动路径各改一半。其余启动期抄进对象的副本在这里补：
    推理档位、图片上限、往返上限。
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
                "summary_token_threshold": int(ctx["summary_token_threshold"]),
                "reasoning_replay_tokens": int(ctx["reasoning_replay_tokens"]),
            })
        if hasattr(app, "image_turns"):
            app.image_turns = int(ctx["image_turns"])
        if hasattr(app, "image_max"):
            app.image_max = int(ctx["image_max"])
        if hasattr(app, "max_passes"):
            app.max_passes = get_max_passes(target)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    reload_model_config = getattr(app, "reload_model_config", None)
    if callable(reload_model_config):
        try:
            note = str(reload_model_config(config_path=target) or "").strip()
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}
        if note:
            applied["note"] = note
    return applied



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
        Path(getattr(host, "plugins_dir", _PLUGINS_DIR)) if host is not None else _PLUGINS_DIR
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
    root = Path(plugins_dir) if plugins_dir is not None else _PLUGINS_DIR
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
        declared = meta["version"] or str(listed.get(name, {}).get("version") or "")
        on = name in listed and meta["enable"] != "0"
        cards.append({
            "name": name,
            "title": meta["name"] or name,
            "description": meta["desc"],
            "icon": meta["icon"],
            "enabled": on,
            "version": _version_label(declared),
            "configurable": entry is not None,
        })
    cards.sort(key=lambda item: (not item["enabled"], item["title"]))
    return {"ok": True, "plugins": cards}


def set_plugin_enabled(name: str, enabled: bool, app: Any = None, *,
                       plugins_path: Optional[Path] = None,
                       plugins_dir: Optional[Path] = None) -> Dict[str, Any]:
    """把插件 `[base] enable` 写成 1 或 0，再按它装载或卸下。

    打开时若总清单还没有这一节，补上 `[plugin:<名字>]`。关掉时节留着，只改开关。
    """
    plugin = str(name or "").strip()
    if not _valid_name(plugin):
        return {"ok": False, "error": "插件名不合法"}
    manifest_path = Path(plugins_path) if plugins_path is not None else DEFAULT_PLUGINS_PATH
    root = Path(plugins_dir) if plugins_dir is not None else _PLUGINS_DIR
    folder = _plugin_folder(
        plugin, plugins_dir=root, plugins_path=manifest_path, app=app)
    if enabled and not (folder / "plugin.py").is_file():
        return {"ok": False, "error": "插件目录里没有 plugin.py"}
    with _LOCK:
        text = _read_text(manifest_path)
        section = f"plugin:{plugin}"
        flag = "1" if enabled else "0"
        config_path = folder / "plugin-config.ini"
        cfg = _read_text(config_path)
        if _section_span(cfg.splitlines(keepends=True), "base") is None:
            cfg = append_ini_section(cfg, "base", [("enable", flag)])
        else:
            cfg = update_ini_keys(cfg, "base", {"enable": flag})
        _write_text(config_path, cfg)
        if enabled and _section_span(text.splitlines(keepends=True), section) is None:
            version = plugin_config_fields(folder)["version"] or "1.0"
            text = append_ini_section(text, section, [("version", version)])
            _write_text(manifest_path, text)
        reports = sync_plugins(
            app, plugins_path=manifest_path, plugins_dir=root) if app is not None else []
    return {"ok": True, "reports": reports}


def sync_plugins(app: Any, *, plugins_path: Optional[Path] = None,
                 plugins_dir: Optional[Path] = None) -> List[Dict[str, str]]:
    """卸掉未开启的插件，再装载清单里 `[base] enable` 不是 0 的。"""
    host = getattr(app, "plugin_host", None) if app is not None else None
    if host is None:
        return []
    base = Path(plugins_dir) if plugins_dir is not None else (
        Path(getattr(host, "plugins_dir", _PLUGINS_DIR))
    )
    resolve = getattr(host, "resolve_plugin_root", None)
    desired = []
    for item in get_plugins(plugins_path):
        name = str(item.get("name") or "")
        path_raw = str(item.get("path") or "").strip()
        if callable(resolve):
            folder = resolve(name, path_raw)
        else:
            folder = resolve_plugin_root(base, name, path_raw)
        if plugin_config_fields(folder)["enable"] == "0":
            continue
        desired.append(item)
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
    """读插件配置的编辑视图；文件还不存在时把同目录的 `.example` 当作草稿。

    不落盘：示例里的密钥是占位符，自动写进真实配置会让"打开设置"变成
    一次隐式配置动作。用户改完点保存才创建文件。

    `editor` 只包含插件自己的节：`[base]` 既不回显也不回写。
    """
    plugin = str(name or "").strip()
    if not _valid_name(plugin):
        return {"ok": False, "error": "插件名不合法"}
    root = Path(plugins_dir) if plugins_dir is not None else _PLUGINS_DIR
    try:
        folder = _plugin_folder(
            plugin, plugins_dir=root, plugins_path=plugins_path, app=app)
        path = _config_file(folder)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    exists = path.is_file()
    source = path if exists else path.with_name(path.name + ".example")
    text = _read_text(source) if source.is_file() else ""
    return {
        "ok": True,
        "name": plugin,
        "exists": exists,
        "seeded": (not exists and source.is_file()),
        "editor": build_editor(text, folder),
    }


def write_plugin_config(name: str, text: Any = None, groups: Any = None,
                        app: Any = None, *,
                        plugins_dir: Optional[Path] = None,
                        plugins_path: Optional[Path] = None) -> Dict[str, Any]:
    """只写插件自己的节：`[base]` 与其它节保持原样。

    插件正在装载时卸下再装，让它重新读文件。
    """
    root = Path(plugins_dir) if plugins_dir is not None else _PLUGINS_DIR
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
    else:
        if not isinstance(text, str):
            return {"ok": False, "error": "配置内容要是文本"}
        merged, error = merge_text(base_text, text, editor["sections"])
    if error:
        return {"ok": False, "error": error}
    final = str(merged or "")
    if len(final.encode("utf-8")) > 512 * 1024:
        return {"ok": False, "error": "配置文件过大"}
    with _LOCK:
        _write_text(path, final)
        reports: List[Dict[str, str]] = []
        host = getattr(app, "plugin_host", None) if app is not None else None
        if host is not None and plugin in list(host.loaded_names()):
            host.unload(plugin)
            reports = sync_plugins(app)
    return {"ok": True, "reports": reports}


def _plugin_config_source(path: Path) -> str:
    """真实配置优先；还没有时用同目录模板作底稿（`[base]` 因此能保留）。"""
    if path.is_file():
        return _read_text(path)
    example = path.with_name(path.name + ".example")
    return _read_text(example) if example.is_file() else ""


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
        state = str(getattr(app, "model_config_state", "") or "")
        return 200, host_catalog(hide_model=state == "catalog")
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
            str(body.get("name") or ""), body.get("text"), body.get("groups"), app)
        return (200 if payload.get("ok") else 400), payload
    if path == "/api/settings/pick-dir":
        payload = pick_directory()
        return (200 if payload.get("ok") or payload.get("cancelled") else 400), payload
    return 404, {"ok": False, "error": "not found"}
