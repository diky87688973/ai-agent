# -*- coding: utf-8 -*-
"""片段合并：静态片段 + 各插件片段 → 一棵配置（不构造、不装配）。

片段有两段：`slots` 是自己拥有的插口（path 在本插件可声明范围内），`provides`
是落到别人插口里的贡献（path = 目标插口 + 子级键）。归属由静态片段的 `owners`
授权：键是前缀、值是插件名，命中最长一条。

合并是一次性内存操作，磁盘上是多份片段，运行期只有一份结果。
"""
from __future__ import annotations

import configparser
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Tuple

from agent.core.app_path import APP_ROOT
from agent.core.slot_config import SlotConfig
from agent.core.slot_problems import (
    event_problems,
    order_problems,
    ownership_problems,
    requires_problems,
    spec_problems,
)
from agent.core.slot_spec import (
    CHILDREN_FIXED,
    CHILDREN_KEYED,
    HOST_OWNER,
    SlotConfigError,
    SlotSpec,
    holds_children,
    parent_path,
    parse_spec,
)
from agent.core.slot_spec import label_of as _label_of

#: 片段文件：仓库根是静态片段，各插件目录下是同名动态片段。
FRAGMENT_FILE = "plugin-slots.json"
PLUGIN_DIRNAME = "plugins"
PLUGINS_INI = "plugins.ini"
PLUGIN_SECTION_PREFIX = "plugin:"
#: 插件片段的路径前缀根；`slots` 段的每条 path 必须落在 `<本前缀><目录名>/` 下。
PLUGIN_PATH_ROOT = "app/plugins/"
#: 静态片段的来源标签，用于报错时指出两处来源。
STATIC_FRAGMENT = f"静态片段（仓库根 {FRAGMENT_FILE}）"
#: `provides` 允许的父插口子级策略：`none` 表示不接受贡献。
KEYED_CHILDREN = frozenset({CHILDREN_KEYED, CHILDREN_FIXED})


def _plugins_ini_flags(repo_root: Path) -> Dict[str, bool]:
    """读 `plugins.ini` 的 `[plugin:<名>]` 段；缺 `enabled` 视为启用。"""
    target = repo_root / PLUGINS_INI
    if not target.is_file():
        return {}
    parser = configparser.ConfigParser()
    try:
        parser.read(target, encoding="utf-8")
    except (OSError, configparser.Error) as exc:
        raise SlotConfigError(f"插件清单不可读：{target}") from exc
    flags: Dict[str, bool] = {}
    for section in parser.sections():
        if section.startswith(PLUGIN_SECTION_PREFIX):
            name = section[len(PLUGIN_SECTION_PREFIX):].strip()
            enabled = str(parser.get(section, "enabled", fallback="1")).strip()
            flags[name] = enabled != "0"
    return flags


def _read_fragment(path: Path) -> Dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SlotConfigError(f"片段不可读：{path}") from exc
    if not isinstance(raw, dict):
        raise SlotConfigError(f"片段顶层必须是对象：{path}")
    return raw


def _fragments(repo_root: Path,
               plugins_root: Path, manifest: Any = None, plugin_roots: Any = None) -> List[Tuple[str, str, Dict[str, Any]]]:
    """收集静态片段与全部启用的插件片段，返回 `(origin, owner, 内容)`。

    两个根分开让：`repo_root` 定位静态片段与 `plugins.ini`，`plugins_root` 定位
    插件片段。二者缺省相同（`<仓库根>/plugins`），但可以不同 —— 装配临时目录
    下的插件时，片段从那里来，工厂也从那里解析，不会回到仓库根找。

    `origin` 是声明方：静态片段为 `__host__`，插件片段为插件名。
    它是「实现在谁那里」的机器判据；人读标签由 `_label_of` 现算。
    """
    static_path = repo_root / FRAGMENT_FILE
    if not static_path.is_file():
        raise SlotConfigError(f"静态片段不存在：{static_path}")
    out: List[Tuple[str, str, Dict[str, Any]]] = [
        (HOST_OWNER, "", _read_fragment(static_path))]
    folders = {child.name: child for child in plugins_root.iterdir() if child.is_dir()} if plugins_root.is_dir() else {}
    folders.update({name: Path(path) for name, path in (plugin_roots or {}).items()})
    flags = (_plugins_ini_flags(repo_root) if manifest is None else
             {str(item["name"]): str(item.get("enabled", "1")) != "0"
              for item in manifest})
    for name, child in sorted(folders.items()):
        fragment = child / FRAGMENT_FILE
        if not child.is_dir() or not fragment.is_file():
            continue
        if flags.get(name, True) is False:
            continue
        out.append((name, name, _read_fragment(fragment)))
    return out


