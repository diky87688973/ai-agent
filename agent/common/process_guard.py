# -*- coding: utf-8 -*-
"""让子进程随父进程一起退出。

Windows 上杀掉父进程不会给子进程任何信号，常驻的推理服务会变成孤儿继续占显存。
把它们放进一个「句柄关闭即终止」的作业对象，父进程无论正常退出还是被强杀，
系统都会连带终止作业内的进程。
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Optional

_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


_kernel32: Optional[ctypes.WinDLL] = None
_job_handle: Optional[int] = None
_job_failed = False


def _kernel() -> ctypes.WinDLL:
    global _kernel32
    if _kernel32 is None:
        _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        _kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        _kernel32.SetInformationJobObject.restype = wintypes.BOOL
        _kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        _kernel32.OpenProcess.restype = wintypes.HANDLE
        _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        _kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        _kernel32.CloseHandle.restype = wintypes.BOOL
        _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    return _kernel32


def _ensure_job() -> Optional[int]:
    """建一个「最后一个句柄关闭就终止所有成员」的作业对象。"""
    global _job_handle, _job_failed
    if _job_handle is not None:
        return _job_handle
    if _job_failed:
        return None
    kernel = _kernel()
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        _job_failed = True
        return None
    info = _ExtendedLimitInformation()
    info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    ok = kernel.SetInformationJobObject(
        handle, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(info), ctypes.sizeof(info))
    if not ok:
        kernel.CloseHandle(handle)
        _job_failed = True
        return None
    _job_handle = handle
    return handle


def adopt(pid: int) -> bool:
    """把已启动的子进程纳入作业对象；失败返回 False，由调用方自行兜底。"""
    if sys.platform != "win32" or pid <= 0:
        return False
    handle = _ensure_job()
    if handle is None:
        return False
    kernel = _kernel()
    proc = kernel.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, int(pid))
    if not proc:
        return False
    try:
        return bool(kernel.AssignProcessToJobObject(handle, proc))
    finally:
        kernel.CloseHandle(proc)
