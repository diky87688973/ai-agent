# -*- coding: utf-8 -*-
"""AI说话的运行时：每会话串行合成、SSE 发布、停止与计数。

一个会话一个 worker，保证段的合成与推送顺序；不同会话的 worker 并行。
worker 只做合成与发布，配置解析与文本校验在各自模块完成。
"""
from __future__ import annotations

import base64
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from agent.core.error_report import report_error

from .config import AISpeakConfig
from .provider import (
    SpeechAudio,
    SpeechEngineUnavailable,
    SpeechError,
    SpeechSynthesisError,
    TTSProvider,
)

PLUGIN_NAME = "ai_speak"
MAX_PENDING_SEGMENTS = 1024
MAX_PLAYBACK_WAITERS = 64
STOP_JOIN_SECONDS = 3.0

Publisher = Callable[[str, str, Dict[str, Any]], int]
CancelCheck = Callable[[], bool]


class SpeechBusy(SpeechError):
    """该会话待合成段达到上限。"""

    def __init__(self, queued: int, limit: int) -> None:
        self.queued = int(queued)
        self.limit = int(limit)
        super().__init__(f"待合成语音过多（{self.queued}/{self.limit}），稍后再试")


class SpeechPlaybackFailed(SpeechError):
    """同步播放没有完成：停止、错误、丢帧或超时。"""

    def __init__(self, status: str, waited_ms: int = 0) -> None:
        self.status = str(status or "failed")
        self.waited_ms = max(0, int(waited_ms))
        message = {
            "stopped": "播放被用户中止",
            "error": "前端播放失败",
            "dropped": "音频没有送达前端",
            "timeout": "等待前端播放超时",
        }.get(self.status, f"播放未完成（{self.status}）")
        super().__init__(message)


class PlaybackWaiter:
    """一次 ai_speak 调用的播放完成等待。"""

    def __init__(self, conversation_id: str, call_id: str) -> None:
        self.conversation_id = str(conversation_id or "")
        self.call_id = str(call_id or "")
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._status: Optional[str] = None
        self._started_at = time.monotonic()

    @property
    def status(self) -> Optional[str]:
        with self._lock:
            return self._status

    @property
    def waited_ms(self) -> int:
        return max(0, int((time.monotonic() - self._started_at) * 1000))

    def resolve(self, status: str) -> str:
        """首次结果生效；重复 ack 不会覆盖已完成的播放结果。"""
        value = str(status or "error")
        with self._lock:
            if self._status is None:
                self._status = value
                self._event.set()
            return self._status

    def wait(self, timeout_s: float, canceled: Optional[CancelCheck] = None) -> str:
        """等 ack；取消检查会把它收成 stopped，超时收成 timeout。"""
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        while True:
            if self._event.wait(0.05):
                return self.status or "timeout"
            if canceled is not None:
                try:
                    if canceled():
                        return self.resolve("stopped")
                except Exception as exc:
                    report_error(
                        "plugin.ai_speak.cancel_check", exc, plugin=PLUGIN_NAME,
                        conversation_id=self.conversation_id,
                    )
            if time.monotonic() >= deadline:
                return self.resolve("timeout")


@dataclass(frozen=True, slots=True)
class _SegmentJob:
    conversation_id: str
    call_id: str
    index: int
    total: int
    text: str
    voice: str