def owners_of(raw: Mapping[str, Any]) -> Dict[str, str]:
    """读静态片段的 `owners` 段并校验互斥；键是前缀，值是插件名。"""
    rows = raw.get("owners") or {}
    if not isinstance(rows, Mapping):
        raise SlotConfigError("owners 必须是对象")
    owners: Dict[str, str] = {}
    for prefix, name in rows.items():
        key = str(prefix).strip().strip("/")
        who = str(name or "").strip()
        if not key or not who:
            raise SlotConfigError(f"owners 条目非法：{prefix!r} -> {name!r}")
        owners[key] = who
    problems: List[str] = []
    keys = sorted(owners)
    for i, left in enumerate(keys):
        for right in keys[i + 1:]:
            if right.startswith(left + "/"):
                problems.append(
                    f"归属授权重叠：{left}（{owners[left]}）与 {right}（{owners[right]}）")
    if problems:
        raise SlotConfigError("片段合并冲突：\n - " + "\n - ".join(problems))
    return owners


def owner_of_path(path: str, owners: Mapping[str, str]) -> str:
    """按最长前缀取归属；没有命中授权前缀的归宿主。"""
    best = ""
    for prefix in owners:
        if path == prefix or path.startswith(prefix + "/"):
            if len(prefix) > len(best):
                best = prefix
    return owners[best] if best else HOST_OWNER


def _declarable(path: str, owner: str, owners: Mapping[str, str]) -> bool:
    """`path` 是否在 `owner` 可声明的范围内（自身前缀或授权前缀）。"""
    own_root = f"{PLUGIN_PATH_ROOT}{owner}"
    if path == own_root or path.startswith(own_root + "/"):
        return True
    return owner_of_path(path, owners) == owner


def _collect(fragments: List[Tuple[str, str, Mapping[str, Any]]],
             owners: Mapping[str, str],
             ) -> Tuple[Dict[str, SlotSpec], Dict[str, str],
                        List[str], List[Tuple[str, str, Mapping[str, Any]]],
                        Dict[str, Tuple[str, ...]],
                        List[Dict[str, Any]]]:
    """逐片段收 `slots`，把 `provides` 留到父插口收齐后再校验。

    返回的第二项是 `origins`（path → 声明方的插件名，静态片段为 `__host__`），
    它是「实现在谁那里」的唯一判据；报错文案的人读标签由它现派生。
    最后一项是 `overrides`（覆盖声明）：它们不进 `specs`，只是求值输入。
    """
    specs: Dict[str, SlotSpec] = {}
    origins: Dict[str, str] = {}
    problems: List[str] = []
    pending: List[Tuple[str, str, Mapping[str, Any]]] = []
    subagent: Dict[str, Tuple[str, ...]] = {}
    overrides: List[Dict[str, Any]] = []
    for origin, owner, raw in fragments:
        label = _label_of(origin)
        if "paths" in raw:
            raise SlotConfigError(
                f"paths 段已取消，改为节点字段：把 children / fixed 写在对应节点上"
                f"（来源：{label}）")
        for row in raw.get("slots") or ():
            if isinstance(row, Mapping) and owner and not row.get("owner"):
                row = {**row, "owner": owner}
            spec = parse_spec(row)
            if owner and not _declarable(spec.path, owner, owners):
                problems.append(
                    f"缺少归属授权：{spec.path} 不在 {owner} 的可声明范围内"
                    f"（来源：{label}）")
                continue
            first = origins.get(spec.path)
            if first is not None:
                problems.append(
                    f"路径重复：{spec.path} 同时出现在 {_label_of(first)} 与 {label}")
                continue
            specs[spec.path] = spec
            origins[spec.path] = origin
        for row in raw.get("provides") or ():
            pending.append((origin, owner, row))
        for row in raw.get("overrides") or ():
            if not isinstance(row, Mapping):
                problems.append(f"覆盖声明必须是对象（来源：{label}）")
                continue
            overrides.append(dict(row))
        tools = raw.get("subagent_tools")
        if tools:
            if not isinstance(tools, (list, tuple)):
                problems.append(f"subagent_tools 必须是数组（来源：{label}）")
            else:
                subagent[owner] = tuple(str(x) for x in tools)
    return specs, origins, problems, pending, subagent, overrides


