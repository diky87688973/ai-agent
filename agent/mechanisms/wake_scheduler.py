# -*- coding: utf-8 -*-
"""会话唤醒调度：单线程定时器、持久化任务与队列投递。

任务只由本管理器的一个线程计时；到期后经注入的 submit 回调交给会话网格。
事实日志仍是唯一真相，调度任务只保存注册信息与投递状态。
"""
from __future__ import annotations

import json
import math
import os
import shutil
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from agent.core.error_report import report_error

#: 任务状态。claimed 只表示正在投递，不是终态。
STATUS_SCHEDULED = "scheduled"
STATUS_CLAIMED = "claimed"
STATUS_DELIVERED = "delivered"
STATUS_CANCELED = "canceled"
STATUS_FAILED = "failed"
TERMINAL = frozenset({STATUS_DELIVERED, STATUS_CANCELED, STATUS_FAILED})

#: 单条 reminder 的长度上限，避免调度文件被单条任务撑大。
MAX_REMINDER_CHARS = 4000

#: 单次等待上限；系统休眠或墙钟跳变后重新计算。
MAX_WAIT_SECONDS = 1.0

#: 终态任务保留上限；超过后按更新时间淘汰最旧的终态任务。
MAX_TERMINAL_JOBS = 200


@dataclass
class WakeJob:
    job_id: str
    target_cid: str
    owner_cid: str
    due_at: float
    reminder: str
    status: str
    created_at: float
    updated_at: float
    last_error: str = ""

    def public(self) -> Dict[str, Any]:
        return asdict(self)


