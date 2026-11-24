"""有界 HTTP 进程池：FIFO 租用、取消隔离、空闲回收与宿主释放。"""
from __future__ import annotations

import contextvars
import math
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from agent.config_schema import MODEL_HTTP_DEFAULTS
from agent.core.error_report import report_error
from agent.mechanisms.model_http.process import HTTPWorker
from agent.mechanisms.providers.base import ModelRequestCancelled, ModelRequestError


@dataclass(frozen=True)
class PoolLimits:
    max_workers: int = int(MODEL_HTTP_DEFAULTS["max_workers"])
    max_pending: int = int(MODEL_HTTP_DEFAULTS["max_pending"])
    wait_timeout: float = float(MODEL_HTTP_DEFAULTS["wait_timeout"])
    idle_timeout: float = float(MODEL_HTTP_DEFAULTS["idle_timeout"])

    def __post_init__(self) -> None:
        for name, minimum in (("max_workers", 1), ("max_pending", 0)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"model_http.{name} 必须是大于等于 {minimum} 的整数")
        for name in ("wait_timeout", "idle_timeout"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"model_http.{name} 必须是有限正数")


@dataclass(eq=False)
class PoolRequest:
    request_id: bytes = field(default_factory=lambda: uuid.uuid4().bytes)
    canceled: threading.Event = field(default_factory=threading.Event)


@dataclass
class _Slot:
    request: PoolRequest | None
    state: str = "busy"
    idle_at: float = 0.0


class ModelHTTPPool:
    """一个进程同时只承载一个请求，状态和租约归池唯一持有。"""

    def __init__(self, limits: PoolLimits | None = None, *,
                 worker_factory: Callable[[], HTTPWorker] = HTTPWorker) -> None:
        self.limits = limits or PoolLimits()
        self._factory = worker_factory
        self._changed = threading.Condition()
        self._workers: dict[HTTPWorker, _Slot] = {}
        self._waiting: deque[PoolRequest] = deque()
        self._closed = False
        self._reaper: threading.Thread | None = None

    def acquire(self, request: PoolRequest) -> HTTPWorker:
        deadline = time.monotonic() + self.limits.wait_timeout
        with self._changed:
            self._check_request(request)
            # 尚未领取空闲容量的队首不占等待预算，避免突发请求误报队满。
            available = self.limits.max_workers - len(self._workers) + sum(
                slot.state == "idle" for slot in self._workers.values())
            if len(self._waiting) >= self.limits.max_pending + available:
                raise ModelRequestError("模型请求等待队列已满，请稍后重试")
            self._waiting.append(request)
        try:
            worker = self._wait_for_worker(request, deadline)
            try:
                worker.start()
                with self._changed:
                    self._check_request(request)
            except BaseException:
                self.release(request, worker, healthy=False)
                raise
            return worker
        finally:
            with self._changed:
                if request in self._waiting:
                    self._waiting.remove(request)
                self._changed.notify_all()

    def _check_request(self, request: PoolRequest) -> None:
        if request.canceled.is_set():
            raise ModelRequestCancelled("模型请求已取消")
        if self._closed:
            raise ModelRequestError("模型 HTTP 进程池已关闭")

    def _wait_for_worker(self, request: PoolRequest, deadline: float) -> HTTPWorker:
        while True:
            stale = []
            with self._changed:
                self._check_request(request)
                if time.monotonic() >= deadline:
                    raise ModelRequestError("模型请求等待进程池超时，请稍后重试或调整并发上限")
                if self._waiting and self._waiting[0] is request:
                    for worker, slot in self._workers.items():
                        if slot.state == "idle" and not worker.alive():
                            slot.state = "retiring"
                            stale.append(worker)
                    if not stale:
                        worker = self._reserve(request)
                        if worker is not None:
                            self._waiting.popleft()
                            self._changed.notify_all()
                            return worker
                if not stale:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ModelRequestError("模型请求等待进程池超时，请稍后重试或调整并发上限")
                    self._changed.wait(remaining)
            for worker in stale:
                self._retire(worker)

    def _reserve(self, request: PoolRequest) -> HTTPWorker | None:
        for worker, slot in self._workers.items():
            if slot.state == "idle":
                slot.state, slot.request = "busy", request
                return worker
        if len(self._workers) >= self.limits.max_workers:
            return None
        worker = self._factory()
        self._workers[worker] = _Slot(request)
        if self._reaper is None:
            # 宿主回收线程不能保留首个请求的会话或插件快照。
            self._reaper = threading.Thread(target=contextvars.Context().run,
                                           args=(self._reap,), name="model-http-idle", daemon=True)
            try:
                self._reaper.start()
            except BaseException:
                self._reaper = None
                self._workers.pop(worker)
                raise
        return worker

    def cancel(self, request: PoolRequest) -> None:
        with self._changed:
            request.canceled.set()
            workers = [worker for worker, slot in self._workers.items() if slot.request is request]
            for worker in workers:
                self._workers[worker].state = "retiring"
            if request in self._waiting:
                self._waiting.remove(request)
            self._changed.notify_all()
        for worker in workers:
            try:
                worker.abort()
            except Exception as exc:
                report_error("model_http.pool.abort", exc)

    def release(self, request: PoolRequest, worker: HTTPWorker, *, healthy: bool) -> None:
        with self._changed:
            slot = self._workers.get(worker)
            if slot is None or slot.request is not request:
                return
            if healthy and not self._closed and not request.canceled.is_set() and slot.state == "busy":
                slot.state, slot.request, slot.idle_at = "idle", None, time.monotonic()
                self._changed.notify_all()
                return
            slot.state = "retiring"
        self._retire(worker)

    def _retire(self, worker: HTTPWorker) -> None:
        try:
            worker.close()
        except Exception as exc:
            report_error("model_http.pool.retire", exc)
        with self._changed:
            if not worker.alive():
                self._workers.pop(worker, None)
            self._changed.notify_all()

    def _reap(self) -> None:
        while True:
            with self._changed:
                if self._closed or not self._workers:
                    self._reaper = None
                    return
                now = time.monotonic()
                stale = [worker for worker, slot in self._workers.items()
                         if (slot.state == "idle" and now - slot.idle_at >= self.limits.idle_timeout)
                         or (slot.state == "retiring" and not worker.alive())]
                if not stale:
                    deadlines = [slot.idle_at + self.limits.idle_timeout for slot in self._workers.values()
                                 if slot.state == "idle"]
                    delay = max(0.001, min(deadlines) - now) if deadlines else None
                    self._changed.wait(delay)
                    continue
                for worker in stale:
                    self._workers[worker].state = "retiring"
            for worker in stale:
                self._retire(worker)

    def snapshot(self) -> dict:
        with self._changed:
            return {"workers": len(self._workers), "waiting": len(self._waiting),
                    **{state: sum(slot.state == state for slot in self._workers.values())
                       for state in ("busy", "idle", "retiring")},
                    "pids": tuple(worker.process.pid for worker in self._workers
                                  if worker.process is not None)}

    def dispose(self) -> None:
        with self._changed:
            self._closed = True
            for request in self._waiting:
                request.canceled.set()
            self._waiting.clear()
            workers = list(self._workers)
            for slot in self._workers.values():
                if slot.request is not None:
                    slot.request.canceled.set()
                slot.state = "retiring"
            reaper = self._reaper
            self._changed.notify_all()
        for worker in workers:
            try:
                worker.abort()
            except Exception as exc:
                report_error("model_http.pool.dispose", exc)
        for worker in workers:
            self._retire(worker)
        if reaper is not None and reaper is not threading.current_thread():
            reaper.join(timeout=2)