def _apply_provides(pending: List[Tuple[str, str, Mapping[str, Any]]],
                    specs: Mapping[str, SlotSpec],
                    owners: Mapping[str, str],
                    ) -> Tuple[Dict[str, SlotSpec], Dict[str, str], List[str]]:
    """校验 `provides`：父插口须已声明且可填。

    两个轴在这里分家：
      owner  取父插口的归属（卸载/回滚跟父插口走）
      origin 取贡献方插件（实现在谁那里）
    """
    out: Dict[str, SlotSpec] = {}
    origin: Dict[str, str] = {}
    problems: List[str] = []
    for origin_name, _owner, row in pending:
        label = _label_of(origin_name)
        spec = parse_spec({k: v for k, v in row.items() if k != "owner"})
        parent = parent_path(spec.path, APP_ROOT)
        host = specs.get(parent)
        if host is None:
            problems.append(
                f"贡献的父插口未声明：{spec.path} 的父路径 {parent}（来源：{label}）")
            continue
        if host.children not in KEYED_CHILDREN:
            problems.append(
                f"父插口不接受贡献：{parent} 的 children={host.children}"
                f"（来源：{label}）")
            continue
        if host.children == CHILDREN_FIXED:
            tail = spec.path[len(parent) + 1:]
            if tail not in host.fixed:
                problems.append(
                    f"父插口只接受固定子名：{parent} 的 fixed={list(host.fixed)}"
                    f"，收到 {tail}（来源：{label}）")
                continue
        owner = owner_of_path(parent, owners)
        if spec.path in out or spec.path in specs:
            problems.append(f"路径重复：{spec.path} 已被声明的插口占用（来源：{label}）")
            continue
        # 用 replace 而不是手工拼字段：每新增一个字段都要在这里再写一遍，
        # 漏掉就静默丢弃（props / children / fixed 都曾在这里丢过）。
        out[spec.path] = replace(spec, owner=owner)
        origin[spec.path] = origin_name
    return out, origin, problems


def _with_ancestors(specs: Mapping[str, SlotSpec], origins_in: Dict[str, str],
                    root: str,
                    ) -> Tuple[Dict[str, SlotSpec], Dict[str, str],
                               FrozenSet[str], List[str]]:
    """按 path 前缀补齐缺失的容器祖先，返回 (specs, origins, 补齐集, 问题)。

    祖先已存在时不覆盖，但它不能持有子级时是配置错：容器类或 children≠none 才行。
    owner 按层级二分：补齐路径落在 `app/plugins/<本插件名>/` 下才归该插件，
    `app/plugins` 本身与插件前缀之上归宿主 —— 否则先排序的插件会把共用的
    一级容器夺走，卸载时连带释放其他插件的子树。
    补齐的容器 origin 取需要它的最深叶子的 origin：它的存在理由就是那个叶子。
    """
    merged: Dict[str, SlotSpec] = dict(specs)
    origins: Dict[str, str] = dict(origins_in)
    synthesized: set[str] = set()
    problems: List[str] = []
    for path in sorted(specs):
        leaf = specs[path]
        parts = path.split("/")
        for depth in range(len(parts) - 1, 0, -1):
            prefix = "/".join(parts[:depth])
            if prefix == root:
                continue
            known = merged.get(prefix)
            if known is not None:
                if not holds_children(known):
                    problems.append(
                        f"祖先不能持有子级：{path} 需要 {prefix} 作为父插口，但它被声明为 "
                        f"kind={known.kind} 且 children=none"
                        f"（来源：{_label_of(origins.get(prefix, HOST_OWNER))}）")
                continue
            own_root = f"{PLUGIN_PATH_ROOT}{leaf.owner}"
            mine = prefix == own_root or prefix.startswith(own_root + "/")
            owner = leaf.owner if mine else HOST_OWNER
            merged[prefix] = SlotSpec(path=prefix, kind="container", owner=owner)
            origins[prefix] = origins.get(path, HOST_OWNER)
            synthesized.add(prefix)
    return merged, origins, frozenset(synthesized), problems


