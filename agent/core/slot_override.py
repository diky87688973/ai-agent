# -*- coding: utf-8 -*-
"""覆盖求值：绑定链、冻结子树与有效视图。

覆盖只换实现，不换形状、不改结构、不产生节点；求值结果是一份只含有效路径的
新配置，覆盖本体求值后即丢弃，不留第二本账。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

from agent.core.slot_config import SlotConfig
from agent.core.slot_problems import validate_problems
from agent.core.slot_spec import (
    BASE_MODE,
    HOST_OWNER,
    MODES,
    OVERRIDE_FIELDS,
    STRUCTURAL_FIELDS,
    SlotConfigError,
    SlotSpec,
    parse_spec,
    sort_key,
)


@dataclass(frozen=True)
class SlotBinding:
    """某个路径上的一份实现；`mode` 决定它与默认实现的关系。"""

    spec: SlotSpec
    mode: str


@dataclass(frozen=True)
class ResolvedBindings:
    """按路径解析出的绑定链。

    `disabled`：禁用路径已含其全部子路径（整棵不可用）。
    `hidden`：`replace_subtree` 的旧后代 —— 主插口换了，子孙跟随失效，
    但它们不算「被禁用」，只是不再属于这棵树。
    """

    chains: Mapping[str, Tuple[SlotBinding, ...]]
    disabled: FrozenSet[str] = frozenset()
    hidden: FrozenSet[str] = frozenset()

    def chain(self, path: str) -> Tuple[SlotBinding, ...]:
        return tuple(self.chains.get(path, ()))


def _mode_of(row: Mapping[str, Any], path: str) -> str:
    mode = str(row.get("mode") or "replace").strip()
    if mode not in MODES:
        raise SlotConfigError(f"mode 非法：{path} / {mode}")
    return mode


def frozen_paths(config: "SlotConfig") -> FrozenSet[str]:
    """冻结节点自身及其全部后代。

    冻结是子树属性，不是单点属性：只冻父不冻子等于形同虚设。
    """
    frozen = {path for path, spec in config.specs.items() if spec.frozen}
    out: set[str] = set()
    for path in config.specs:
        for base in frozen:
            if path == base or path.startswith(base + "/"):
                out.add(path)
                break
    return frozenset(out)


def _check_structural(row: Mapping[str, Any], path: str, base: SlotSpec) -> None:
    """覆盖不得改形状：结构字段出现即拒，并指明要走下一轮快照。"""
    for key in STRUCTURAL_FIELDS:
        if key in row and row[key] != getattr(base, key):
            raise SlotConfigError(
                f"覆盖不得修改结构字段：{path} 的 {key}"
                f"（当前为 {getattr(base, key)!r}，覆盖写作 {row[key]!r}；"
                f"该字段属于结构变更，须走下一轮快照）")


def resolve_bindings(config: SlotConfig,
                     overrides: Sequence[Mapping[str, Any]]) -> ResolvedBindings:
    """把覆盖声明解析成每个路径的绑定链，并判定模式与边界冲突。

    三条边界在这里就挡下，装配主干不靠调用方自觉：
      冻结子树内的任何覆盖都拒（冻结是子树属性）
      覆盖不得修改结构字段（换实现不等于换形状）
      覆盖不得声明后代（覆盖只换实现，不产生节点）
    """
    frozen = frozen_paths(config)
    grouped: Dict[str, List[Tuple[SlotSpec, str]]] = {}
    for row in overrides:
        if not isinstance(row, Mapping):
            raise SlotConfigError("覆盖声明必须是对象")
        raw_path = str(row.get("path") or "").strip().strip("/")
        base = config.specs.get(raw_path)
        if base is None:
            raise SlotConfigError(f"覆盖指向不存在的路径：{raw_path}")
        if raw_path in frozen:
            raise SlotConfigError(f"冻结节点不可覆盖：{raw_path}（frozen）")
        _check_structural(row, raw_path, base)
        spec = parse_spec(row, base, OVERRIDE_FIELDS)
        grouped.setdefault(raw_path, []).append((spec, _mode_of(row, raw_path)))
    _check_no_descendants(grouped)
    chains: Dict[str, Tuple[SlotBinding, ...]] = {}
    disabled: set[str] = set()
    swapped: set[str] = set()
    for path, base in config.specs.items():
        items = grouped.get(path, [])
        modes = [mode for _spec, mode in items]
        _check_modes(path, modes)
        if "disable" in modes:
            chains[path] = ()
            disabled.add(path)
            continue
        winner = next((spec for spec, mode in items
                       if mode in ("replace", "replace_subtree")), None)
        if winner is not None:
            mode = next(mode for spec, mode in items if spec is winner)
            chains[path] = (SlotBinding(winner, mode),)
            if mode == "replace_subtree":
                swapped.add(path)
            continue
        chain = [SlotBinding(base, BASE_MODE)]
        for spec, mode in sorted(items, key=lambda item: sort_key(item[0])):
            chain.append(SlotBinding(spec, mode))
        chains[path] = tuple(chain)
    for path in list(disabled):
        prefix = path + "/"
        disabled.update(item for item in config.specs if item.startswith(prefix))
    # 整棵替换：旧后代跟随失效（不从旧实现里“接着用”），但不等于禁用本节点
    hidden = {item for path in swapped for item in config.specs
              if item != path and item.startswith(path + "/")}
    return ResolvedBindings(chains=chains, disabled=frozenset(disabled),
                            hidden=frozenset(hidden))


def _check_no_descendants(
        grouped: Mapping[str, Sequence[Tuple[SlotSpec, str]]]) -> None:
    """覆盖不得声明后代：被整棵换掉或禁用的子树下，不许再出现覆盖。

    覆盖只换实现，不产生节点；在已被换掉的子树下再写一条覆盖，
    等于把覆盖当声明用 —— 那段声明会石沉大海。
    """
    roots = [path for path, items in grouped.items()
             if any(mode in ("replace_subtree", "disable")
                    for _spec, mode in items)]
    for root in roots:
        prefix = root + "/"
        for path in grouped:
            if path != root and path.startswith(prefix):
                raise SlotConfigError(
                    f"覆盖不得声明后代：{path}（其祖先 {root} 已被整棵替换或禁用）")


def effective_view(config: SlotConfig,
                   overrides: Optional[Sequence[Mapping[str, Any]]] = None,
                   ) -> SlotConfig:
    """声明 + 覆盖 求值出有效视图；覆盖求值后即丢弃。

    返回值仍是一棵 `SlotConfig`，所以 `children` / `topo_order` / 绑定器都能直接用；
    但它只含有效路径：`replace_subtree` 与 `disable` 的旧后代不在里面，
    也就不会被构造。覆盖本体不写回（`overrides=()`），不存在第二本账。
    """
    rows = tuple(config.overrides if overrides is None else overrides)
    if not rows:
        return config
    bindings = resolve_bindings(config, rows)
    specs: Dict[str, SlotSpec] = {}
    origins = dict(config.origins)
    if overrides is None:
        for row, origin in zip(rows, config.override_origins):
            path = str(row.get("path") or "").strip().strip("/")
            if (origin != HOST_OWNER and config.spec(path).kind.startswith("ui-")
                    and _mode_of(row, path) in ("replace", "replace_subtree")):
                origins[path] = origin
    for path in config.paths():
        # 两种失效都不进视图：整棵禁用，与主插口换了之后的旧后代。
        if path in bindings.hidden or path in bindings.disabled:
            continue
        chain = bindings.chain(path)
        if not chain:
            continue
        winner = next((item for item in chain
                       if item.mode in ("replace", "replace_subtree")), None)
        if winner is not None:
            specs[path] = winner.spec
            continue
        if len(chain) > 1:
            raise SlotConfigError(
                f"该组合在装配期无法表达：{path} 的 mode 为 "
                f"{'、'.join(item.mode for item in chain[1:])}"
                "（当前有效视图只支持 replace / replace_subtree / disable）")
        specs[path] = chain[0].spec
    view = SlotConfig(
        root=config.root, version=config.version, specs=specs,
        origins={path: origin for path, origin in origins.items()
                 if path in specs},
        synthesized=frozenset(path for path in config.synthesized if path in specs),
        subagent_tools=config.subagent_tools, plugins_root=config.plugins_root,
        plugin_roots=config.plugin_roots)
    problems = validate_problems(view.specs, view.root, view.origins)
    if problems:
        raise SlotConfigError("有效视图校验未通过：\n - " + "\n - ".join(problems))
    return view


def _check_modes(path: str, modes: Sequence[str]) -> None:
    for exclusive in ("replace", "replace_subtree"):
        if modes.count(exclusive) > 1:
            raise SlotConfigError(f"同一路径出现多个 {exclusive}：{path}")
    if "replace" in modes and "replace_subtree" in modes:
        raise SlotConfigError(f"replace 与 replace_subtree 并存：{path}")
    if "disable" in modes and len(modes) > 1:
        raise SlotConfigError(f"disable 与其他模式并存：{path}")
