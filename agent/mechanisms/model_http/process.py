"""HTTP 工作进程的启动、终止与管道回收。"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from contextlib import suppress
from pathlib import Path

from agent.core.error_report import report_error
from agent.mechanisms.providers.base import ModelRequestCancelled, ModelRequestError


def worker_command() -> list[str]:
    executable = Path(sys.executable)
    if executable.name.lower() == "pythonw.exe":
        executable = executable.with_name("python.exe")
    return [str(executable), "-B", "-m", "agent.mechanisms.model_http.worker"]


class HTTPWorker:
    """终止不获取管道锁；启动和回收串行，防止迟到创建逃逸。"""

    def __init__(self) -> None:
        self.process: subprocess.Popen[bytes] | None = None
        self._aborted = threading.Event()
        self._lock = threading.Lock()

    def alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self) -> None:
        with self._lock:
            if self._aborted.is_set():
                raise ModelRequestCancelled("模型请求已取消")
            if self.process is None:
                self.process = subprocess.Popen(
                    worker_command(), cwd=str(Path(__file__).resolve().parents[3]),
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            if self._aborted.is_set():
                self.abort()
                raise ModelRequestCancelled("模型请求已取消")
            if not self.alive():
                raise ModelRequestError("模型 HTTP 工作进程已退出")

    def abort(self) -> None:
        self._aborted.set()
        process = self.process
        if process is not None and process.poll() is None:
            try:
                process.kill()
            except ProcessLookupError:
                return

    def close(self) -> None:
        self.abort()
        with self._lock:
            process = self.process
            if process is None:
                return
            try:
                process.wait(timeout=2)
            finally:
                for stream in (process.stdin, process.stdout):
                    if stream is not None:
                        try:
                            # 终止可能发生在请求体尚未写完时。
                            with suppress(BrokenPipeError):
                                stream.close()
                        except OSError as exc:
                            report_error("model_http.close", exc)
