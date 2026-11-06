"""轮次租约：活跃读取者退出后才发布插件变更。"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Iterator, List
from uuid import uuid4

from agent.core.error_report import report_error


@dataclass(frozen=True)
class SlotRequest:
    request_id: str
    applied: bool

class SlotLifecycle:
    """并发回合共享当前代；变更回调在无活跃回合时串行执行。"""

    def __init__(self, snapshots: Any) -> None:
        self.snapshots = snapshots
        self._lock = threading.RLock()
        self._readers = 0
        self._pending: List[tuple[Callable[[], Any], dict]] = []
        self._closed = False
        self._operations: List[dict] = []

    @property
    def operations(self) -> tuple:
        with self._lock:
            return tuple(MappingProxyType(dict(item)) for item in self._operations)

    def _apply(self, apply: Callable[[], Any], operation: dict) -> None:
        operation["status"] = "applying"
        try:
            apply()
        except Exception as exc:
            details = [f"{type(exc).__name__}: {exc}"]
            cause = exc.__cause__
            while cause is not None and len(details) < 4:
                details.append(f"{type(cause).__name__}: {cause}")
                cause = cause.__cause__
            operation.update(status="failed", error="；".join(details))
            raise
        operation["status"] = "succeeded"

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
                    for apply, operation in pending:
                        try:
                            self._apply(apply, operation)
                        except Exception as exc:
                            report_error("slot_lifecycle.apply", exc)

    def request(self, apply: Callable[[], Any], *, label: str = "") -> SlotRequest:
        """返回不可变请求凭据；终态由 operations 的只读查询提供。"""
        with self._lock:
            if self._closed:
                raise RuntimeError("插口生命周期已关闭")
            if len(self._pending) >= 64:
                raise RuntimeError("插口变更队列已满")
            operation = {"request_id": uuid4().hex, "label": label,
                         "status": "queued", "error": ""}
            if len(self._operations) >= 64:
                finished = next((index for index, item in enumerate(self._operations)
                                 if item["status"] in {"succeeded", "failed"}), None)
                if finished is None:
                    raise RuntimeError("插口变更记录已满")
                self._operations.pop(finished)
            self._operations.append(operation)
            if self._readers:
                self._pending.append((apply, operation))
                return SlotRequest(operation["request_id"], False)
            self._apply(apply, operation)
            return SlotRequest(operation["request_id"], True)

    def close(self) -> None:
        with self._lock:
            if self._readers:
                raise RuntimeError("仍有活跃回合，不能释放插口")
            self._closed = True
            self._pending.clear()
