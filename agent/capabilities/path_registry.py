# -*- coding: utf-8 -*-
"""插件路径注册表：插口协议、注册项和生命周期清理。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Optional, Tuple

_PATH_SEGMENT = re.compile(r"^[a-z0-9_-]+$")
_PARAM_SEGMENT = re.compile(r"^<([a-z][a-z0-9_]*)>$")
_PARAM_VALUE = re.compile(r"^[A-Za-z0-9_.-]+$")


class PathRegistryError(ValueError):
    """路径不符合插口协议。"""


def split_path(path: str) -> Tuple[str, ...]:
    raw = str(path or "").strip().strip("/")
    if not raw or "\\" in raw or ".." in raw:
        raise PathRegistryError(f"路径非法：{path!r}")
    parts = tuple(raw.split("/"))
    for part in parts:
        if _PARAM_SEGMENT.match(part):
            continue
        if not _PATH_SEGMENT.match(part):
            raise PathRegistryError(f"路径段非法：{part!r}")
    return parts


def match_pattern(pattern: str, path: str) -> Optional[Dict[str, str]]:
    expected = split_path(pattern)
    actual = split_path(path)
    if len(expected) != len(actual):
        return None
    params: Dict[str, str] = {}
    for want, got in zip(expected, actual):
        param = _PARAM_SEGMENT.match(want)
        if param:
            if not _PARAM_VALUE.match(got):
                return None
            params[param.group(1)] = got
            continue
        if want != got:
            return None
    return params


@dataclass(slots=True)
class PathSlot:
    pattern: str
    kind: str
    children: str
    allowed_kinds: Tuple[str, ...] = ()
    fixed_children: Tuple[str, ...] = ()
    owner: str = "*"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "path": self.pattern,
            "kind": self.kind,
            "children": self.children,
            "allowed_kinds": list(self.allowed_kinds),
            "fixed_children": list(self.fixed_children),
            "owner": self.owner,
        }


@dataclass(slots=True)
class PathEntry:
    path: str
    kind: str
    owner: str
    handler: Optional[Callable[..., Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind,
            "owner": self.owner,
            "metadata": dict(self.metadata),
        }


@dataclass
class PathRegistry:
    slots: Dict[str, PathSlot] = field(default_factory=dict)
    entries: Dict[str, PathEntry] = field(default_factory=dict)

    def add_slot(
        self, pattern: str, *, kind: str, children: str,
        allowed_kinds: Iterable[str] = (), fixed_children: Iterable[str] = (),
        owner: str = "*",
    ) -> Callable[[], None]:
        split_path(pattern)
        if children not in ("none", "fixed", "keyed", "extension"):
            raise PathRegistryError(f"子路径策略非法：{children!r}")
        if pattern in self.slots:
            raise PathRegistryError(f"插口已注册：{pattern}")
        slot = PathSlot(
            pattern=pattern, kind=str(kind), children=children,
            allowed_kinds=tuple(str(item) for item in allowed_kinds),
            fixed_children=tuple(str(item) for item in fixed_children),
            owner=str(owner or "*"),
        )
        self.slots[pattern] = slot

        def _drop_slot() -> None:
            if self.slots.get(pattern) is slot:
                del self.slots[pattern]

        return _drop_slot

    def _parent_slot(self, path: str) -> Tuple[PathSlot, str]:
        parts = split_path(path)
        if len(parts) < 2:
            raise PathRegistryError(f"根路径不可注册：{path!r}")
        parent = "/".join(parts[:-1])
        for slot in self.slots.values():
            if match_pattern(slot.pattern, parent) is not None:
                return slot, parts[-1]
        raise PathRegistryError(f"父插口未注册：{parent}")

    def validate(self, path: str, *, kind: str, owner: str) -> None:
        """只校验路径是否落在父插口协议内，不写入 entry。"""
        if path in self.entries:
            raise PathRegistryError(f"路径已注册：{path}")
        slot, child = self._parent_slot(path)
        if slot.children == "none":
            raise PathRegistryError(f"父插口不允许子路径：{slot.pattern}")
        if slot.children == "fixed" and child not in slot.fixed_children:
            raise PathRegistryError(f"子路径不在固定列表：{child}")
        if slot.children in ("keyed", "extension") and not _PARAM_VALUE.match(child):
            raise PathRegistryError(f"子路径参数非法：{child!r}")
        if slot.allowed_kinds and kind not in slot.allowed_kinds:
            raise PathRegistryError(f"kind 不被插口接受：{kind}")
        if slot.owner != "*" and slot.owner != owner:
            raise PathRegistryError(f"owner 不被插口接受：{owner}")

    def register(
        self, path: str, *, kind: str, owner: str,
        handler: Optional[Callable[..., Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Callable[[], None]:
        self.validate(path, kind=kind, owner=owner)
        entry = PathEntry(path=path, kind=str(kind), owner=str(owner),
                          handler=handler, metadata=dict(metadata or {}))
        self.entries[path] = entry

        def _drop_entry() -> None:
            if self.entries.get(path) is entry:
                del self.entries[path]

        return _drop_entry

    def get(self, path: str) -> PathEntry:
        entry = self.entries.get(str(path or ""))
        if entry is None:
            raise PathRegistryError(f"路径不存在：{path!r}")
        return entry

    def catalog(self) -> Dict[str, Any]:
        return {
            "slots": [slot.as_dict() for slot in self.slots.values()],
            "entries": [entry.as_dict() for entry in self.entries.values()],
        }

    def drop_owner(self, owner: str) -> int:
        name = str(owner or "")
        paths = [path for path, entry in self.entries.items() if entry.owner == name]
        for path in paths:
            self.entries.pop(path, None)
        return len(paths)


__all__ = ["PathEntry", "PathRegistry", "PathRegistryError", "PathSlot",
           "match_pattern", "split_path"]
