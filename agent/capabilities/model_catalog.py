# -*- coding: utf-8 -*-
"""模型目录：跨厂商的模型描述注册表 + provider 缓存。

唯一权威来源，语义是"替换"而不是"合并"：同一来源再注册一次就是配置变了，
整批覆盖。合并式注册表一旦真出现第二个来源，`default_id` 该听谁的就没法回答。

三条纪律：

1. 权威是算出来的：`authoritative = len(有效条目) > 0`。不能把布尔值固化在
   设置那一刻——配置从 3 条改成 0 条时，布尔值不会跟着变，权威就会指着一个空目录。
2. 锁内不做 I/O：条目回调可能读配置文件，解析与校验在锁外完成，进锁只做一次
   引用替换。任意一次快照要么全旧、要么全新。
3. provider 缓存按整批重建：条目任一字段变化就丢光缓存。条目数是十几个，
   重建成本可忽略，换来的是没有"指纹算错拿了旧实例"这类难复现的问题。
"""
from __future__ import annotations

import json
import sys
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple, Union

from agent.capabilities.contributions import Disposer
from agent.mechanisms.model_provider import ModelProvider
from agent.mechanisms.provider_registry import build_provider, known_kinds

#: 条目来源：静态序列，或每次快照时重新求值的回调（插件用它实现热读配置）。
EntrySource = Union[Sequence["ModelEntry"], Callable[[], Sequence["ModelEntry"]]]


@dataclass(frozen=True)
class ModelEntry:
    """一条模型描述。

    `options_json` 存规范化 JSON 而不是共享 dict：`frozen` 只保证字段不能重新赋值，
    字段里塞一个可变 dict 仍然能被调用方改写——那样的"只读视图"是假的。
    """

    id: str
    provider: str
    options_json: str = "{}"
    label: str = ""
    is_default: bool = False

    @classmethod
    def from_options(
        cls,
        *,
        id: str,
        provider: str,
        label: str = "",
        options: Optional[Mapping[str, Any]] = None,
        is_default: bool = False,
    ) -> "ModelEntry":
        """用选项字典构造条目；键排序后落 JSON，指纹与输出都稳定。"""
        try:
            options_json = json.dumps(
                dict(options or {}), ensure_ascii=False, sort_keys=True, default=str,
            )
        except (TypeError, ValueError):
            options_json = "{}"
        return cls(
            id=str(id or "").strip(),
            provider=str(provider or "").strip().lower(),
            options_json=options_json,
            label=str(label or ""),
            is_default=bool(is_default),
        )

    @property
    def options(self) -> Dict[str, Any]:
        """选项的新副本：调用方改它不会影响目录里的那份。"""
        try:
            data = json.loads(self.options_json or "{}")
        except (TypeError, ValueError):
            # 单条目录的 options 坏了只影响这一条；按空选项继续，目录仍可用。
            return {}
        return dict(data) if isinstance(data, dict) else {}

    @property
    def context_window(self) -> int:
        """模型上下文窗口（token）；条目没声明时为 0（调用方用缺省值兜底）。"""
        try:
            return max(0, int(self.options.get("context_window") or 0))
        except (TypeError, ValueError):
            return 0

    @property
    def compression_percent(self) -> int:
        """该模型的压缩触发百分比；缺失或越界按 70。"""
        raw = self.options.get("compression_percent")
        if isinstance(raw, bool):
            return 70
        if isinstance(raw, int):
            value = raw
        elif isinstance(raw, str) and raw.strip().isdigit():
            value = int(raw.strip())
        else:
            return 70
        return value if 10 <= value <= 90 else 70


@dataclass(frozen=True)
class CatalogSnapshot:
    """某一瞬间的目录：条目是 tuple，调用方改不动内部。"""

    entries: Tuple[ModelEntry, ...]
    default_id: str
    authoritative: bool
    source: str

    def entry(self, model_id: str) -> Optional[ModelEntry]:
        want = str(model_id or "").strip()
        for item in self.entries:
            if item.id == want:
                return item
        return None


def _warn(message: str) -> None:
    print(f"[model_catalog] {message}", file=sys.stderr, flush=True)


