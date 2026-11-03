# -*- coding: utf-8 -*-
"""自装配组件契约：所有运行期组件继承 SlotComponent。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agent.core.error_report import report_error


class SlotComponent(ABC):
    """可被插口树装配的组件。"""

    path: str
    master: bool = False

    @abstractmethod
    def assembly(self, tree: Any) -> bool:
        """装配自己的直接子组件；叶子返回 True。"""

    def port_value(self) -> Any:
        """作为依赖端口时暴露的值；默认暴露组件自身。"""
        return self

    def dispose(self) -> None:
        """释放组件持有的资源。"""
        return None


class SlotLeaf(SlotComponent):
    """没有子组件的叶子。"""

    def __init__(self, path: str, *, master: bool = False) -> None:
        self.path = path
        self.master = bool(master)

    def assembly(self, tree: Any) -> bool:
        return True


class SlotContainer(SlotComponent):
    """只按树结构遍历直接子节点的通用容器。"""

    def __init__(self, path: str, *, master: bool = True) -> None:
        self.path = path
        self.master = bool(master)
        self._plugins: list[Any] = []
        self._disposed = False
        self._assembled = False

    def assembly(self, tree: Any) -> bool:
        if self._assembled:
            return True
        added: list[Any] = []
        failure = False
        try:
            for child in tree.children(self.path):
                if not child.enabled:
                    continue
                if child.metadata.get("scope") == "session":
                    continue
                plugin = tree.materialize(child)
                added.append(plugin)
                self._plugins.append(plugin)
                ok = tree.assemble(plugin)
                if not ok and child.master:
                    failure = True
                    break
        except Exception:
            self._rollback(added, tree)
            raise
        if failure:
            self._rollback(added, tree)
            return False
        self._assembled = True
        return True

    def _rollback(self, added: list[Any], tree: Any = None) -> None:
        """撤掉本次 assembly 已挂上的子组件，并清掉树上的实例缓存。"""
        for plugin in reversed(added):
            if tree is not None:
                tree.release_component(plugin)
            try:
                plugin.dispose()
            except Exception as exc:
                report_error("agent.core.slot.SlotContainer.assembly_rollback", exc)
            try:
                self._plugins.remove(plugin)
            except ValueError as exc:
                report_error("agent.core.slot.SlotContainer.remove", exc)

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        for plugin in reversed(self._plugins):
            plugin.dispose()
        self._plugins.clear()


class SlotContribution(SlotLeaf):
    """把一个运行期扩展点注册动作包装成树节点。"""

    def __init__(self, path: str, register: Any, *, master: bool = True) -> None:
        super().__init__(path, master=master)
        self._register = register
        self._disposer = None
        self._applied = False
        self._disposed = False

    def assembly(self, tree: Any) -> bool:
        if self._applied:
            return True
        self._disposer = self._register()
        self._applied = True
        return True

    def deactivate(self) -> None:
        """替换时撤销当前注册，但保留可再次 assembly 的能力。"""
        if not self._applied:
            return
        self._applied = False
        disposer, self._disposer = self._disposer, None
        if callable(disposer):
            disposer()

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        self.deactivate()


class SlotValue(SlotLeaf):
    """持有单个服务实例的叶子组件。"""

    def __init__(self, path: str, value: Any, *, master: bool = False) -> None:
        super().__init__(path, master=master)
        self.value = value
        self._disposed = False

    def port_value(self) -> Any:
        return self.value

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        close = getattr(self.value, "close", None)
        if callable(close):
            close()


__all__ = [
    "SlotComponent", "SlotContainer", "SlotContribution", "SlotLeaf",
    "SlotValue",
]
