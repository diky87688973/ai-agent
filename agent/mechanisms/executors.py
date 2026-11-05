# -*- coding: utf-8 -*-
"""执行器注册表：工具预览（confirm_id 制）之后谁来真正落盘。

内置写类工具的执行器在装配点静态给；插件贡献的写类工具走这里登记 ——
提交发生在工具调用那一刻，登记发生在插件装载那一刻，所以用注册表解耦顺序。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from agent.core.app_path import app_path

Executor = Callable[[Dict[str, Any]], Dict[str, Any]]


class ExecutorRegistry:
    """`{工具名: 执行器}`；同名后登记者覆盖前者，注销只删自己那一条。"""

    def __init__(self, slots: Any = None) -> None:
        self._items: Dict[str, Executor] = {}
        self._owners: Dict[str, str] = {}
        self._slots = slots

    @staticmethod
    def _slot_path(name: str) -> str:
        return app_path("tools", name, "executor")

    def _ensure_slot(self, name: str, owner: str = "") -> None:
        if self._slots is None:
            return
        path = self._slot_path(name)
        if path not in self._slots.nodes:
            self._slots.register_slot(
                path, kind="executor", default=self._items.get(name),
                default_owner=str(owner or "__host__"))

    def add(self, name: str, fn: Executor, owner: str = "",
            *, replace: bool = False) -> Any:
        """登记执行器；replace=True 时走绑定替换，旧实现保留为回退。"""
        key = str(name or "").strip()
        if not key:
            raise ValueError("执行器名不能为空")
        if not callable(fn):
            raise ValueError("执行器必须可调用")
        if replace:
            return self.replace(key, fn, owner)
        self._items[key] = fn
        self._owners[key] = str(owner or "")
        self._ensure_slot(key, owner)
        if self._slots is not None:
            node = self._slots.nodes[self._slot_path(key)]
            if not node.bindings:
                node.default = fn
        return lambda: self._drop(key, fn)

    def replace(self, name: str, fn: Executor, owner: str = "",
                *, priority: int = 0) -> Any:
        """绑定一个新执行器实现；disposer 后恢复旧实现。"""
        key = str(name or "").strip()
        if not key:
            raise ValueError("执行器名不能为空")
        if not callable(fn):
            raise ValueError("执行器必须可调用")
        if self._slots is None:
            raise RuntimeError("执行器注册表未接入插口树")
        self._ensure_slot(key, owner)
        return self._slots.bind(
            self._slot_path(key), fn, owner=str(owner or "__plugin__"),
            mode="replace", priority=priority)

    def _drop(self, key: str, fn: Executor) -> None:
        if self._items.get(key) is fn:
            self._items.pop(key, None)
            self._owners.pop(key, None)

    def get(self, name: str) -> Optional[Executor]:
        key = str(name or "").strip()
        if self._slots is not None:
            path = self._slot_path(key)
            node = self._slots.nodes.get(path)
            if node is not None:
                if node.default is None and not node.bindings:
                    return None
                return self._slots.resolve(path)
        return self._items.get(key)

    def names(self) -> List[str]:
        names = set(self._items)
        if self._slots is not None:
            for path in self._slots.nodes:
                prefix = app_path("tools") + "/"
                suffix = "/executor"
                if path.startswith(prefix) and path.endswith(suffix):
                    names.add(path[len(prefix):-len(suffix)])
        return sorted(names)
