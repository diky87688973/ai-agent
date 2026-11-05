# -*- coding: utf-8 -*-
"""配置容器：节点表、来源轴、读取与拓扑序。

`SlotConfig` 是装配与覆盖共同的输入形状；`load_config` 读一份片段文件，
`topo_order` 给出构造顺序（子先于父，成环即报错）。
"""
from __future__ import annotations

import heapq
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Tuple

from agent.core.app_path import APP_ROOT
from agent.core.slot_problems import validate_problems
from agent.core.slot_spec import (
    HOST_OWNER,
    SlotConfigError,
    SlotSpec,
    label_of,
    parse_spec,
    sort_key,
)


def _validate(config: "SlotConfig") -> None:
    for message in validate_problems(config.specs, config.root, config.origins):
        raise SlotConfigError(message)


@dataclass(frozen=True)
class SlotConfig:
    """一份完整配置：装配节点。

    两个归属轴：
      `owner`   卸载与回滚归属；`provides` 节点跟父插口走
      `origins` 实现归属；`provides` 节点跟贡献方走，静态片段为 `__host__`
    「实现在谁那里」只由 `origins` 说，不从路径或 owner 推。

    `sources` 是 `origins` 的派生视图（人读标签，只用于报错），不单独存一份事实。
    `synthesized` 是加载器补齐的祖先容器路径集合；它们也在 `origins` 里，
    标签取自需要它的最深叶子，故需另外记一份供报错标注。
    `subagent_tools` 是各插件声明的子智能体可见工具清单，不建成节点。
    `plugins_root` 是插件片段所在目录；它同时是装配期解析插件 factory 的根。
    单片段解析（`parse`）没有仓库上下文，故为 None，此时解析插件 factory 报错。
    """

    root: str = APP_ROOT
    version: int = 1
    specs: Mapping[str, SlotSpec] = field(default_factory=dict)
    origins: Mapping[str, str] = field(default_factory=dict)
    synthesized: FrozenSet[str] = frozenset()
    subagent_tools: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)
    plugins_root: Optional[Path] = None
    plugin_roots: Mapping[str, Path] = field(default_factory=dict)
    #: 覆盖声明（声明层的输入，不参与构造）：求值后进有效视图，本体即丢弃。
    overrides: Tuple[Mapping[str, Any], ...] = ()

    @property
    def sources(self) -> Mapping[str, str]:
        """人读来源标签，由 `origins` 现算；只用于报错文案。"""
        return MappingProxyType({path: label_of(origin)
                                 for path, origin in self.origins.items()})

    def origin_of(self, path: str) -> str:
        """声明方：插件名或 `__host__`；未登记的路径视为宿主。"""
        return self.origins.get(path, HOST_OWNER)

    @classmethod
    def parse(cls, raw: Any) -> "SlotConfig":
        if not isinstance(raw, Mapping):
            raise SlotConfigError("配置顶层必须是对象")
        if "paths" in raw:
            raise SlotConfigError(
                "paths 段已取消，改为节点字段：把 children / fixed 写在对应节点的声明上")
        rows = raw.get("slots")
        if not isinstance(rows, list) or not rows:
            raise SlotConfigError("配置缺少 slots 列表")
        specs: Dict[str, SlotSpec] = {}
        for row in rows:
            spec = parse_spec(row)
            if spec.path in specs:
                raise SlotConfigError(f"路径重复：{spec.path}")
            specs[spec.path] = spec
        try:
            version = int(raw.get("version") or 1)
        except (TypeError, ValueError) as exc:
            raise SlotConfigError("version 非法") from exc
        overrides = raw.get("overrides") or ()
        if not isinstance(overrides, (list, tuple)):
            raise SlotConfigError("overrides 必须是数组")
        config = cls(
            root=str(raw.get("root") or APP_ROOT),
            version=version,
            specs=specs,
            overrides=tuple(dict(row) for row in overrides),
        )
        _validate(config)
        return config

    def spec(self, path: str) -> SlotSpec:
        try:
            return self.specs[path]
        except KeyError as exc:
            raise SlotConfigError(f"路径不存在：{path}") from exc

    def paths(self) -> Tuple[str, ...]:
        """全部节点路径。装配与绑定通过它遍历，不直接拓 `specs`。"""
        return tuple(self.specs)

    def children(self, path: str) -> Tuple[SlotSpec, ...]:
        """直接子节点，按同层排序键返回。"""
        prefix = path.rstrip("/") + "/"
        return tuple(sorted(
            (spec for spec in self.specs.values()
             if spec.path.startswith(prefix)
             and "/" not in spec.path[len(prefix):]),
            key=sort_key,
        ))

    def by_scope(self, scope: str) -> Tuple[SlotSpec, ...]:
        return tuple(spec for spec in self.specs.values() if spec.scope == scope)


def load_config(path: Path) -> SlotConfig:
    target = Path(path)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SlotConfigError(f"配置不可读：{target}") from exc
    return SlotConfig.parse(raw)


def topo_order(config: SlotConfig) -> Tuple[str, ...]:
    """按依赖求值的构造顺序；子节点先于父节点，成环即报错。

    容器构造时要把已构造的子节点交给 factory，所以包含关系也是一条依赖边。
    """
    children: Dict[str, List[str]] = {path: [] for path in config.specs}
    for path in config.specs:
        head, sep, _tail = path.rpartition("/")
        if sep and head in children:
            children[head].append(path)
    pending: Dict[str, set] = {
        path: set(spec.requires.values()) | set(children[path])
        for path, spec in config.specs.items()}
    dependents: Dict[str, List[str]] = {path: [] for path in config.specs}
    for path, deps in pending.items():
        for dep in deps:
            dependents[dep].append(path)
    ready = [(sort_key(config.specs[path]), path)
             for path, deps in pending.items() if not deps]
    heapq.heapify(ready)
    order: List[str] = []
    while ready:
        _key, path = heapq.heappop(ready)
        order.append(path)
        for child in sorted(dependents.get(path, ())):
            pending[child].discard(path)
            if not pending[child]:
                heapq.heappush(ready, (sort_key(config.specs[child]), child))
    if len(order) != len(pending):
        stuck = sorted(path for path, deps in pending.items() if deps)
        raise SlotConfigError(f"依赖成环：{', '.join(stuck)}")
    return tuple(order)