class _SessionWorker:
    """一个会话的串行合成队列。"""

    def __init__(
        self,
        runtime: "AISpeakRuntime",
        conversation_id: str,
        provider: TTSProvider,
        config: AISpeakConfig,
    ) -> None:
        self._runtime = runtime
        self._cid = conversation_id
        self._provider = provider
        self._config = config
        self._queue: "queue.Queue[Optional[Tuple[_SegmentJob, Publisher]]]" = queue.Queue(
            maxsize=MAX_PENDING_SEGMENTS
        )
        self._put_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._stop = threading.Event()
        self._generation = 0
        self._reason = ""
        self._current_publisher: Optional[Publisher] = None
        self._thread = threading.Thread(
            target=self._run, name=f"ai-speak-{conversation_id[:8]}", daemon=True
        )
        self._thread.start()

    @property
    def conversation_id(self) -> str:
        return self._cid

    def enqueue(self, jobs: List[_SegmentJob], publisher: Publisher) -> None:
        with self._put_lock:
            if self._stop.is_set():
                raise SpeechEngineUnavailable("语音 worker 已停止")
            free = self._queue.maxsize - self._queue.qsize()
            if free < len(jobs):
                raise SpeechBusy(self._queue.qsize(), self._queue.maxsize)
            for job in jobs:
                self._queue.put_nowait((job, publisher))

    def stop(self, reason: str) -> None:
        with self._state_lock:
            self._generation += 1
            self._reason = str(reason or "stopped")
            self._stop.set()
        self._drain()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass

    def _drain(self) -> None:
        while True:
            try:
                item = self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                return
            if item is not None:
                self._runtime._mark_dequeued(self._cid)

    def join(self, timeout: float) -> bool:
        self._thread.join(timeout=max(0.0, timeout))
        return not self._thread.is_alive()

    @property
    def current_publisher(self) -> Optional[Publisher]:
        return self._current_publisher

    def _publish_raw(self, publisher: Optional[Publisher], event: str,
                     payload: Dict[str, Any]) -> int:
        if publisher is None:
            return 0
        try:
            return int(publisher(PLUGIN_NAME, event, payload))
        except Exception as exc:
            report_error("plugin.ai_speak.publish", exc, plugin=PLUGIN_NAME)
            return 0

    def _segment_payload(self, job: _SegmentJob, audio: SpeechAudio) -> Dict[str, Any]:
        encoded = base64.b64encode(audio.data).decode("ascii")
        return {
            "conversation_id": job.conversation_id,
            "call_id": job.call_id,
            "index": job.index,
            "total": job.total,
            "text": job.text,
            "voice": audio.voice or job.voice,
            "mime": audio.mime,
            "audio": encoded,
            "bytes": len(audio.data),
            "gap_ms": self._config.play_interval_ms,
        }

    def _error_payload(self, job: _SegmentJob, exc: Exception) -> Dict[str, Any]:
        return {
            "conversation_id": job.conversation_id,
            "call_id": job.call_id,
            "index": job.index,
            "code": "synthesis_failed",
            "message": f"{type(exc).__name__}: {exc}",
        }

    def _run(self) -> None:
        try:
            while True:
                item = self._queue.get()
                try:
                    if item is None:
                        return
                    job, publisher = item
                    self._current_publisher = publisher
                    self._runtime._mark_dequeued(self._cid)
                    if self._stop.is_set():
                        continue
                    try:
                        audio = self._provider.synthesize(
                            self._runtime.speech_text(job.text),
                            voice=job.voice,
                            timeout_s=self._runtime.synthesis_timeout_s,
                        )
                    except SpeechSynthesisError as exc:
                        self._runtime._mark_failed(self._cid, exc)
                        self._runtime._finish_playback(
                            job.conversation_id, job.call_id, "error")
                        self._publish_raw(publisher, "error", self._error_payload(job, exc))
                        continue
                    except SpeechEngineUnavailable as exc:
                        self._runtime._mark_failed(self._cid, exc)
                        self._runtime._finish_playback(
                            job.conversation_id, job.call_id, "error")
                        self._publish_raw(publisher, "error", self._error_payload(job, exc))
                        self._stop.set()
                        return
                    except Exception as exc:
                        self._runtime._mark_failed(self._cid, exc)
                        self._runtime._finish_playback(
                            job.conversation_id, job.call_id, "error")
                        self._publish_raw(publisher, "error", self._error_payload(job, exc))
                        continue

                    if self._stop.is_set():
                        continue
                    delivered = self._publish_raw(
                        publisher, "segment", self._segment_payload(job, audio)
                    )
                    if delivered <= 0:
                        self._runtime._mark_dropped(self._cid)
                        self._runtime._finish_playback(
                            job.conversation_id, job.call_id, "dropped")
                        self._stop.set()
                        self._reason = "no_sse_channel"
                        return
                    self._runtime._mark_spoken(self._cid)
                finally:
                    self._queue.task_done()
        finally:
            self._runtime._drop_worker(self._cid, self)

    def _stop_payload(self) -> Dict[str, Any]:
        return {
            "conversation_id": self._cid,
            "reason": self._reason or "stopped",
        }

    def publish_stop(self) -> None:
        self._publish_raw(self._current_publisher, "stop", self._stop_payload())


