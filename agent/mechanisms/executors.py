# -*- coding: utf-8 -*-
"""执行器注册表：工具预览（confirm_id 制）之后谁来真正落盘。

内置写类工具的执行器在装配点静态给；插件贡献的写类工具走这里登记 ——
提交发生在工具调用那一刻，登记发生在插件装载那一刻，所以用注册表解耦顺序。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

Executor = Callable[[Dict[str, Any]], Dict[str, Any]]


class ExecutorRegistry:
    """`{工具名: 执行器}`；同名后登记者覆盖前者，注销只删自己那一条。"""

    def __init__(self) -> None:
        self._items: Dict[str, Executor] = {}
        self._owners: Dict[str, str] = {}

    def add(self, name: str, fn: Executor, owner: str = "") -> Callable[[], None]:
        """登记执行器；返回幂等 disposer。"""
        key = str(name or "").strip()
        if not key:
            raise ValueError("执行器名不能为空")
        if not callable(fn):
            raise ValueError("执行器必须可调用")
        self._items[key] = fn
        self._owners[key] = str(owner or "")
        return lambda: self._drop(key, fn)

    def _drop(self, key: str, fn: Executor) -> None:
        if self._items.get(key) is fn:
            self._items.pop(key, None)
            self._owners.pop(key, None)

    def get(self, name: str) -> Optional[Executor]:
        return self._items.get(str(name or "").strip())

    def names(self) -> List[str]:
        return sorted(self._items)
