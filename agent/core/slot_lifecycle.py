"""轮次租约：活跃读取者退出后才发布插件变更。"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any, Callable, Iterator, List

from agent.core.error_report import report_error


class SlotLifecycle:
    """并发回合共享当前代；变更回调在无活跃回合时串行执行。"""

    def __init__(self, snapshots: Any) -> None:
        self.snapshots = snapshots
        self._lock = threading.RLock()
        self._readers = 0
        self._pending: List[Callable[[], Any]] = []
        self._closed = False

    @contextmanager
    def turn(self) -> Iterator[Any]:
        with self._lock:
            if self._closed:
                raise RuntimeError("插口生命周期已关闭")
            self._readers += 1
            snapshot = self.snapshots.current
        try:
            yield snapshot
        finally:
            with self._lock:
                self._readers -= 1
                if not self._readers:
                    pending, self._pending = self._pending, []
                    for apply in pending:
                        try:
                            apply()
                        except Exception as exc:
                            report_error("slot_lifecycle.apply", exc)

    def request(self, apply: Callable[[], Any]) -> bool:
        """返回 True 表示已应用，False 表示将在全部回合结束后应用。"""
        with self._lock:
            if self._closed:
                raise RuntimeError("插口生命周期已关闭")
            if self._readers:
                self._pending.append(apply)
                return False
            apply()
            return True

    def close(self) -> None:
        with self._lock:
            if self._readers:
                raise RuntimeError("仍有活跃回合，不能释放插口")
            self._closed = True
            self._pending.clear()