class AISpeakRuntime:
    """插件运行时：配置、引擎、每会话 worker、发布器与统计。"""

    def __init__(
        self,
        config: AISpeakConfig,
        provider: TTSProvider,
        *,
        synthesis_timeout_s: float = 15.0,
    ) -> None:
        self._config = config
        self._provider = provider
        self._synthesis_timeout_s = float(synthesis_timeout_s)
        self._lock = threading.Lock()
        self._stats_lock = threading.Lock()
        self._playback_lock = threading.Lock()
        self._workers: Dict[str, _SessionWorker] = {}
        self._playback: Dict[Tuple[str, str], PlaybackWaiter] = {}
        self._stats: Dict[str, Dict[str, int]] = {}
        self._totals = {"queued": 0, "spoken": 0, "failed": 0, "dropped": 0}
        self._last_error: Optional[Dict[str, str]] = None
        self._disposed = False

    # ── 属性 ──

    @property
    def config(self) -> AISpeakConfig:
        return self._config

    @property
    def synthesis_timeout_s(self) -> float:
        return self._synthesis_timeout_s

    def speech_text(self, text: str) -> str:
        from .text import to_speech_text

        return to_speech_text(text)

    def provider_ready(self) -> bool:
        return bool(self._provider.available())

    # ── 入队 ──

    def enqueue(
        self,
        conversation_id: str,
        call_id: str,
        segments: Tuple[str, ...],
        voice: str,
        publisher: Publisher,
    ) -> int:
        cid = str(conversation_id or "").strip()
        if not cid:
            raise SpeechEngineUnavailable("缺少会话 id")
        if self._disposed:
            raise SpeechEngineUnavailable("语音插件已卸载")
        if not segments:
            return 0
        jobs = [
            _SegmentJob(
                conversation_id=cid,
                call_id=str(call_id or ""),
                index=index,
                total=len(segments),
                text=text,
                voice=str(voice or self._config.voice),
            )
            for index, text in enumerate(segments)
        ]
        with self._lock:
            if self._disposed:
                raise SpeechEngineUnavailable("语音插件已卸载")
            worker = self._workers.get(cid)
            if worker is None:
                worker = _SessionWorker(self, cid, self._provider, self._config)
                self._workers[cid] = worker
            with self._stats_lock:
                bucket = self._stats.setdefault(
                    cid, {"queued": 0, "spoken": 0, "failed": 0, "dropped": 0}
                )
                bucket["queued"] += len(jobs)
                self._totals["queued"] += len(jobs)
            try:
                worker.enqueue(jobs, publisher)
            except Exception:
                with self._stats_lock:
                    bucket["queued"] = max(0, bucket["queued"] - len(jobs))
                    self._totals["queued"] = max(0, self._totals["queued"] - len(jobs))
                raise
        return len(jobs)

    # ── 播放完成等待 ──

    def begin_playback(self, conversation_id: str, call_id: str) -> PlaybackWaiter:
        """登记一次播放等待；必须在 enqueue 之前调用，避免 ack 先到。"""
        cid = str(conversation_id or "").strip()
        call = str(call_id or "").strip()
        if not cid or not call:
            raise ValueError("同步播放需要 conversation_id 与 call_id")
        with self._playback_lock:
            if self._disposed:
                raise SpeechEngineUnavailable("语音插件已卸载")
            key = (cid, call)
            existing = self._playback.get(key)
            if existing is not None:
                return existing
            if len(self._playback) >= MAX_PLAYBACK_WAITERS:
                oldest_key = max(
                    self._playback,
                    key=lambda item: self._playback[item].waited_ms,
                )
                self._playback.pop(oldest_key).resolve("dropped")
            waiter = PlaybackWaiter(cid, call)
            self._playback[key] = waiter
            return waiter

    def ack_playback(self, conversation_id: str, call_id: str, status: str) -> bool:
        """前端 ack；未知/已完成的调用返回 False，不影响播放器。"""
        call = str(call_id or "").strip()
        if not call:
            return False
        value = str(status or "error").strip().lower()
        if value not in ("played", "stopped", "error", "incomplete"):
            value = "error"
        cid = str(conversation_id or "").strip()
        with self._playback_lock:
            key = (cid, call)
            waiter = self._playback.pop(key, None)
            if waiter is None and not cid:
                matches = [item for item in self._playback if item[1] == call]
                if len(matches) == 1:
                    waiter = self._playback.pop(matches[0])
            if waiter is not None:
                waiter.resolve("dropped" if value == "incomplete" else value)
                return True
        return False

    def forget_playback(self, conversation_id: str, call_id: str) -> None:
        """工具结束等待后清理登记；ack 已经先到时是空操作。"""
        with self._playback_lock:
            self._playback.pop((str(conversation_id or ""), str(call_id or "")), None)

    def _finish_playback(self, conversation_id: str, call_id: str, status: str) -> None:
        """worker 侧失败信号：合成错误、无连接或丢段。"""
        with self._playback_lock:
            waiter = self._playback.pop(
                (str(conversation_id or ""), str(call_id or "")), None
            )
        if waiter is not None:
            waiter.resolve(status)

    def _resolve_playback_cid(self, conversation_id: str, status: str) -> None:
        cid = str(conversation_id or "")
        with self._playback_lock:
            keys = [key for key in self._playback if key[0] == cid]
            waiters = [self._playback.pop(key) for key in keys]
        for waiter in waiters:
            waiter.resolve(status)

    def _resolve_all_playback(self, status: str) -> None:
        with self._playback_lock:
            waiters = list(self._playback.values())
            self._playback.clear()
        for waiter in waiters:
            waiter.resolve(status)

    # ── 停止 ──

    def stop_cid(self, conversation_id: str, reason: str = "stopped") -> None:
        cid = str(conversation_id or "").strip()
        if not cid:
            return
        self._resolve_playback_cid(cid, "stopped")
        with self._lock:
            worker = self._workers.pop(cid, None)
        if worker is None:
            return
        worker.stop(reason)
        worker.publish_stop()
        worker.join(0.2)

    def dispose(self) -> None:
        with self._lock:
            if self._disposed:
                return
            self._disposed = True
            workers = list(self._workers.values())
            self._workers.clear()
        self._resolve_all_playback("stopped")
        for worker in workers:
            worker.stop("plugin_unloaded")
            worker.publish_stop()
        deadline = time.monotonic() + STOP_JOIN_SECONDS
        for worker in workers:
            remaining = max(0.0, deadline - time.monotonic())
            if not worker.join(remaining):
                report_error(
                    "plugin.ai_speak.stop",
                    RuntimeError("合成线程未在期限内退出"),
                    plugin=PLUGIN_NAME,
                    conversation_id=worker.conversation_id,
                )

    # ── worker 回调与统计 ──

    def _drop_worker(self, cid: str, worker: _SessionWorker) -> None:
        with self._lock:
            if self._workers.get(cid) is worker:
                self._workers.pop(cid, None)

    def _mark_dequeued(self, cid: str) -> None:
        with self._stats_lock:
            bucket = self._stats.setdefault(
                cid, {"queued": 0, "spoken": 0, "failed": 0, "dropped": 0}
            )
            if bucket["queued"] > 0:
                bucket["queued"] -= 1

    def _mark_spoken(self, cid: str) -> None:
        with self._stats_lock:
            bucket = self._stats.setdefault(
                cid, {"queued": 0, "spoken": 0, "failed": 0, "dropped": 0}
            )
            bucket["spoken"] += 1
            self._totals["spoken"] += 1

    def _mark_failed(self, cid: str, exc: Exception) -> None:
        with self._stats_lock:
            bucket = self._stats.setdefault(
                cid, {"queued": 0, "spoken": 0, "failed": 0, "dropped": 0}
            )
            bucket["failed"] += 1
            self._totals["failed"] += 1
            self._last_error = {
                "code": "synthesis_failed",
                "message": f"{type(exc).__name__}: {exc}",
            }
        report_error("plugin.ai_speak.synthesis", exc, plugin=PLUGIN_NAME, conversation_id=cid)

    def _mark_dropped(self, cid: str) -> None:
        with self._stats_lock:
            bucket = self._stats.setdefault(
                cid, {"queued": 0, "spoken": 0, "failed": 0, "dropped": 0}
            )
            bucket["dropped"] += 1
            self._totals["dropped"] += 1

    # ── 状态 ──

    def status(self) -> Dict[str, Any]:
        with self._stats_lock:
            sessions = [
                {"conversation_id": cid, **dict(values)}
                for cid, values in sorted(self._stats.items())
            ]
            totals = dict(self._totals)
            last_error = dict(self._last_error) if self._last_error else None
        with self._playback_lock:
            playback_waiting = len(self._playback)
        return {
            "engine": self._config.engine,
            "engine_ready": self.provider_ready(),
            "voice": self._config.voice,
            "max_segment_chars": self._config.max_segment_chars,
            "play_interval_ms": self._config.play_interval_ms,
            "sync_playback": self._config.sync_playback,
            "playback_waiting": playback_waiting,
            "sessions": sessions,
            "totals": totals,
            "last_error": last_error,
        }
