# -*- coding: utf-8 -*-
"""跨进程产物锁：同一份共享产物同时只允许一个进程写。

锁用 `mkdir` 的原子性实现，Windows 与 POSIX 行为一致，不依赖 msvcrt / fcntl。
持有者信息写在锁目录内的 `holder.json`：持有进程被强杀后，下一个申请者按 PID
存活判定回收，残留锁不会把流水线永久卡住。

用法：

    from artifact_lock import ArtifactLock, LockBusy

    with ArtifactLock(ROOT, "coverage", purpose="check_coverage"):
        ...

    ArtifactLock(ROOT, "ci", purpose="ci.py").acquire(wait_s=60)
"""
from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

#: 锁目录相对仓库根的位置
LOCK_DIRNAME = ".locks"

#: 锁目录已建好、`holder.json` 还没落地的最短宽限时间
WRITE_GRACE_S = 5.0

#: `holder.json` 文件名
HOLDER_FILE = "holder.json"


@dataclass(frozen=True)
class Holder:
    """锁的持有者：进程号、用途、加锁时刻、唯一令牌。"""

    pid: int
    purpose: str
    since: float
    token: str

    def age_s(self) -> float:
        return max(0.0, time.time() - self.since)

    def describe(self) -> str:
        purpose = self.purpose or "unknown"
        return f"pid={self.pid}（{purpose}，已持有 {self.age_s():.1f}s）"


class LockBusy(RuntimeError):
    """锁被别的进程占用；`holder` 为 None 表示持有者信息不可读。"""

    def __init__(self, name: str, holder: Optional[Holder], waited_s: float) -> None:
        self.name = name
        self.holder = holder
        self.waited_s = waited_s
        who = holder.describe() if holder else "持有者信息不可读"
        super().__init__(f"产物锁 {name} 被占用：{who}；已等 {waited_s:.1f}s")


def parse_holder(text: str) -> Optional[Holder]:
    """解析 `holder.json`；不是合法持有者记录时返回 None。"""
    try:
        raw = json.loads(text)
    except (ValueError, TypeError):
        # 文本不是合法 JSON：这条记录不能当有效持有者
        return None
    if not isinstance(raw, dict):
        return None
    try:
        pid = int(raw.get("pid", 0))
        since = float(raw.get("since", 0.0))
    except (TypeError, ValueError):
        # 字段缺失或类型不对：同样按不可读处理，由调用方按年龄兜底
        return None
    if pid <= 0:
        return None
    return Holder(
        pid=pid,
        purpose=str(raw.get("purpose") or ""),
        since=since,
        token=str(raw.get("token") or ""),
    )


def pid_alive(pid: int) -> bool:
    """进程是否还活着；判断不了时按存活处理，避免误拆别人的锁。"""
    if pid <= 0:
        return False
    if os.name == "nt":
        return _windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        # 进程号不存在：持有者已退出
        return False
    except PermissionError:
        # 存在但不属于当前用户
        return True
    return True


def _windows_pid_alive(pid: int) -> bool:
    """`OpenProcess` + `GetExitCodeProcess`：Windows 上不能用 `os.kill(pid, 0)`。"""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE,
                                            ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    process_query_limited = 0x1000
    still_active = 259
    error_access_denied = 5
    handle = kernel32.OpenProcess(process_query_limited, False, pid)
    if not handle:
        # 权限不足说明进程在，只是不允许查询；其余错误按已退出处理
        return ctypes.get_last_error() == error_access_denied
    try:
        code = wintypes.DWORD(0)
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


class ArtifactLock:
    """某个产物的独占锁；`acquire` 成功后才能写，`release` 幂等。"""

    def __init__(self, root: Path, name: str, purpose: str = "",
                 lock_root: Optional[Path] = None) -> None:
        self.root = Path(root)
        self.name = name
        self.purpose = purpose
        base = Path(lock_root) if lock_root is not None else self.root / LOCK_DIRNAME
        self.path = base / f"{name}.lock"
        self._holder: Optional[Holder] = None

    @property
    def held(self) -> bool:
        return self._holder is not None

    @property
    def holder(self) -> Optional[Holder]:
        return self._holder

    def acquire(self, wait_s: float = 0.0, poll_s: float = 0.1,
                force: bool = False) -> None:
        """拿锁；失败抛 `LockBusy`。`force` 无视存活判定强拆现有锁。"""
        started = time.monotonic()
        while True:
            holder = self._try_create()
            if holder is not None:
                self._holder = holder
                return
            text, current = self._read()
            if force or self._reclaimable(current):
                if self._reclaim(text):
                    continue
            waited = time.monotonic() - started
            if waited >= wait_s:
                raise LockBusy(self.name, current, waited)
            time.sleep(poll_s)

    def release(self) -> None:
        """释放自己持有的锁；令牌对不上说明已被回收，保持现状。"""
        holder, self._holder = self._holder, None
        if holder is None:
            return
        _text, current = self._read()
        if current is None or current.token != holder.token:
            return
        shutil.rmtree(self.path, ignore_errors=True)

    def __enter__(self) -> "ArtifactLock":
        self.acquire()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()

    def _try_create(self) -> Optional[Holder]:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.mkdir()
        except FileExistsError:
            # 目录已存在：别人先拿到了锁
            return None
        holder = Holder(pid=os.getpid(), purpose=self.purpose,
                        since=time.time(), token=uuid.uuid4().hex)
        payload = json.dumps({
            "pid": holder.pid,
            "purpose": holder.purpose,
            "since": holder.since,
            "token": holder.token,
        }, ensure_ascii=False)
        try:
            (self.path / HOLDER_FILE).write_text(payload, encoding="utf-8")
        except OSError:
            # 半成品锁由宽限时间兜底，先清掉自己这一层
            shutil.rmtree(self.path, ignore_errors=True)
            raise
        return holder

    def _read(self) -> Tuple[str, Optional[Holder]]:
        try:
            text = (self.path / HOLDER_FILE).read_text(encoding="utf-8")
        except (FileNotFoundError, NotADirectoryError):
            # 锁目录刚建好、持有者信息还没落地
            return "", None
        except OSError:
            # 读不到内容时按年龄判定，不让权限问题把锁判成"有人在写"
            return "", None
        return text, parse_holder(text)

    def _reclaimable(self, holder: Optional[Holder]) -> bool:
        if holder is None:
            return _age_of(self.path) >= WRITE_GRACE_S
        return not pid_alive(holder.pid)

    def _reclaim(self, expected: str) -> bool:
        current, _holder = self._read()
        if current != expected:
            return False
        # 先改名再删：改名是原子的，删旧目录的同时不会误伤刚建好的新锁
        graveyard = self.path.with_name(f"{self.path.name}.stale.{uuid.uuid4().hex}")
        try:
            os.replace(self.path, graveyard)
        except OSError:
            # 目录已被别人回收，或改名失败：交给下一次轮询重试
            return False
        shutil.rmtree(graveyard, ignore_errors=True)
        return True


def _age_of(path: Path) -> float:
    try:
        return time.time() - path.stat().st_mtime
    except OSError:
        # 锁已被别的进程回收
        return 0.0
