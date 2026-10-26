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


@dataclass
class LoginLimiter:
    max_failures: int = 5
    lock_seconds: int = 300
    _buckets: Dict[str, _Bucket] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def allowed(self, key: str) -> bool:
        with self._lock:
            bucket = self._buckets.get(str(key))
            return not bucket or bucket.locked_until <= time.time()

    def fail(self, key: str) -> None:
        with self._lock:
            bucket = self._buckets.setdefault(str(key), _Bucket())
            bucket.failures += 1
            if bucket.failures >= max(1, int(self.max_failures)):
                bucket.locked_until = time.time() + max(1, int(self.lock_seconds))
                bucket.failures = 0

    def success(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(str(key), None)
