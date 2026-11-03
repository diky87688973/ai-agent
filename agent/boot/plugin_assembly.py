# -*- coding: utf-8 -*-
"""插件目录内的启动期装配声明。

插件在其目录放 `plugin-assembly.json` 即可在启动时覆盖应用装配节点：
节点路径、factory、metadata 与 requires 都来自插件目录，不需要改
`agent/boot/slot_tree.json`。声明存在即自动装载该插件；清单里的
`enabled = 0` 仍然优先。
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Iterable, List, Tuple

_PACKAGE = "dsh_plugin_assembly"
_PLUGIN_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


class PluginAssemblyError(RuntimeError):
    """插件装配声明无效或 factory 无法加载。"""


@dataclass(frozen=True)
class AssemblyOverlay:
    """自动装载清单与启动期节点覆盖。"""

    manifest: List[Dict[str, str]]
    nodes: Tuple[Dict[str, Any], ...]


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


def _package(name: str, path: Path) -> None:
    module = sys.modules.get(name)
    if module is None:
        module = ModuleType(name)
        module.__path__ = [str(path)]  # type: ignore[attr-defined]
        sys.modules[name] = module
        return
    if not getattr(module, "__path__", None):
        module.__path__ = [str(path)]  # type: ignore[attr-defined]


def _factory(root: Path, name: str, spec: str) -> str:
    module_name, sep, attr = str(spec or "").partition(":")
    if not sep or not module_name or not attr:
        raise PluginAssemblyError(f"factory 必须是 module:attr：{spec!r}")
    if module_name.startswith(("agent.", "dsh_plugin_assembly.")):
        return spec
    relative = module_name.replace(".", "/") + ".py"
    target = (root / relative).resolve()
    try:
        target.relative_to(root.resolve())
    except (OSError, ValueError) as exc:
        raise PluginAssemblyError(f"factory 越出插件目录：{module_name}") from exc
    if not target.is_file():
        raise PluginAssemblyError(f"factory 模块不存在：{module_name}")
    package_name = f"{_PACKAGE}.{name.replace('-', '_')}"
    _package(_PACKAGE, root.parent)
    _package(package_name, root)
    module_path = f"{package_name}.{module_name.replace('.', '_')}"
    module_spec = importlib.util.spec_from_file_location(module_path, target)
    if module_spec is None or module_spec.loader is None:
        raise PluginAssemblyError(f"无法加载 factory 模块：{module_name}")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_path] = module
    try:
        module_spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_path, None)
        raise PluginAssemblyError(
            f"factory 模块执行失败：{module_name}：{type(exc).__name__}: {exc}"
        ) from exc
    if not callable(getattr(module, attr, None)):
        raise PluginAssemblyError(f"factory 属性不可调用：{module_name}:{attr}")
    return f"{module_path}:{attr}"


def _nodes(root: Path, name: str) -> List[Dict[str, Any]]:
    path = root / "plugin-assembly.json"
    raw = _json(path)
    kind = str(raw.get("kind") or "").strip()
    if kind and kind != "assembly":
        raise PluginAssemblyError(f"plugin-assembly.json 的 kind 必须是 assembly：{path}")
    rows = raw.get("nodes")
    if not isinstance(rows, list):
        raise PluginAssemblyError(f"plugin-assembly.json 缺少 nodes 列表：{path}")
    nodes: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise PluginAssemblyError(f"装配节点必须是对象：{path}")
        node = dict(row)
        node_path = str(node.get("path") or "").strip()
        if not node_path:
            raise PluginAssemblyError(f"装配节点缺少 path：{path}")
        factory = str(node.get("factory") or "").strip()
        if factory:
            node["factory"] = _factory(root, name, factory)
        elif "metadata" not in node and "requires" not in node:
            raise PluginAssemblyError(f"装配节点缺少 factory 或 metadata：{node_path}")
        node["path"] = node_path
        nodes.append(node)
    return nodes


def discover(plugins_dir: Path, manifest: Iterable[Any]) -> AssemblyOverlay:
    """扫描插件目录，返回自动装载清单与启动期节点覆盖。

    只有带 `plugin-assembly.json` 或 `plugin-meta.json` 中
    `auto_load` 为真的插件才自动进入清单；其余插件沿用原清单规则。
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
        entries.append(item)
        by_name[name] = item
    if not base.is_dir():
        return AssemblyOverlay(entries, ())

    nodes: List[Dict[str, Any]] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir() or child.name.startswith(("_", ".")):
            continue
        assembly = child / "plugin-assembly.json"
        meta = child / "plugin-meta.json"
        try:
            meta_data = _json(meta) if meta.is_file() else {}
        except PluginAssemblyError:
            meta_data = {}
        auto = assembly.is_file() or _truthy(meta_data.get("auto_load"))
        if not auto:
            continue
        name = _name(child.name)
        if name in by_name and _disabled(by_name[name]):
            continue
        if assembly.is_file():
            nodes.extend(_nodes(child, name))
        if (child / "plugin.py").is_file() and name not in by_name:
            item = {"name": name}
            entries.append(item)
            by_name[name] = item
    return AssemblyOverlay(entries, tuple(nodes))


__all__ = ["AssemblyOverlay", "PluginAssemblyError", "discover"]
