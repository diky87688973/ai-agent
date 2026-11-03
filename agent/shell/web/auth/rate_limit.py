# -*- coding: utf-8 -*-
"""登录失败限流：按来源与账户做短时指数退避。"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class _Bucket:
    failures: int = 0
    locked_until: float = 0.0
    updated: float = 0.0


@dataclass
class LoginLimiter:
    max_failures: int = 5
    lock_seconds: int = 300
    max_buckets: int = 4096
    _buckets: Dict[str, _Bucket] = field(default_factory=dict)
    _overflow_failures: int = 0
    _overflow_locked_until: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _prune_locked(self, now: float) -> None:
        # 先清已过期锁；桶数仍有上限，按最近更新时间淘汰最旧的未锁定桶。
        for key in [k for k, b in self._buckets.items()
                    if b.locked_until and b.locked_until <= now]:
            self._buckets.pop(key, None)
        if len(self._buckets) <= self.max_buckets:
            return
        unlocked = sorted(
            (b.updated, k) for k, b in self._buckets.items()
            if not b.locked_until or b.locked_until <= now)
        for _updated, key in unlocked:
            if len(self._buckets) <= self.max_buckets:
                break
            self._buckets.pop(key, None)

    def _overflow_fail_locked(self, now: float) -> None:
        """桶表满且全是锁定项时的共享失败计数：宁可全局限流，也不能放行。"""
        if self._overflow_locked_until > now:
            return
        self._overflow_failures += 1
        if self._overflow_failures >= max(1, int(self.max_failures)):
            self._overflow_locked_until = now + max(1, int(self.lock_seconds))
            self._overflow_failures = 0

    def allowed(self, key: str) -> bool:
        with self._lock:
            now = time.time()
            bucket = self._buckets.get(str(key))
            if bucket is not None and bucket.locked_until and bucket.locked_until <= now:
                self._buckets.pop(str(key), None)
                return True
            if bucket is None and self._overflow_locked_until > now:
                return False
            return not bucket or bucket.locked_until <= now

    def fail(self, key: str) -> None:
        key = str(key)
        with self._lock:
            now = time.time()
            self._prune_locked(now)
            if key not in self._buckets and len(self._buckets) >= self.max_buckets:
                self._overflow_fail_locked(now)
                return
            bucket = self._buckets.setdefault(key, _Bucket())
            bucket.updated = now
            bucket.failures += 1
            if bucket.failures >= max(1, int(self.max_failures)):
                bucket.locked_until = now + max(1, int(self.lock_seconds))
                bucket.failures = 0

    def success(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(str(key), None)
            self._overflow_failures = 0
            self._overflow_locked_until = 0.0