def _frozen_overrides(specs: Mapping[str, SlotSpec],
                      origins: Mapping[str, str]) -> List[str]:
    """冻结节点及其子树不得被其他片段添加或改写。"""
    frozen = {path: origins.get(path, HOST_OWNER) for path, spec in specs.items()
              if spec.frozen}
    problems: List[str] = []
    for path in sorted(specs):
        for base, holder in frozen.items():
            if path != base and not path.startswith(base + "/"):
                continue
            own = origins.get(path, HOST_OWNER)
            if own != holder:
                problems.append(
                    f"冻结节点被覆盖：{base}（来源：{_label_of(holder)}）"
                    f"拒绝 {path}（来源：{_label_of(own)}）")
            break
    return problems


def load_merged(repo_root: Path,
                plugins_root: Optional[Path] = None, *, manifest: Any = None,
                plugin_roots: Any = None) -> SlotConfig:
    """读静态片段 + 扫插件根收动态片段 → 校验冲突 → 合并成一份配置。

    只做配置合并，不构造、不装配。冲突一律报错并指出两处来源。
    合并过程中以 `origins`（path → 声明方插件名）为唯一事实，
    报错文案用的 `sources` 由它现派生。

    `plugins_root` 缺省为 `<repo_root>/plugins`；显式传入时片段从那里收集，
    并写进 `SlotConfig.plugins_root` —— 同一个值也是装配期解析插件 factory 的根，
    片段来源与工厂解析根因此只有一份事实。
    """
    root = Path(repo_root)
    plugins = Path(plugins_root) if plugins_root is not None else root / PLUGIN_DIRNAME
    fragments = _fragments(root, plugins, manifest, plugin_roots)
    owners = owners_of(fragments[0][2])
    specs, origins, problems, pending, subagent, overrides = _collect(fragments, owners)
    origin_root = str(fragments[0][2].get("root") or APP_ROOT)
    specs, origins, synthesized, gaps = _with_ancestors(specs, origins, origin_root)
    problems.extend(gaps)
    active = set(origins.values())
    pending = [item for item in pending
               if owner_of_path(parent_path(str(item[2].get("path", "")), APP_ROOT), owners)
               in active | {HOST_OWNER}]
    provided, contributed, gaps = _apply_provides(pending, specs, owners)
    problems.extend(gaps)
    specs.update(provided)
    origins.update(contributed)
    config = SlotConfig(
        root=origin_root, version=int(fragments[0][2].get("version") or 1),
        specs=specs, origins=origins,
        synthesized=synthesized, subagent_tools=subagent,
        plugins_root=plugins, overrides=tuple(overrides),
        plugin_roots={name: Path((plugin_roots or {}).get(name, plugins / name))
                      for name, _, _ in fragments if name != HOST_OWNER})
    # 合并出来的配置同样是配置：节点级判据（factory 有无与形状、能否持有子级、
    # 事件名、root 前缀）必须对成品再跑一遍 —— 绕开 `SlotConfig.parse` 不等于绕开校验。
    labels = config.sources
    problems.extend(spec_problems(config.specs, config.root))
    problems.extend(event_problems(config.specs))
    problems.extend(ownership_problems(config.specs, config.origins))
    problems.extend(requires_problems(config.specs, labels, synthesized))
    problems.extend(order_problems(config.specs, config.root, labels, synthesized))
    problems.extend(_frozen_overrides(specs, origins))
    if problems:
        raise SlotConfigError("片段合并冲突：\n - " + "\n - ".join(problems))
    return config
