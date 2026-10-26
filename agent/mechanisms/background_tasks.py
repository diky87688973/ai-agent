# -*- coding: utf-8 -*-
"""按 cid 隔离的后台任务队列与进程执行器。

任务状态只在本进程内存中保存；进程退出即全部丢弃。每个任务由
`BackgroundTaskExecutor` 启动独立进程组，输出进入有界 ring，模型通过
`background_task` 工具读取未消费部分。
"""
from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, Sequence

from agent.core.error_report import report_error

MAX_RUNNING_PER_CID = 10
MAX_PENDING_PER_CID = 10
MAX_OUTPUT_BYTES = 256 * 1024
WAIT_DEFAULT_MS = 30_000
WAIT_MAX_MS = 600_000

QUEUED = "queued"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
TIMED_OUT = "timed_out"
CANCELLED = "cancelled"
TERMINAL = frozenset({COMPLETED, FAILED, TIMED_OUT, CANCELLED})


@dataclass
class BackgroundTaskRecord:
    task_id: str
    cid: str
    argv: List[str]
    cwd: str
    timeout_sec: int
    label: str
    batch: str
    created_at: float
    deadline_at: float
    status: str = QUEUED
    pid: Optional[int] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    exit_code: Optional[int] = None
    detail: str = ""
    cancel_requested: bool = False
    stdout: bytearray = field(default_factory=bytearray)
    stderr: bytearray = field(default_factory=bytearray)
    stdout_cursor: int = 0
    stderr_cursor: int = 0
    truncated: bool = False
    process: Optional[subprocess.Popen] = None
    settled: threading.Event = field(default_factory=threading.Event)

    def public(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "pid": self.pid,
            "label": self.label,
            "batch": self.batch,
            "argv": list(self.argv),
            "cwd": self.cwd,
            "timeout_sec": self.timeout_sec,
            "created_at": self.created_at,
            "deadline_at": self.deadline_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exit_code": self.exit_code,
            "detail": self.detail,
            "cancel_requested": self.cancel_requested,
        }


class BackgroundTaskExecutor:
    """启动独立进程组的子进程，并负责杀整棵进程树。"""

    @staticmethod
    def spawn(argv: Sequence[str], cwd: Path, env: Dict[str, str]) -> subprocess.Popen:
        if os.name == "nt":
            flags = 0x08000000  # CREATE_NO_WINDOW
            return subprocess.Popen(
                list(argv),
                cwd=str(cwd),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=flags,
            )
        return subprocess.Popen(
            list(argv),
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

    @staticmethod
    def kill_tree(pid: int, process: Optional[subprocess.Popen] = None) -> bool:
        if process is not None and process.poll() is not None:
            return True
        if os.name == "nt":
            try:
                result = subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                report_error("agent.mechanisms.background_tasks.kill_tree", exc,
                             pid=pid)
                result = None
            if result is not None and result.returncode in (0, 128):
                return True
            if result is not None:
                report_error(
                    "agent.mechanisms.background_tasks.kill_tree",
                    RuntimeError(f"taskkill exit={result.returncode}"),
                    pid=pid,
                )
            if process is not None:
                try:
                    process.kill()
                except OSError as exc:
                    report_error("agent.mechanisms.background_tasks.kill_fallback", exc,
                                 pid=pid)
                    return False
            return False
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError) as exc:
            report_error("agent.mechanisms.background_tasks.kill_tree", exc, pid=pid)
            if process is not None:
                try:
                    process.kill()
                except OSError as fallback:
                    report_error("agent.mechanisms.background_tasks.kill_fallback",
                                 fallback, pid=pid)
                    return False
            return False
        deadline = time.time() + 2
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
            except (ProcessLookupError, PermissionError):
                return True
            time.sleep(0.05)
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError) as exc:
            report_error("agent.mechanisms.background_tasks.kill_tree", exc, pid=pid)
            return False
        return True


@dataclass
class _CidQueue:
    pending: Deque[BackgroundTaskRecord] = field(default_factory=deque)
    running: Dict[str, BackgroundTaskRecord] = field(default_factory=dict)
    history: List[BackgroundTaskRecord] = field(default_factory=list)


