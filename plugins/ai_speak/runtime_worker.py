# -*- coding: utf-8 -*-
"""AI说话 worker：播放等待、每会话串行合成与 SSE 发布。

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


class SpeechSynthesisFailed(SpeechError):
    """语音合成失败：没有音频可播；detail 是引擎给出的原因。"""

    def __init__(self, detail: str = "") -> None:
        self.detail = str(detail or "")
        message = "语音合成失败"
        if self.detail:
            message += f"：{self.detail}"
        super().__init__(message)


class SpeechPlaybackFailed(SpeechError):
    """播放没有完成：播放出错、停止、丢帧或超时。"""

    def __init__(self, status: str, waited_ms: int = 0, detail: str = "") -> None:
        self.status = str(status or "failed")
        self.waited_ms = max(0, int(waited_ms))
        self.detail = str(detail or "")
        message = {
            "stopped": "播放被用户中止",
            "error": "播放失败",
            "dropped": "音频没有送达前端",
            "timeout": "等待前端播放超时",
        }.get(self.status, f"播放未完成（{self.status}）")
        if self.detail:
            message += f"：{self.detail}"
        super().__init__(message)


class PlaybackWaiter:
    """一次 ai_speak 调用的播放完成等待。"""

    def __init__(self, conversation_id: str, call_id: str) -> None:
        self.conversation_id = str(conversation_id or "")
        self.call_id = str(call_id or "")
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._status: Optional[str] = None
        self._detail = ""
        self._started_at = time.monotonic()

    @property
    def status(self) -> Optional[str]:
        with self._lock:
            return self._status

    @property
    def waited_ms(self) -> int:
        return max(0, int((time.monotonic() - self._started_at) * 1000))

    @property
    def detail(self) -> str:
        with self._lock:
            return self._detail

    def resolve(self, status: str, detail: str = "") -> str:
        """首次结果生效；重复 ack 不会覆盖已完成的播放结果。"""
        value = str(status or "error")
        with self._lock:
            if self._status is None:
                self._status = value
                self._detail = str(detail or "")
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
        runtime: Any,
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
            return

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
            "speed": self._config.speed,
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
                            speed=self._config.speed,
                        )
                    except SpeechSynthesisError as exc:
                        self._runtime._mark_failed(self._cid, exc)
                        self._runtime._finish_playback(
                            job.conversation_id, job.call_id, "synthesis_failed",
                            f"{type(exc).__name__}: {exc}")
                        self._publish_raw(publisher, "error", self._error_payload(job, exc))
                        continue
                    except SpeechEngineUnavailable as exc:
                        self._runtime._mark_failed(self._cid, exc)
                        self._runtime._finish_playback(
                            job.conversation_id, job.call_id, "synthesis_failed",
                            f"{type(exc).__name__}: {exc}")
                        self._publish_raw(publisher, "error", self._error_payload(job, exc))
                        self._stop.set()
                        return
                    except Exception as exc:
                        report_error("plugin.ai_speak.synthesis", exc)
                        self._runtime._mark_failed(self._cid, exc)
                        self._runtime._finish_playback(
                            job.conversation_id, job.call_id, "synthesis_failed",
                            f"{type(exc).__name__}: {exc}")
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
