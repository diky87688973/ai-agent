"""模型 HTTP 池的请求作用域和独立调用方的资源所有权。"""
from __future__ import annotations

import contextvars
import threading
import weakref
from contextlib import contextmanager
from typing import Iterator

from agent.mechanisms.model_http.pool import ModelHTTPPool
from agent.mechanisms.providers.base import ModelRequestError

_POOL: contextvars.ContextVar[ModelHTTPPool | None] = contextvars.ContextVar("model_http_pool", default=None)


@contextmanager
def pool_scope(pool: ModelHTTPPool) -> Iterator[None]:
    token = _POOL.set(pool)
    try:
        yield
    finally:
        _POOL.reset(token)


class ModelHTTPClient:
    """宿主请求借用共享池；独立 provider 拥有自己的惰性池。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._owned: ModelHTTPPool | None = None
        self._finalizer = None
        self._disposed = False

    def pool(self) -> ModelHTTPPool:
        with self._lock:
            if self._disposed:
                raise ModelRequestError("模型 HTTP 客户端已关闭")
            scoped = _POOL.get()
            if scoped is not None:
                return scoped
            if self._owned is None:
                self._owned = ModelHTTPPool()
                self._finalizer = weakref.finalize(self, self._owned.dispose)
            return self._owned

    def dispose(self) -> None:
        with self._lock:
            self._disposed = True
            finalizer = self._finalizer
        if finalizer is not None:
            finalizer()
