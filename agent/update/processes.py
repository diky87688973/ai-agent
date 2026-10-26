# -*- coding: utf-8 -*-
"""更新器的进程边界：按安装路径查找并停止旧 GUI 进程。"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List

from agent.update.logs import log_event

TH32CS_SNAPPROCESS = 0x00000002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001
MAX_PATH = 32767


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.c_ulong),
        ("cntUsage", ctypes.c_ulong),
        ("th32ProcessID", ctypes.c_ulong),
        ("th32DefaultHeapID", ctypes.c_void_p),
        ("th32ModuleID", ctypes.c_ulong),
        ("cntThreads", ctypes.c_ulong),
        ("th32ParentProcessID", ctypes.c_ulong),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", ctypes.c_ulong),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


def _same_path(left: str, right: Path) -> bool:
    try:
        return os.path.normcase(str(Path(left).resolve())) == os.path.normcase(str(right.resolve()))
    except OSError:
        return False


def _kernel32():
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateToolhelp32Snapshot.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel32.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel32.Process32FirstW.restype = ctypes.c_int
    kernel32.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel32.Process32NextW.restype = ctypes.c_int
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)
    ]
    kernel32.QueryFullProcessImageNameW.restype = ctypes.c_int
    kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    kernel32.TerminateProcess.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    return kernel32


def _process_image_path(pid: int) -> str:
    kernel32 = _kernel32()
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return ""
    try:
        size = ctypes.c_ulong(MAX_PATH)
        buffer = ctypes.create_unicode_buffer(MAX_PATH)
        if not kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)):
            return ""
        return str(buffer.value or "")
    finally:
        kernel32.CloseHandle(handle)


def find_pids(executable: Path) -> List[int]:
    """返回当前正在运行的、映像路径等于 executable 的进程。"""
    target = Path(executable)
    if os.name != "nt" or not target.is_file():
        return []
    kernel32 = ctypes.windll.kernel32
    kernel32 = _kernel32()
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot in (0, ctypes.c_void_p(-1).value):
        return []
    entries = _PROCESSENTRY32W()
    entries.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
    found: List[int] = []
    try:
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entries)):
            return []
        while True:
            image = _process_image_path(int(entries.th32ProcessID))
            if image and _same_path(image, target):
                found.append(int(entries.th32ProcessID))
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entries)):
                break
    finally:
        kernel32.CloseHandle(snapshot)
    return found


def stop_old_launcher(root: Path, wait_seconds: float = 3.0) -> List[int]:
    """旧 GUI 还在时等待并终止；返回实际终止的 PID。"""
    executable = Path(root) / "agent-gui.exe"
    try:
        old = find_pids(executable)
        if not old:
            return []
        time.sleep(max(0.0, float(wait_seconds)))
        old = find_pids(executable)
        if not old:
            return []
        kernel32 = _kernel32()
        killed: List[int] = []
        for pid in old:
            handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, int(pid))
            if not handle:
                log_event(root, "old_launcher_stop_failed", level="error",
                          pid=int(pid), error="OpenProcess failed")
                continue
            try:
                if kernel32.TerminateProcess(handle, 1):
                    killed.append(int(pid))
                else:
                    log_event(root, "old_launcher_stop_failed", level="error",
                              pid=int(pid), error="TerminateProcess failed")
            finally:
                kernel32.CloseHandle(handle)
        return killed
    except Exception as exc:
        log_event(root, "old_launcher_stop_failed", level="error",
                  error=f"{type(exc).__name__}: {exc}")
        raise


def cleanup_launcher_archives(root: Path, attempts: int = 5,
                              delay: float = 0.2) -> list[str]:
    """删除旧 launcher 归档；旧进程刚终止时短暂重试。"""
    directory = Path(root) / "updates" / "launcher"
    if not directory.is_dir():
        return []
    removed: list[str] = []
    for archived in sorted(directory.glob("agent-gui.exe.old-*")):
        for attempt in range(max(1, int(attempts))):
            try:
                archived.unlink()
                removed.append(archived.name)
                break
            except FileNotFoundError:
                break
            except OSError as exc:
                if attempt + 1 >= attempts:
                    log_event(root, "launcher_archive_cleanup_failed",
                              level="error", name=archived.name, error=str(exc))
                    break
                time.sleep(max(0.0, float(delay)))
    return removed


def launch_after_update(root: Path) -> bool:
    """更新结束后启动新 GUI；只由 updater 在已停止旧 GUI 时调用。"""
    executable = Path(root) / "agent-gui.exe"
    if os.name != "nt" or not executable.is_file():
        return False
    try:
        subprocess.Popen(
            [str(executable)],
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    except OSError:
        return False
    return True


def runtime_available() -> bool:
    """当前环境是否是 Windows（供测试和调用方判断）。"""
    return os.name == "nt" and sys.platform.startswith("win")
