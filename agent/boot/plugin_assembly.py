# -*- coding: utf-8 -*-
"""插件自动装载清单：扫描插件目录，找出应当自动装载的插件。

默认清单扫描 `plugin-slots.json`、装配标记和元数据的 `auto_load`。
显式自定义清单限制未列出插件；清单里的禁用标记优先。

装配覆盖不在这里：节点怎么装配由 `plugin-slots.json` 片段与装配器决定，
本模块只回答「哪些插件要装」。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from agent.capabilities.plugins import resolve_plugin_root

_PLUGIN_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


class PluginAssemblyError(RuntimeError):
    """插件自动装载声明无效。"""


@dataclass(frozen=True)
class AssemblyOverlay:
    """自动装载清单。"""

    manifest: List[Dict[str, str]]


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _name(value: Any) -> str:
    text = str(value or "").strip()
    if not _PLUGIN_NAME.fullmatch(text):
        raise PluginAssemblyError(f"插件名非法：{value!r}")
    return text


def _json(path: Path) -> Dict[str, Any]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise PluginAssemblyError(f"读取失败：{path}：{exc}") from exc
    if not isinstance(raw, dict):
        raise PluginAssemblyError(f"JSON 顶层必须是对象：{path}")
    return raw


def _disabled(entry: Dict[str, Any]) -> bool:
    return str(entry.get("enabled", "1") or "1").strip() == "0"


def discover(plugins_dir: Path, manifest: Iterable[Any], *,
             include_unlisted: bool = True) -> AssemblyOverlay:
    """扫描插件目录，返回自动装载清单。

    默认剖面接受片段或自动装载标记，自定义剖面按显式清单限制片段发现。
    """
    base = Path(plugins_dir).resolve()
    entries: List[Dict[str, str]] = []
    by_name: Dict[str, Dict[str, str]] = {}
    for entry in manifest or ():
        raw = entry if isinstance(entry, dict) else {"name": entry}
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        item = {"name": name}
        if "path" in raw:
            item["path"] = str(raw.get("path") or "")
        if "enabled" in raw:
            item["enabled"] = str(raw.get("enabled") or "1")
        if not resolve_plugin_root(base, name, item.get("path", "")).exists():
            continue
        entries.append(item)
        by_name[name] = item
    if not base.is_dir():
        return AssemblyOverlay(entries)

    for child in sorted(base.iterdir()):
        if not child.is_dir() or child.name.startswith(("_", ".")):
            continue
        meta = child / "plugin-meta.json"
        try:
            meta_data = _json(meta) if meta.is_file() else {}
        except PluginAssemblyError:
            meta_data = {}
        if (not include_unlisted and child.name not in by_name
                and not _truthy(meta_data.get("auto_load"))):
            entries.append({"name": child.name, "enabled": "0"})
            continue
        auto = ((child / "plugin-slots.json").is_file()
                or _truthy(meta_data.get("auto_load")))
        if not auto:
            continue
        name = _name(child.name)
        if name in by_name and _disabled(by_name[name]):
            continue
        if meta.is_file() and name not in by_name:
            item = {"name": name}
            entries.append(item)
            by_name[name] = item
    return AssemblyOverlay(entries)


__all__ = ["AssemblyOverlay", "PluginAssemblyError", "discover"]