class WakeJobStore:
    """jobs.json 的原子读写；损坏文件留诊断并另存，不阻塞进程启动。"""

    def __init__(self, storage_dir: Path) -> None:
        self.path = Path(storage_dir) / "jobs.json"
        self._path = self.path

    def load(self) -> List[WakeJob]:
        if not self._path.is_file():
            return []
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            report_error("agent.mechanisms.wake_scheduler.load", exc,
                         path=str(self._path))
            self._quarantine()
            return []
        rows = raw.get("jobs") if isinstance(raw, dict) else None
        out: List[WakeJob] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            try:
                out.append(WakeJob(
                    job_id=str(row["job_id"]),
                    target_cid=str(row["target_cid"]),
                    owner_cid=str(row.get("owner_cid") or ""),
                    due_at=float(row["due_at"]),
                    reminder=str(row["reminder"]),
                    status=str(row.get("status") or STATUS_SCHEDULED),
                    created_at=float(row.get("created_at") or 0),
                    updated_at=float(row.get("updated_at") or 0),
                    last_error=str(row.get("last_error") or ""),
                ))
            except (KeyError, TypeError, ValueError) as exc:
                report_error("agent.mechanisms.wake_scheduler.row", exc,
                             path=str(self._path))
        return out

    def save(self, jobs: List[WakeJob]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._path.with_name(f".{self._path.name}.{os.getpid()}.tmp")
        payload = {"jobs": [job.public() for job in jobs]}
        try:
            temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
            os.replace(temp, self._path)
        except OSError:
            try:
                temp.unlink(missing_ok=True)
            except OSError as cleanup:
                report_error("agent.mechanisms.wake_scheduler.save_cleanup", cleanup,
                             path=str(temp))
            raise

    def _quarantine(self) -> None:
        try:
            broken = self._path.with_name(f"{self._path.name}.broken.{int(time.time())}")
            os.replace(self._path, broken)
        except OSError as exc:
            report_error("agent.mechanisms.wake_scheduler.quarantine", exc,
                         path=str(self._path))


class _SchedulerProcessLock:
    """跨进程单实例锁；目录创建原子，持有者 PID 用于回收崩溃后的残留锁。"""

    def __init__(self, storage_dir: Path) -> None:
        self.path = Path(storage_dir) / "scheduler.lock"
        self._token = uuid.uuid4().hex

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                self.path.mkdir()
            except FileExistsError:
                holder = self._read_holder()
                if holder and _pid_alive(int(holder.get("pid") or 0)):
                    return False
                try:
                    shutil.rmtree(self.path)
                except OSError as exc:
                    report_error("agent.mechanisms.wake_scheduler.lock_reclaim", exc,
                                 path=str(self.path))
                    return False
                continue
            try:
                (self.path / "holder.json").write_text(
                    json.dumps({"pid": os.getpid(), "token": self._token}),
                    encoding="utf-8")
            except OSError as exc:
                report_error("agent.mechanisms.wake_scheduler.lock_write", exc,
                             path=str(self.path))
                try:
                    shutil.rmtree(self.path)
                except OSError as cleanup:
                    report_error("agent.mechanisms.wake_scheduler.lock_cleanup",
                                 cleanup, path=str(self.path))
                return False
            return True
        return False

    def release(self) -> None:
        holder = self._read_holder()
        if holder and holder.get("token") == self._token:
            try:
                shutil.rmtree(self.path)
            except OSError as exc:
                report_error("agent.mechanisms.wake_scheduler.lock_release", exc,
                             path=str(self.path))

    def _read_holder(self) -> Dict[str, Any]:
        try:
            raw = json.loads((self.path / "holder.json").read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except (OSError, ValueError):
            return {}


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        return _windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _windows_pid_alive(pid: int) -> bool:
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
    handle = kernel32.OpenProcess(process_query_limited, False, int(pid))
    if not handle:
        return ctypes.get_last_error() == error_access_denied
    try:
        code = wintypes.DWORD(0)
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


class WakeScheduler:
    """单线程唤醒调度器；可注入 submit、时钟与目标校验以便测试。"""

    def __init__(
        self,
        storage_dir: Path,
        *,
        submit: Callable[..., Dict[str, Any]],
        delivered: Optional[Callable[[str, str], bool]] = None,
        target_exists: Optional[Callable[[str], bool]] = None,
        now_fn: Callable[[], float] = time.time,
    ) -> None:
        self._store = WakeJobStore(Path(storage_dir))
        self._submit = submit
        self._delivered = delivered
        self._target_exists = target_exists
        self._now = now_fn
        self._lock = threading.RLock()
        self._changed = threading.Condition(self._lock)
        self._jobs: Dict[str, WakeJob] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._process_lock = _SchedulerProcessLock(self._store.path.parent)
        self._owner = False
        self._start_attempted = False
        for job in self._store.load():
            self._jobs[job.job_id] = job

    # ── 生命周期 ──────────────────────────────────────────

    def start(self) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return True
            self._start_attempted = True
            if not self._process_lock.acquire():
                self._owner = False
                report_error("agent.mechanisms.wake_scheduler.lock_busy",
                             "另一个进程正在运行唤醒调度器",
                             path=str(self._process_lock.path))
                return False
            self._owner = True
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._loop, name="wake-scheduler", daemon=True)
            self._thread.start()
        self.run_due()
        return True

    def stop(self) -> None:
        self._stop.set()
        with self._changed:
            self._changed.notify_all()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        if self._owner:
            self._process_lock.release()
            self._owner = False

    # ── 注册 / 查询 / 取消 ─────────────────────────────────

    def schedule(self, *, target_cid: str, owner_cid: str, due_at: float,
                 reminder: str) -> Dict[str, Any]:
        if self._start_attempted and not self._owner:
            raise RuntimeError("另一个进程正在运行唤醒调度器")
        target = str(target_cid or "").strip()
        owner = str(owner_cid or "").strip()
        text = str(reminder or "").strip()
        if not target or not owner:
            raise ValueError("target_cid 与 owner_cid 不能为空")
        if not text:
            raise ValueError("reminder 不能为空")
        if len(text) > MAX_REMINDER_CHARS:
            raise ValueError(f"reminder 不能超过 {MAX_REMINDER_CHARS} 字")
        due = float(due_at)
        now = float(self._now())
        if not math.isfinite(due) or due <= now:
            raise ValueError("到期时间必须晚于当前时间")
        if target != owner and self._target_exists is not None and not self._target_exists(target):
            raise ValueError("目标会话不存在")
        job = WakeJob(
            job_id="wake-" + uuid.uuid4().hex[:12],
            target_cid=target,
            owner_cid=owner,
            due_at=due,
            reminder=text,
            status=STATUS_SCHEDULED,
            created_at=now,
            updated_at=now,
        )
        with self._changed:
            self._jobs[job.job_id] = job
            self._save_locked()
            self._changed.notify_all()
        return job.public()

    def schedule_seconds(self, seconds: Any, *, target_cid: str,
                         owner_cid: str, reminder: str) -> Dict[str, Any]:
        try:
            delay = float(seconds)
        except (TypeError, ValueError) as exc:
            raise ValueError("seconds 必须是数字") from exc
        if not math.isfinite(delay) or delay <= 0:
            raise ValueError("seconds 必须是大于 0 的有限数字")
        return self.schedule(target_cid=target_cid, owner_cid=owner_cid,
                             due_at=self._now() + delay, reminder=reminder)

    def schedule_at(self, at: Any, *, target_cid: str,
                    owner_cid: str, reminder: str) -> Dict[str, Any]:
        return self.schedule(target_cid=target_cid, owner_cid=owner_cid,
                             due_at=parse_due_at(at, self._now()), reminder=reminder)

    def cancel(self, job_id: str, *, owner_cid: str = "") -> Dict[str, Any]:
        if self._start_attempted and not self._owner:
            raise RuntimeError("另一个进程正在运行唤醒调度器")
        ident = str(job_id or "").strip()
        if not ident:
            raise ValueError("job_id 不能为空")
        with self._changed:
            job = self._jobs.get(ident)
            if job is None:
                raise ValueError("任务不存在")
            if owner_cid and job.owner_cid != str(owner_cid):
                raise ValueError("任务不属于当前会话")
            if job.status in TERMINAL:
                return job.public()
            job.status = STATUS_CANCELED
            job.updated_at = float(self._now())
            self._save_locked()
            self._changed.notify_all()
            return job.public()

    def list_jobs(self, *, target_cid: str = "", owner_cid: str = "") -> List[Dict[str, Any]]:
        with self._lock:
            rows = list(self._jobs.values())
        if target_cid:
            rows = [job for job in rows if job.target_cid == str(target_cid)]
        if owner_cid:
            rows = [job for job in rows if job.owner_cid == str(owner_cid)]
        rows.sort(key=lambda job: (job.due_at, job.created_at))
        return [job.public() for job in rows]

    # ── 调度循环 ──────────────────────────────────────────

    def run_due(self, now: Optional[float] = None) -> List[Dict[str, Any]]:
        """投递所有到期任务；返回本次实际投递的任务。"""
        current = float(self._now() if now is None else now)
        due: List[WakeJob] = []
        with self._changed:
            for job in list(self._jobs.values()):
                if job.status not in (STATUS_SCHEDULED, STATUS_CLAIMED):
                    continue
                if job.due_at > current:
                    continue
                if job.status == STATUS_CLAIMED and self._is_delivered(job):
                    job.status = STATUS_DELIVERED
                    job.updated_at = current
                    continue
                job.status = STATUS_CLAIMED
                job.updated_at = current
                due.append(job)
            if due:
                self._save_locked()
        delivered: List[Dict[str, Any]] = []
        for job in due:
            if self._deliver(job, current):
                delivered.append(job.public())
        return delivered

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_due()
            except Exception as exc:  # 调度线程不能因单条任务退出
                report_error("agent.mechanisms.wake_scheduler.loop", exc)
            with self._changed:
                if self._stop.is_set():
                    return
                now = float(self._now())
                next_due = min(
                    (job.due_at for job in self._jobs.values()
                     if job.status in (STATUS_SCHEDULED, STATUS_CLAIMED)),
                    default=now + MAX_WAIT_SECONDS,
                )
                self._changed.wait(timeout=max(0.01, min(MAX_WAIT_SECONDS,
                                                           next_due - now)))

    def _deliver(self, job: WakeJob, now: float) -> bool:
        if job.target_cid != job.owner_cid and self._target_exists is not None \
                and not self._target_exists(job.target_cid):
            self._settle(job, STATUS_FAILED, "目标会话不存在", now)
            return False
        with self._lock:
            current = self._jobs.get(job.job_id)
            if current is None or current.status != STATUS_CLAIMED:
                return False
        if self._is_delivered(job):
            self._settle(job, STATUS_DELIVERED, "", now)
            return True
        message = {
            "content": job.reminder,
            "meta": {"kind": "wake", "source": "wake_scheduler",
                     "wake_job_id": job.job_id},
        }
        try:
            result = self._submit(job.target_cid, message, origin="system",
                                  dedupe_key=job.job_id)
        except Exception as exc:
            report_error("agent.mechanisms.wake_scheduler.deliver", exc,
                         conversation_id=job.target_cid, job_id=job.job_id)
            self._settle(job, STATUS_FAILED, f"{type(exc).__name__}: {exc}", now)
            return False
        if not isinstance(result, dict) or not (result.get("run_id") or result.get("queued")):
            self._settle(job, STATUS_FAILED, "投递被拒绝", now)
            return False
        self._settle(job, STATUS_DELIVERED, "", now)
        return True

    def _is_delivered(self, job: WakeJob) -> bool:
        if self._delivered is None:
            return False
        try:
            return bool(self._delivered(job.target_cid, job.job_id))
        except Exception as exc:
            report_error("agent.mechanisms.wake_scheduler.delivered", exc,
                         conversation_id=job.target_cid, job_id=job.job_id)
            return False

    def _settle(self, job: WakeJob, status: str, error: str, now: float) -> None:
        with self._changed:
            current = self._jobs.get(job.job_id)
            if current is None:
                return
            if current.status == STATUS_CANCELED:
                return
            current.status = status
            current.last_error = str(error or "")
            current.updated_at = now
            self._save_locked()
            self._changed.notify_all()

    def _prune_locked(self) -> None:
        terminal = [job for job in self._jobs.values() if job.status in TERMINAL]
        overflow = len(terminal) - MAX_TERMINAL_JOBS
        if overflow <= 0:
            return
        terminal.sort(key=lambda job: job.updated_at)
        for job in terminal[:overflow]:
            self._jobs.pop(job.job_id, None)

    def _save_locked(self) -> None:
        self._prune_locked()
        try:
            self._store.save(list(self._jobs.values()))
        except OSError as exc:
            report_error("agent.mechanisms.wake_scheduler.save", exc,
                         path=str(self._store.path))
            print(f"[wake] 任务落盘失败：{type(exc).__name__}: {exc}",
                  file=sys.stderr, flush=True)


def parse_due_at(value: Any, now: float) -> float:
    """解析带时区 ISO 8601；无时区按宿主本地时区解释。"""
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("at 不能为空")
    if raw.endswith(("Z", "z")):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("at 必须是 ISO 8601 时间") from exc
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    due = parsed.timestamp()
    if due <= now:
        raise ValueError("at 必须晚于当前时间")
    return due
