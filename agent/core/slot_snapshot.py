# -*- coding: utf-8 -*-
"""轮次快照：一轮之内只读的插口视图。

树在启动时合并一次、装配一次，之后结构定型。每轮开始时取一份快照，
轮内所有读取点都问同一份快照；轮内发生的变更只登记为待生效，下一轮才重建。

快照只装三样东西：版本号、当期只读配置、app 级已构造实例的引用。
实例本身不复制也不包装——只复制结构与引用，是快照的定义。

session 级实例刻意不进快照：同一路径在不同会话是不同的实例，
快照若固化它，会话 A 的快照被会话 B 读到就是跨会话串实例。
session 解析仍走 `session_context` 的既有链（本会话实例 → app 级 → 报错），
快照不介入、不缓存、不代理。
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from agent.core.slot_config import SlotConfig
from agent.core.slot_spec import (
    SCOPE_APP,
    SlotConfigError,
    SlotSpec,
)

#: 重建函数的返回值：新的配置与应用级实例表。
Rebuild = Callable[[], Tuple[SlotConfig, Mapping[str, Any]]]


@dataclass(frozen=True)
class SlotSnapshot:
    """某一轮的只读插口视图。

    `built` 只含 `scope=app` 的已构造实例；`session` 级路径不会出现，
    取 session 实例请走会话自己的解析链。

    本类的 `version` 是结构版本（每次重建自增），
    与 `SlotConfig.version`（配置格式版本）无关。
    """

    version: int
    config: SlotConfig
    built: Mapping[str, Any] = field(default_factory=dict)

    def has(self, path: str) -> bool:
        return path in self.built

    def get(self, path: str) -> Any:
        try:
            return self.built[path]
        except KeyError as exc:
            raise SlotConfigError(f"快照中无此实例：{path}") from exc

    def paths(self) -> Tuple[str, ...]:
        return tuple(sorted(self.built))


def _freeze_value(value: Any) -> Any:
    """递归冻结容器：映射成只读视图，序列换成不可变同构。

    映射 -> `MappingProxyType`；`list` / `tuple` -> `tuple`；`set` -> `frozenset`；
    `bytearray` -> `bytes`；其余原样返回。
    序列必须换成不可变类型：只冻字典不冻序列，轮内仍能 append。
    载荷整体序列化给前端，`json.dumps` 对 `tuple` 与 `list` 输出一致，故对外格式不变。
    """
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_value(item)
                                 for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_value(item) for item in value)
    if isinstance(value, bytearray):
        return bytes(value)
    return value


def _freeze_spec(spec: SlotSpec) -> SlotSpec:
    """节点的副本：`requires` / `props` 两个字典字段被冻结。

    `frozen=True` 只锁字段赋值，不锁字段内容；只冻 `config.specs` 等于只锁住
    「增删换节点」，取出来的节点内部字典仍可改。故逐个节点做副本。
    """
    return replace(
        spec,
        requires=MappingProxyType({key: str(value)
                                   for key, value in spec.requires.items()}),
        props=_freeze_value(spec.props),
    )


def _freeze_config(config: SlotConfig) -> SlotConfig:
    """把配置与它的节点全部冻结，返回副本。

    `frozen=True` 只锁字段赋值，不锁字段内容；`specs` 等字段实际是普通 dict，
    拿到快照就能往里写。快照对配置的只读承诺必须对内容也成立：
    先冻每个节点，再冻装节点的映射。
    复制一份再冻，不把调用方传进来的对象也冻上。
    """
    return replace(
        config,
        specs=MappingProxyType({path: _freeze_spec(spec)
                                for path, spec in config.specs.items()}),
        origins=MappingProxyType(dict(config.origins)),
        subagent_tools=MappingProxyType(dict(config.subagent_tools)),
    )


def _app_level(config: SlotConfig, built: Mapping[str, Any]) -> Dict[str, Any]:
    """只保留 app 级已构造实例。

    session 级路径不进快照。装配结果里出现配置中没有的路径，说明合并与装配不同步，
    这是硬错误：静默丢它会让 bug 一直隐形，只在某个功能莫名失效时才暴露。
    """
    kept: Dict[str, Any] = {}
    for path, value in built.items():
        spec = config.specs.get(path)
        if spec is None:
            raise SlotConfigError(f"装配结果出现配置中没有的路径：{path}")
        if spec.scope == SCOPE_APP:
            kept[path] = value
    return kept


class SnapshotStore:
    """快照的唯一入口：谁持有它，谁就是本进程的权威。

    不设模块级单例：模块级可变全局就是与树并行的第二套账本。
    唯一性由「调用方持有并注入」保证——需要读插口的模块拿到的都是同一个实例。
    两个 store 各自独立、版本号互不共享，因此不会被误当成一份权威。
    """

    def __init__(self, config: SlotConfig, built: Mapping[str, Any], *,
                 rebuild: Optional[Rebuild] = None) -> None:
        frozen = _freeze_config(config)
        self._config = frozen
        self._built = MappingProxyType(_app_level(frozen, built))
        self._rebuild = rebuild
        self._version = 0
        self._snapshot = SlotSnapshot(
            version=self._version, config=frozen, built=self._built)
        self._pending: List[str] = []

    @property
    def version(self) -> int:
        """当前结构版本；轮内不变，重建后自增。"""
        return self._version

    @property
    def has_pending(self) -> bool:
        return bool(self._pending)

    @property
    def current(self) -> SlotSnapshot:
        """最近一次取到的快照；未取过即为初始快照。"""
        return self._snapshot

    def stage(self, reason: str = "") -> None:
        """登记一条待生效变更。

        只记描述，不落账：真正重建仍走宿主既有的合并与装配入口，
        由注入的 `rebuild` 完成，本类不拼结构。
        """
        self._pending.append(str(reason or "change"))

    def begin_turn(self) -> SlotSnapshot:
        """轮次边界调用一次，返回本轮快照。

        版本未变且无待生效变更时直接返回上一份对象——没有注册/注销时开销接近零。
        有待生效变更时调 `rebuild` 重建一次，版本自增，变更从本轮起可见。
        """
        if not self._pending:
            return self._snapshot
        if self._rebuild is None:
            raise SlotConfigError("有待生效变更但未注入重建入口")
        config, built = self._rebuild()
        frozen = _freeze_config(config)
        self._config = frozen
        self._built = MappingProxyType(_app_level(frozen, built))
        self._pending.clear()
        self._version += 1
        self._snapshot = SlotSnapshot(
            version=self._version, config=frozen, built=self._built)
        return self._snapshot

    def accept(self, version: int) -> bool:
        """异步结果落地前的过期校验：版本不符即拒。"""
        return int(version) == self._version


__all__ = ["SlotSnapshot", "SnapshotStore"]
