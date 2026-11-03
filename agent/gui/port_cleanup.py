# -*- coding: utf-8 -*-
"""端口占用清理：识别监听进程、强杀进程树并等待端口释放。"""
from __future__ import annotations

import os
import signal
import subprocess
import time
from typing import Any, List

from agent.core.error_report import report_error


def _local_host(endpoint: str) -> str:
    """从 netstat 的本地端点里取地址部分；兼容 IPv6 方括号。"""
    text = str(endpoint or "").strip()
    if text.startswith("["):
        end = text.find("]")
        return text[1:end] if end > 1 else text
    return text.rsplit(":", 1)[0] if ":" in text else text


def _host_matches(endpoint: str, host: str) -> bool:
    """判断监听地址是否属于目标 host；通配监听对所有 host 生效。"""
    local = _local_host(endpoint).strip("[]").lower()
    wanted = str(host or "").strip().strip("[]").lower()
    if local in ("", "0.0.0.0", "::", "*"):
        return True
    if wanted in ("localhost", "127.0.0.1"):
        return local in ("localhost", "127.0.0.1", "::1")
    return local == wanted


def listening_pids(host: str, port: int) -> List[int]:
    """返回监听指定端口的进程号；只读取系统监听表。"""
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        pids: List[int] = []
        for line in str(result.stdout or "").splitlines():
            parts = line.split()
            if len(parts) < 5 or parts[0].upper() != "TCP":
                continue
            if parts[3].upper() != "LISTENING":
                continue
            try:
                local_port = int(parts[1].rsplit(":", 1)[1])
                pid = int(parts[4])
            except (IndexError, ValueError) as exc:
                report_error("agent.gui.launcher.port_table", exc)
                continue
            if local_port == int(port) and _host_matches(parts[1], host) and pid > 0 and pid not in pids:
                pids.append(pid)
        return pids
    for command in (
        ["lsof", "-nP", f"-iTCP:{int(port)}", "-sTCP:LISTEN", "-t"],
        ["fuser", "-n", "tcp", str(int(port))],
    ):
        try:
            result = subprocess.run(
                command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, timeout=5, check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            report_error("agent.gui.launcher.port_owner", exc)
            continue
        if result.returncode != 0:
            continue
        pids = []
        for token in str(result.stdout or "").split():
            try:
                pid = int(token)
            except ValueError as exc:
                report_error("agent.gui.launcher.port_pid", exc)
                continue
            if pid > 0 and pid not in pids:
                pids.append(pid)
        if pids:
            return pids
    return []


def kill_pid(pid: int) -> bool:
    """强制结束进程树；失败返回 False。"""
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=8, check=False,
            )
            return result.returncode == 0
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
            time.sleep(0.1)
        os.kill(pid, signal.SIGKILL)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def force_stop_agent_port(host: str, port: int, is_agent_health: Any) -> bool:
    """结束占用端口的旧 AI Agent 进程，等待端口释放。"""
    pids = listening_pids(host, port)
    if not pids:
        return False
    for pid in pids:
        if not kill_pid(pid):
            return False
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not is_agent_health(host, port, timeout=0.3):
            return not listening_pids(host, port)
        time.sleep(0.1)
    return not listening_pids(host, port)