class ModelCatalog:
    """模型描述注册表；provider 实例按条目惰性构造并缓存。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._source = ""
        self._entries: EntrySource = ()
        #: 每次登记/注销自增；disposer 只对自己那次登记生效。
        self._generation = 0
        #: 最近一次成功解析出的条目；热读失败时继续用它，不让模型列表凭空消失。
        self._last_good: Tuple[ModelEntry, ...] = ()
        #: 当前批次条目的指纹，用于判定缓存是否还有效。
        self._fingerprint: Tuple[Tuple[str, str, str], ...] = ()
        #: 键是条目指纹而非 id：热读配置下同 id 的选项可能变，键必须跟着变。
        self._providers: Dict[Tuple[str, str, str], ModelProvider] = {}

    # ── 注册 / 注销 ──

    def set_source(self, source: str, entries: EntrySource) -> Disposer:
        """登记（或整批替换）一个来源；返回幂等 disposer。

        第二个不同来源被拒绝：目录只允许一个权威。拒绝时保留原来源并留痕，
        插件装载不因此失败（装载顺序不是契约，必须确定且可审计）。
        """
        name = str(source or "").strip()
        if not name:
            raise ValueError("模型目录来源名不能为空")
        normalized = self._normalize(name, entries) or ()
        with self._lock:
            if self._source and self._source != name:
                raise RuntimeError(
                    f"模型目录已有来源 {self._source!r}，拒绝第二个来源 {name!r}"
                )
            self._source = name
            self._entries = entries
            self._last_good = normalized
            self._generation += 1
            generation = self._generation
            self._fingerprint = ()
            self._providers = {}
        return lambda: self._drop_source(name, generation)

    def _drop_source(self, source: str, generation: int) -> None:
        with self._lock:
            if self._source != source or self._generation != generation:
                return
            self._source = ""
            self._entries = ()
            self._last_good = ()
            self._generation += 1
            self._fingerprint = ()
            self._providers = {}

    def _normalize(self, source: str, entries: EntrySource) -> Optional[Tuple[ModelEntry, ...]]:
        """求出条目并校验。

        回调抛异常返回 `None`（"这次没读到"，由调用方决定沿用旧值），
        条目重复抛 `ValueError`（"读到了，但配置写坏了"）。两者不能混为一谈。
        """
        try:
            raw = entries() if callable(entries) else entries
            items = list(raw or ())
        except Exception as exc:
            _warn(f"{source}: 读取模型条目失败：{type(exc).__name__}: {exc}")
            return None
        seen: Dict[str, ModelEntry] = {}
        for item in items:
            if not isinstance(item, ModelEntry):
                _warn(f"{source}: 忽略非 ModelEntry 条目：{type(item).__name__}")
                continue
            if not item.id:
                _warn(f"{source}: 忽略 id 为空的模型条目")
                continue
            if item.id in seen:
                raise ValueError(f"{source}: 模型 id 重复：{item.id!r}")
            if not item.provider:
                _warn(f"{source}: [model:{item.id}] 未指定 provider，条目无效")
                continue
            if item.provider not in known_kinds():
                _warn(f"{source}: [model:{item.id}] 未知 provider {item.provider!r}，条目无效")
                continue
            seen[item.id] = item
        return tuple(seen.values())

    # ── 读快照 ──

    def snapshot(self) -> CatalogSnapshot:
        # 最多重试几轮：解析期间来源被替换时按当前状态重算，而不是无限递归。
        for _ in range(4):
            with self._lock:
                source = self._source
                entries_ref = self._entries
            if not source:
                return CatalogSnapshot(
                    entries=(), default_id="", authoritative=False, source="",
                )
            try:
                normalized = self._normalize(source, entries_ref)
            except ValueError:
                # 热读期间配置写坏（例如重复 id）：沿用上一份好配置，聊天不中断。
                normalized = None
            if normalized is None:
                # 回调读不到配置：沿用上一份好配置，不让模型列表瞬间清零。
                with self._lock:
                    normalized = self._last_good
            fingerprint = tuple(
                (item.id, item.provider, item.options_json) for item in normalized
            )
            with self._lock:
                if self._source != source or self._entries is not entries_ref:
                    continue
                self._last_good = normalized
                if fingerprint != self._fingerprint:
                    self._fingerprint = fingerprint
                    self._providers = {}
                break
        else:
            # 连续被抢占：用最后一次求值结果作答，不阻塞也不递归。
            with self._lock:
                source = self._source
                normalized = self._last_good
        default_id = ""
        for item in normalized:
            if item.is_default:
                default_id = item.id
                break
        if not default_id and normalized:
            default_id = normalized[0].id
        return CatalogSnapshot(
            entries=normalized,
            default_id=default_id,
            authoritative=bool(normalized),
            source=source,
        )

    def ids(self) -> Tuple[str, ...]:
        return tuple(item.id for item in self.snapshot().entries)

    def default_id(self) -> str:
        return self.snapshot().default_id

    def provider_for(self, model_id: str) -> Optional[ModelProvider]:
        """按模型 id 取 provider 实例；未知 id 返回 None（由调用方决定报错）。"""
        snap = self.snapshot()
        item = snap.entry(model_id)
        if item is None:
            return None
        key = (item.id, item.provider, item.options_json)
        with self._lock:
            cached = self._providers.get(key)
            if cached is not None:
                return cached
        built = build_provider(item.provider, item.options)
        with self._lock:
            # 双检：并发构造只保留一个；缓存键含整条指纹，旧条目不会被新条目命中。
            return self._providers.setdefault(key, built)
