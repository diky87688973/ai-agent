"""会话停止操作：立即发信号、异步清理及有界终态查询。"""
from __future__ import annotations

import math
import threading
import time
import uuid
from collections import OrderedDict
from typing import Any, Callable

from agent.core.context import SERVICE_BACKGROUND_TASKS
from agent.core.error_report import report_error
from agent.core.thread_context import thread_with_context
from agent.mechanisms.background_tasks import TaskTerminationError
from agent.mechanisms.command_safety import ShellTerminationError, force_kill_active_shell_process
from agent.shell.session import resume as resume_module


class StopWaitTimeout(TimeoutError):
    """仅观察等待超时；停止操作仍可用原标识继续查询。"""

    def __init__(self, stop_id: str) -> None:
        self.stop_id = stop_id
        super().__init__(f"停止状态等待超时，清理可能仍在进行（stop_id={stop_id}）")


def validate_wait_timeout(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("停止等待时限必须是有限非负秒数")
    return float(value)


class StopCleanupError(RuntimeError):
    def __init__(self, errors: list[Exception]) -> None:
        self.failed_task_ids = [task for error in errors if isinstance(error, TaskTerminationError)
                                for task in error.task_ids]
        self.failed_process_ids = [pid for error in errors if isinstance(error, ShellTerminationError)
                                   for pid in error.pids]
        super().__init__("；".join(str(error) for error in errors))


class StopOperations:
    """由 SessionRunner 持有；未完成或失败的清理阻止同会话再次启动。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._changed = threading.Condition(self._lock)
        self._active: dict[str, dict] = {}
        self._completed: OrderedDict[str, dict] = OrderedDict()
        self._starting: dict[str, set] = {}

    def register_start(self, cid: str, control: Any) -> Callable[[], None]:
        with self._lock:
            self._starting.setdefault(cid, set()).add(control)
            item = self._active.get(cid)
            blocked = item is not None and item["state"] != "completed"
        if blocked:
            control.set()
        def remove() -> None:
            with self._lock:
                controls = self._starting.get(cid)
                if controls is not None:
                    controls.discard(control)
                    if not controls:
                        self._starting.pop(cid)
        return remove

    def busy(self, cid: str) -> bool:
        with self._lock:
            return cid in self._active

    def blocking(self, cid: str) -> bool:
        with self._lock:
            item = self._active.get(cid)
            return item is not None and item["state"] != "completed"

    def status(self, cid: str, stop_id: str) -> dict | None:
        with self._lock:
            item = self._active.get(cid) or self._completed.get(cid)
            if item is None or item["stop_id"] != stop_id:
                return None
            return {key: value for key, value in item.items() if key != "thread"}

    def wait(self, cid: str, stop_id: str, timeout: float = 30.0) -> dict:
        deadline = time.monotonic() + validate_wait_timeout(timeout)
        with self._changed:
            while True:
                item = self._active.get(cid) or self._completed.get(cid)
                if item is None or item["stop_id"] != stop_id:
                    raise OSError("停止操作不存在或已被新的停止请求替代")
                if item["state"] != "stopping":
                    return {key: value for key, value in item.items() if key != "thread"}
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise StopWaitTimeout(stop_id)
                self._changed.wait(remaining)

    def begin(self, cid: str, signal: Callable[[], None], cleanup: Callable[[], Any],
              completed: Callable[[], None], *, run_id: str = "") -> dict:
        with self._lock:
            old = self._active.get(cid)
            if old is not None and old["state"] == "stopping":
                return {key: value for key, value in old.items() if key != "thread"}
            item = {"stop_id": uuid.uuid4().hex, "state": "stopping",
                    "conversation_id": cid, "run_id": run_id, "stop_requested": False}
            self._active[cid] = item
            self._completed.pop(cid, None)
            starting = tuple(self._starting.get(cid, ()))
            self._changed.notify_all()
        try:
            for control in starting:
                control.set()
            signal()
            with self._lock:
                item["stop_requested"] = True
            thread = thread_with_context(target=self._run, args=(cid, item, cleanup, completed),
                                         name=f"session-stop-{cid[:12]}", daemon=True)
            with self._lock:
                item["thread"] = thread
            thread.start()
        except Exception as exc:
            report_error("shell.session.stop", exc, conversation_id=cid)
            self._fail(item, exc)
        with self._lock:
            return {key: value for key, value in item.items() if key != "thread"}

    def _fail(self, item: dict, error: Exception) -> None:
        with self._lock:
            item.update(state="failed", error="停止清理失败，请重试停止")
            self._changed.notify_all()
            if isinstance(error, StopCleanupError):
                item.update(failed_task_ids=error.failed_task_ids,
                            failed_process_ids=error.failed_process_ids)
                if error.failed_task_ids:
                    item["error"] = "部分后台进程未能终止，请重试停止"

    def _run(self, cid: str, item: dict, cleanup: Callable[[], Any],
             completed: Callable[[], None]) -> None:
        try:
            cleanup()
        except Exception as exc:
            report_error("shell.session.stop", exc, conversation_id=cid)
            self._fail(item, exc)
            return
        with self._lock:
            item.update(state="completed")
            self._changed.notify_all()
        try:
            completed()
        except Exception as exc:
            report_error("shell.session.stop.dispatch", exc, conversation_id=cid)
        finally:
            with self._lock:
                if self._active.get(cid) is item:
                    self._active.pop(cid)
                    self._completed[cid] = {key: value for key, value in item.items() if key != "thread"}
                    while len(self._completed) > 128:
                        self._completed.popitem(last=False)

    def join(self, timeout: float) -> bool:
        deadline = time.monotonic() + max(0, timeout)
        with self._lock:
            threads = [item.get("thread") for item in self._active.values()]
        for thread in threads:
            if thread is not None and thread.ident is not None:
                thread.join(max(0, deadline - time.monotonic()))
        with self._lock:
            return not any(item["state"] == "stopping" or
                           (item.get("thread") is not None and item["thread"].is_alive())
                           for item in self._active.values())


def cleanup_cancel(app: Any, key: str, store_for: Callable) -> None:
    errors = []
    try:
        force_kill_active_shell_process(scope=key)
    except ShellTerminationError as exc:
        errors.append(exc)
    context = getattr(app, "context", None)
    if context is not None and context.has(SERVICE_BACKGROUND_TASKS):
        tasks = context.get(SERVICE_BACKGROUND_TASKS)
        try:
            tasks.cancel_all(key, "用户终止会话")
        except TaskTerminationError as exc:
            errors.append(exc)
    store = store_for(key) or getattr(app, "store", None)
    try:
        resume_module.interrupt_confirmation(app, key, store)
    except OSError as exc:
        errors.append(exc)
    if errors:
        raise StopCleanupError(errors)


def begin_cancel(operations: StopOperations, app: Any, mesh: Any, cid: str,
                 event: Any, store_for: Callable, activate: Callable, *, run_id: str = "") -> dict:
    def completed() -> None:
        mesh.activate_queued(cid, lambda item: activate(cid, {}, queued=item), user_only=True)
    return operations.begin(cid, lambda: mesh.mark_stopped(cid, cancel=event),
                            lambda: cleanup_cancel(app, cid, store_for),
                            completed, run_id=run_id)


def cancel_check(mesh: Any, event: Any, cid: str) -> Callable[[], bool]:
    next_probe = 0.0
    stopped = False
    def check() -> bool:
        nonlocal next_probe, stopped
        if stopped or (event is not None and event.is_set()):
            return True
        now = time.monotonic()
        if now >= next_probe:
            next_probe = now + 0.1
            stopped = mesh.is_stopped(cid)
        return stopped
    return check