class BackgroundTaskManager:
    """后台任务注册表、调度器与通知源。"""

    def __init__(
        self,
        allowed_roots: Sequence[Path],
        *,
        notice: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self._roots = [Path(root).resolve() for root in allowed_roots]
        self._notice = notice
        self._lock = threading.RLock()
        self._changed = threading.Condition(self._lock)
        self._queues: Dict[str, _CidQueue] = {}
        self._notice_batches: Dict[str, set[str]] = {}
        self._shutdown = threading.Event()
        self._scheduler = threading.Thread(
            target=self._schedule_loop, name="background-tasks-scheduler", daemon=True
        )
        self._scheduler.start()

    def active_total(self) -> int:
        with self._lock:
            return sum(self._active_locked(q) for q in self._queues.values())

    def set_notice(self, notice: Optional[Callable[[str, str], None]]) -> None:
        with self._lock:
            self._notice = notice

    def _queue(self, cid: str) -> _CidQueue:
        key = str(cid or "").strip()
        if not key:
            raise ValueError("缺少会话 id")
        return self._queues.setdefault(key, _CidQueue())

    def _active_locked(self, q: _CidQueue) -> int:
        return len(q.pending) + len(q.running)

    def create(self, cid: str, argv: Sequence[str], cwd: str, timeout_sec: int,
               label: str = "", batch: str = "") -> Dict[str, Any]:
        argv = [str(item) for item in argv] if isinstance(argv, (list, tuple)) else []
        argv = [item for item in argv]
        label = str(label or "").strip()
        batch = str(batch or "").strip()
        if not argv or any(not item or "\x00" in item for item in argv):
            raise ValueError("argv 必须是非空字符串数组")
        if not label:
            raise ValueError("缺少 label（任务小标题）")
        if len(label) > 120:
            raise ValueError("label 不能超过 120 字")
        try:
            timeout = int(timeout_sec)
        except (TypeError, ValueError) as exc:
            raise ValueError("timeout_sec 必须是整数") from exc
        if not 1 <= timeout <= 86400:
            raise ValueError("timeout_sec 必须在 1..86400")
        target = self._resolve_cwd(cwd)
        now = time.time()
        with self._lock:
            q = self._queue(cid)
            existing = list(q.pending) + list(q.running.values()) + q.history
            if batch and not any(item.batch == batch for item in existing):
                return {"ok": False, "error": "batch_not_found", "batch": batch}
            if not batch:
                batch = f"batch-{uuid.uuid4().hex[:10]}"
            if len(q.pending) >= MAX_PENDING_PER_CID:
                return {"ok": False, "error": "task_queue_full", "limit": MAX_PENDING_PER_CID}
            record = BackgroundTaskRecord(
                task_id=f"bt-{uuid.uuid4().hex[:12]}",
                cid=str(cid).strip(),
                argv=argv,
                cwd=str(target),
                timeout_sec=timeout,
                label=label,
                batch=batch,
                created_at=now,
                deadline_at=now + timeout,
            )
            q.pending.append(record)
            notices: List[str] = []
            self._schedule_locked(q, notices)
            result = {"ok": True, "task": record.public()}
        self._emit_notices(notices)
        return result

    def list_tasks(self, cid: str, batch: str, task_id: str = "",
                   status: str = "") -> Dict[str, Any]:
        batch = str(batch or "").strip()
        task_id = str(task_id or "").strip()
        status = str(status or "").strip()
        if not batch:
            raise ValueError("缺少 batch（批次号）")
        with self._lock:
            q = self._queue(cid)
            all_rows = list(q.pending) + list(q.running.values()) + list(q.history)
            batch_rows = [item for item in all_rows if item.batch == batch]
            counts: Dict[str, int] = {}
            for item in batch_rows:
                counts[item.status] = counts.get(item.status, 0) + 1
            rows = batch_rows
            if task_id:
                rows = [item for item in rows if item.task_id == task_id]
            if status:
                rows = [item for item in rows if item.status == status]
            rows.sort(key=lambda item: item.created_at, reverse=True)
            return {
                "ok": True,
                "tasks": [item.public() for item in rows],
                "total": len(rows),
                "counts": counts,
            }

    def snapshot(self, cid: str) -> Dict[str, Any]:
        with self._lock:
            q = self._queue(cid)
            rows = list(q.pending) + list(q.running.values()) + list(q.history)
            rows.sort(key=lambda item: item.created_at, reverse=True)
            counts: Dict[str, int] = {}
            for item in rows:
                counts[item.status] = counts.get(item.status, 0) + 1
            return {"ok": True, "tasks": [item.public() for item in rows], "counts": counts}

    def cancel(self, cid: str, task_id: str, reason: str = "") -> Dict[str, Any]:
        task_id = str(task_id or "").strip()
        reason = str(reason or "").strip()
        notices: List[str] = []
        with self._lock:
            q = self._queue(cid)
            for pending in list(q.pending):
                if pending.task_id == task_id:
                    q.pending.remove(pending)
                    self._settle_locked(q, pending, CANCELLED, reason or "cancelled", notices)
                    result = {"ok": True, "task": pending.public()}
                    break
            else:
                item = q.running.get(task_id)
                if item is None:
                    old = next((row for row in q.history if row.task_id == task_id), None)
                    if old is None:
                        return {"ok": False, "error": "task_not_found"}
                    return {"ok": True, "task": old.public()}
                if item.cancel_requested:
                    return {"ok": True, "task": item.public()}
                item.cancel_requested = True
                item.detail = reason or "cancelled by user"
                if item.pid:
                    BackgroundTaskExecutor.kill_tree(item.pid, item.process)
                result = {"ok": True, "task": item.public()}
        self._emit_notices(notices)
        return result

    def output(self, cid: str, task_id: str, wait: bool = False, timeout_ms: int = WAIT_DEFAULT_MS) -> Dict[str, Any]:
        task_id = str(task_id or "").strip()
        timeout = max(0, min(int(timeout_ms or 0), WAIT_MAX_MS))
        deadline = time.monotonic() + timeout / 1000.0
        with self._lock:
            q = self._queue(cid)
            item = q.running.get(task_id)
            if item is None:
                item = next((old for old in q.history if old.task_id == task_id), None)
            if item is None:
                return {"ok": False, "error": "task_not_found"}
            if wait:
                while item.status not in TERMINAL:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self._changed.wait(remaining)
            out = self._read_locked(item)
            return {"ok": True, **out}

    def shutdown(self) -> None:
        self._shutdown.set()
        with self._lock:
            items = [item for q in self._queues.values() for item in q.running.values()]
        for item in items:
            if item.pid:
                BackgroundTaskExecutor.kill_tree(item.pid)
        for item in items:
            item.settled.wait(3)

    # ── 调度与生命周期 ─────────────────────────────────────
    def _schedule_loop(self) -> None:
        while not self._shutdown.wait(0.05):
            notices: List[str] = []
            with self._lock:
                for q in list(self._queues.values()):
                    self._schedule_locked(q, notices)
            self._emit_notices(notices)

    def _schedule_locked(self, q: _CidQueue, notices: Optional[List[str]] = None) -> None:
        notices = notices if notices is not None else []
        while len(q.running) < MAX_RUNNING_PER_CID and q.pending:
            record = q.pending[0]
            if record.deadline_at <= time.time():
                q.pending.popleft()
                self._settle_locked(q, record, TIMED_OUT, "queue_timeout", notices)
                continue
            q.pending.popleft()
            self._start_locked(q, record, notices)

    def _start_locked(self, q: _CidQueue, record: BackgroundTaskRecord, notices: List[str]) -> None:
        record.status = RUNNING
        record.started_at = time.time()
        q.running[record.task_id] = record
        env = self._env()
        try:
            proc = BackgroundTaskExecutor.spawn(record.argv, Path(record.cwd), env)
        except (OSError, ValueError) as exc:
            record.detail = f"spawn_failed: {exc}"
            self._settle_locked(q, record, FAILED, record.detail, notices)
            return
        record.process = proc
        record.pid = proc.pid
        threading.Thread(target=self._read_stream, args=(record, proc.stdout, "stdout"),
                         name=f"bt-out-{record.task_id}", daemon=True).start()
        threading.Thread(target=self._read_stream, args=(record, proc.stderr, "stderr"),
                         name=f"bt-err-{record.task_id}", daemon=True).start()
        threading.Thread(target=self._watch, args=(q, record),
                         name=f"bt-wait-{record.task_id}", daemon=True).start()

    def _read_stream(self, record: BackgroundTaskRecord, stream: Any, channel: str) -> None:
        if stream is None:
            return
        target = record.stdout if channel == "stdout" else record.stderr
        try:
            while True:
                chunk = stream.read(8192)
                if not chunk:
                    break
                with self._lock:
                    target.extend(chunk)
                    if len(target) > MAX_OUTPUT_BYTES:
                        drop = len(target) - MAX_OUTPUT_BYTES
                        del target[:drop]
                        record.truncated = True
                    self._changed.notify_all()
        except (OSError, ValueError) as exc:
            report_error("agent.mechanisms.background_tasks.read", exc, task_id=record.task_id)
        finally:
            try:
                stream.close()
            except OSError as exc:
                report_error("agent.mechanisms.background_tasks.close", exc, task_id=record.task_id)

    def _watch(self, q: _CidQueue, record: BackgroundTaskRecord) -> None:
        proc = record.process
        if proc is None:
            return
        remaining = max(0.0, record.deadline_at - time.time())
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            record.cancel_requested = True
            BackgroundTaskExecutor.kill_tree(proc.pid, proc)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired as exc:
                report_error("agent.mechanisms.background_tasks.timeout_wait", exc,
                             task_id=record.task_id)
            notices: List[str] = []
            with self._lock:
                self._settle_locked(q, record, TIMED_OUT, "execution_timeout", notices)
            self._emit_notices(notices)
            return
        notices = []
        with self._lock:
            if record.status == RUNNING:
                if record.cancel_requested:
                    self._settle_locked(q, record, CANCELLED, record.detail or "cancelled", notices)
                elif proc.returncode == 0:
                    self._settle_locked(q, record, COMPLETED, "", notices)
                else:
                    self._settle_locked(q, record, FAILED, f"exit_code: {proc.returncode}", notices)
        self._emit_notices(notices)

    def _settle_locked(self, q: _CidQueue, record: BackgroundTaskRecord,
                       status: str, detail: str = "", notices: Optional[List[str]] = None) -> None:
        if record.status in TERMINAL:
            return
        record.status = status
        record.detail = detail
        record.finished_at = time.time()
        if record.process is not None:
            record.exit_code = record.process.returncode
        q.running.pop(record.task_id, None)
        if record not in q.history:
            q.history.append(record)
        record.settled.set()
        self._changed.notify_all()
        if notices is not None:
            self._notice_batches.setdefault(record.cid, set()).add(record.batch)
            if self._active_locked(q) == 0:
                notices.append(record.cid)

    def _emit_notices(self, notices: List[str]) -> None:
        if not notices or self._notice is None:
            return
        for cid in dict.fromkeys(notices):
            batches = sorted(self._notice_batches.pop(cid, set()))
            batch_text = "、".join(batches) if batches else "未知批次"
            text = (
                "<<系统通知>>\n"
                "本消息为 任务管理器 触发的系统通知\n"
                f"任务批次：{batch_text} 已完结，请查看结果。"
            )
            try:
                self._notice(cid, text)
            except Exception as exc:
                report_error("agent.mechanisms.background_tasks.notice", exc, conversation_id=cid)

    # ── 输出与沙箱 ─────────────────────────────────────────
    def _read_locked(self, record: BackgroundTaskRecord) -> Dict[str, Any]:
        out = bytes(record.stdout[record.stdout_cursor:]).decode("utf-8", "replace")
        err = bytes(record.stderr[record.stderr_cursor:]).decode("utf-8", "replace")
        record.stdout_cursor = len(record.stdout)
        record.stderr_cursor = len(record.stderr)
        return {
            "task_id": record.task_id,
            "status": record.status,
            "output": out,
            "stderr": err,
            "truncated": record.truncated,
            "exit_code": record.exit_code,
        }

    def _resolve_cwd(self, cwd: str) -> Path:
        raw = str(cwd or "").strip()
        if not raw:
            if not self._roots:
                raise ValueError("没有允许的工作目录")
            target = self._roots[0]
        else:
            target = Path(raw).expanduser().resolve()
        for root in self._roots:
            if target == root or root in target.parents:
                return target
        raise ValueError("cwd_outside_allowed_roots")

    @staticmethod
    def _env() -> Dict[str, str]:
        # 后台子进程只继承定位系统/用户目录所需的变量，不继承凭据。
        # 这不是文件、网络或权限隔离，不能替代 OS 沙箱。
        allowed = {
            "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR",
            "COMSPEC", "TEMP", "TMP", "HOME", "LANG", "LC_ALL", "TERM",
            "LOCALAPPDATA", "APPDATA", "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
            "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)",
            "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "OS",
            "USERNAME", "USERDOMAIN", "TMPDIR",
            "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME",
        }
        env = {key: value for key, value in os.environ.items()
               if key.upper() in allowed}
        env.setdefault("PATH", os.environ.get("PATH", ""))
        return env
