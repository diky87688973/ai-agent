# -*- coding: utf-8 -*-
"""本地推理服务的进程管理：懒启动、健康检查、空闲回收与崩溃重启。

模型常驻要占约 3.8 GiB 显存，因此不做常驻：首次合成时拉起，空闲到期即释放，
把显存还给画图等其他模型。
"""
from __future__ import annotations

import atexit
import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from agent.common.process_guard import adopt
from agent.common.tts_contract import TTSEngineUnavailable, TTSNotInstalled
from agent.core.error_report import report_error

#: 本机回环请求必须绕过系统代理，否则会被代理转走。
_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class ServerSupervisor:
    """一个可执行文件 + 一个模型文件的常驻服务。"""

    def __init__(self, *, exe: Path, model: Path, port: int,
                 startup_timeout: float = 20.0, idle_timeout: float = 600.0,
                 voices_dir: Optional[Path] = None) -> None:
        self._exe = Path(exe)
        self._model = Path(model)
        self._port = int(port)
        self._startup_timeout = max(1.0, float(startup_timeout))
        self._idle_timeout = max(0.0, float(idle_timeout))
        self._voices_dir = Path(voices_dir) if voices_dir is not None else None
        self._lock = threading.RLock()
        self._proc: Optional[subprocess.Popen] = None
        self._last_used = 0.0
        self._base = f"http://127.0.0.1:{self._port}"
        # 进程被强杀时只有作业对象能收尾，atexit 只兑正常退出这一种。
        atexit.register(self.stop)

    @property
    def base_url(self) -> str:
        return self._base

    def missing_reason(self) -> str:
        """返回不可启动的原因；空串表示文件齐备。"""
        if not self._exe.is_file():
            return f"推理程序不存在：{self._exe}"
        if not self._model.is_file():
            return f"模型文件不存在：{self._model}"
        return ""

    def is_running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def ensure_ready(self) -> str:
        """保证服务可接受请求并返回基地址。"""
        reason = self.missing_reason()
        if reason:
            raise TTSNotInstalled(reason)

        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                if self._healthy():
                    self._last_used = time.monotonic()
                    return self._base
                self._terminate_locked()
            self._start_locked()
            self._wait_healthy_locked()
            self._last_used = time.monotonic()
            return self._base

    def release_idle(self) -> bool:
        """空闲超时则停服；返回是否真的停了。"""
        if self._idle_timeout <= 0:
            return False
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                return False
            if time.monotonic() - self._last_used < self._idle_timeout:
                return False
            self._terminate_locked()
            return True

    def stop(self) -> None:
        with self._lock:
            self._terminate_locked()

    # ── 内部 ──────────────────────────────────────────────

    def _start_locked(self) -> None:
        argv = [str(self._exe), str(self._model),
                "--port", str(self._port), "--parallel", "1"]
        if self._voices_dir is not None:
            # 不指定时服务会把音色文件写到进程当前目录，那是项目根。
            # 目录不存在时服务不会自建，会静默退回默认目录，所以先建好。
            self._voices_dir.mkdir(parents=True, exist_ok=True)
            argv += ["--voices-dir", str(self._voices_dir)]
        try:
            self._proc = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_CREATE_NO_WINDOW,
            )
        except OSError as exc:
            self._proc = None
            raise TTSEngineUnavailable(f"启动推理服务失败：{exc}") from exc
        adopt(self._proc.pid)

    def _wait_healthy_locked(self) -> None:
        deadline = time.monotonic() + self._startup_timeout
        while time.monotonic() < deadline:
            proc = self._proc
            if proc is not None and proc.poll() is not None:
                code = proc.returncode
                self._proc = None
                raise TTSEngineUnavailable(f"推理服务启动后立即退出（退出码 {code}）")
            if self._healthy():
                return
            time.sleep(0.2)
        self._terminate_locked()
        raise TTSEngineUnavailable(
            f"推理服务在 {self._startup_timeout:.0f}s 内未就绪（端口 {self._port}）")

    def _healthy(self) -> bool:
        try:
            with _NO_PROXY.open(f"{self._base}/health", timeout=1.5) as resp:
                payload: Any = json.loads(resp.read() or b"{}")
        except (urllib.error.URLError, OSError, ValueError):
            return False
        return str(payload.get("status") or "") == "ok"

    def _terminate_locked(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            try:
                proc.kill()
                proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired) as exc:
                report_error("plugin.tts.supervisor", exc, plugin="tts")
