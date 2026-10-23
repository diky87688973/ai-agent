# -*- coding: utf-8 -*-
"""AI说话运行时：配置、每会话 worker、发布器与统计。"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional, Tuple

from agent.core.error_report import report_error

from .config import AISpeakConfig
from .provider import SpeechEngineUnavailable, TTSProvider
from .runtime_worker import (
    MAX_PLAYBACK_WAITERS,
    PLUGIN_NAME,
    STOP_JOIN_SECONDS,
    PlaybackWaiter,
    Publisher,
    SpeechBusy,  # noqa: F401 - tool.py 从此导入
    SpeechPlaybackFailed,  # noqa: F401 - tool.py 从此导入
    SpeechSynthesisFailed,  # noqa: F401 - tool.py 从此导入
    _SegmentJob,
    _SessionWorker,
)


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

    def ack_playback(self, conversation_id: str, call_id: str, status: str,
                     detail: str = "") -> bool:
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
                waiter.resolve("dropped" if value == "incomplete" else value, detail)
                return True
        return False

    def forget_playback(self, conversation_id: str, call_id: str) -> None:
        """工具结束等待后清理登记；ack 已经先到时是空操作。"""
        with self._playback_lock:
            self._playback.pop((str(conversation_id or ""), str(call_id or "")), None)

    def _finish_playback(self, conversation_id: str, call_id: str, status: str,
                         detail: str = "") -> None:
        """worker 侧失败信号：合成错误、无连接或丢段。"""
        with self._playback_lock:
            waiter = self._playback.pop(
                (str(conversation_id or ""), str(call_id or "")), None
            )
        if waiter is not None:
            waiter.resolve(status, detail)

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
            "speed": self._config.speed,
            "playback_waiting": playback_waiting,
            "sessions": sessions,
            "totals": totals,
            "last_error": last_error,
        }
