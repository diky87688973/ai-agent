"""模型流的可取消等待与传输资源终止契约。"""
from __future__ import annotations

import contextvars
import queue
import threading
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from agent.core.error_report import report_error
from agent.core.thread_context import thread_with_context


class StreamControl(threading.Event):
    """单次模型调用拥有取消状态，传输层登记自己的终止动作。"""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._callbacks: set[Callable[[], None]] = set()

    @property
    def stopped(self) -> threading.Event:
        return self

    def set(self) -> None:
        self.stop()

    def register(self, abort: Callable[[], None]) -> Callable[[], None]:
        with self._lock:
            stopped = self.stopped.is_set()
            if not stopped:
                self._callbacks.add(abort)
        if stopped:
            abort()

        def remove() -> None:
            with self._lock:
                self._callbacks.discard(abort)

        return remove

    def stop(self) -> None:
        with self._lock:
            super().set()
            callbacks = tuple(self._callbacks)
            self._callbacks.clear()

        def abort_one(abort: Callable[[], None]) -> None:
            try:
                abort()
            except Exception as exc:
                report_error("core.stream_control.abort", exc)

        for abort in callbacks:
            thread_with_context(target=abort_one, args=(abort,),
                                name="model-stream-abort", daemon=True).start()


_CONTROL: contextvars.ContextVar[StreamControl | None] = contextvars.ContextVar(
    "model_stream_control", default=None)


@contextmanager
def stream_control_scope(control: StreamControl) -> Iterator[None]:
    """将当前执行链上的同步传输绑定到同一个取消令牌。"""
    token = _CONTROL.set(control)
    try:
        yield
    finally:
        _CONTROL.reset(token)


def register_stream_abort(abort: Callable[[], None]) -> Callable[[], None]:
    """传输适配器登记当前调用的终止动作；返回注销函数。"""
    control = _CONTROL.get()
    return control.register(abort) if control is not None else lambda: None


def interruptible_stream(open_stream: Callable[[], Iterator[Any]],
                         canceled: Callable[[], bool]) -> Iterator[Any]:
    """隔离阻塞读取；只有消费线程能把增量提交给回合与事实流。"""
    if canceled():
        return
    control = StreamControl()
    parent = _CONTROL.get()
    detach = parent.register(control.stop) if parent is not None else lambda: None
    frames: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=16)

    def put(kind: str, value: Any = None) -> None:
        while not control.stopped.is_set():
            try:
                frames.put((kind, value), timeout=0.05)
                return
            except queue.Full:
                if control.is_set():
                    return

    def read() -> None:
        token = _CONTROL.set(control)
        try:
            if control.is_set():
                return
            stream = open_stream()
            try:
                for frame in stream:
                    if control.stopped.is_set():
                        break
                    put("frame", frame)
            finally:
                close = getattr(stream, "close", None)
                if callable(close):
                    close()
        except Exception as exc:
            if not control.is_set():
                report_error("core.stream_control.read", exc)
            put("error", exc)
        finally:
            put("end")
            _CONTROL.reset(token)

    worker = None
    try:
        worker = thread_with_context(target=read, name="model-stream-read", daemon=True)
        worker.start()
        while not canceled():
            try:
                kind, value = frames.get(timeout=0.05)
            except queue.Empty:
                if canceled():
                    return
                continue
            if canceled() or kind == "end":
                return
            if kind == "error":
                raise value
            yield value
    finally:
        control.stop()
        detach()
        if worker is not None and worker.ident is not None:
            worker.join(timeout=0.2)
