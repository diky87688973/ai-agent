# -*- coding: utf-8 -*-
"""鉴权文件安全：目录/文件权限、原子写入与平台校验。

Windows 依赖 icacls 收紧 DACL，读取时用 Win32 ACL API 校验；
Linux 使用 POSIX mode；macOS 额外清理并校验 NFSv4 ACL。
"""
from __future__ import annotations

import ctypes
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
from ctypes import wintypes
from pathlib import Path

from agent.core.error_report import report_error


class AuthSecurityError(RuntimeError):
    """无法保证鉴权文件只对允许的身份可见。"""


_SE_FILE_OBJECT = 1
_DACL_SECURITY_INFORMATION = 0x00000004
_SE_DACL_PROTECTED = 0x00001000
_ACL_SIZE_INFORMATION = 2
_ACCESS_ALLOWED_ACE_TYPE = 0
_INHERITED_ACE = 0x10
_WINDOWS_ALLOWED = ("S-1-5-18", "S-1-5-32-544", "S-1-3-4")


class _AclSizeInformation(ctypes.Structure):
    _fields_ = [
        ("AceCount", wintypes.DWORD),
        ("AclBytesInUse", wintypes.DWORD),
        ("AclBytesFree", wintypes.DWORD),
    ]


class _AceHeader(ctypes.Structure):
    _fields_ = [
        ("AceType", ctypes.c_ubyte),
        ("AceFlags", ctypes.c_ubyte),
        ("AceSize", wintypes.WORD),
    ]


_ADVAPI32 = None
_ADVAPI32_LOCK = threading.Lock()


def _advapi32():
    global _ADVAPI32
    if _ADVAPI32 is not None:
        return _ADVAPI32
    with _ADVAPI32_LOCK:
        if _ADVAPI32 is not None:
            return _ADVAPI32
        library = ctypes.WinDLL("advapi32", use_last_error=True)
        library.GetNamedSecurityInfoW.argtypes = [
            wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD,
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        library.GetNamedSecurityInfoW.restype = wintypes.DWORD
        library.GetAclInformation.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(_AclSizeInformation),
            wintypes.DWORD, ctypes.c_int,
        ]
        library.GetAclInformation.restype = wintypes.BOOL
        library.GetAce.argtypes = [
            ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p),
        ]
        library.GetAce.restype = wintypes.BOOL
        library.GetSecurityDescriptorControl.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(wintypes.WORD),
            ctypes.POINTER(wintypes.DWORD),
        ]
        library.GetSecurityDescriptorControl.restype = wintypes.BOOL
        library.ConvertSidToStringSidW.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p),
        ]
        library.ConvertSidToStringSidW.restype = wintypes.BOOL
        _ADVAPI32 = library
        return library


_WINDOWS_SID = ""
_WINDOWS_SID_LOCK = threading.Lock()


def _powershell() -> str:
    executable = shutil.which("powershell") or shutil.which("powershell.exe")
    if not executable:
        raise AuthSecurityError("找不到 PowerShell，无法读取 Windows SID")
    return executable


def _windows_sid() -> str:
    global _WINDOWS_SID
    if _WINDOWS_SID:
        return _WINDOWS_SID
    with _WINDOWS_SID_LOCK:
        if _WINDOWS_SID:
            return _WINDOWS_SID
        try:
            result = subprocess.run(
                [_powershell(), "-NoProfile", "-NonInteractive", "-Command",
                 "[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=15,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AuthSecurityError(f"读取 Windows 用户 SID 失败：{exc}") from exc
        sid = (result.stdout or "").strip()
        if result.returncode != 0 or not sid.startswith("S-1-"):
            raise AuthSecurityError("无法读取当前 Windows 用户 SID")
        _WINDOWS_SID = sid
        return sid


def _icacls(path: Path, args: list[str]) -> None:
    icacls = shutil.which("icacls")
    if not icacls:
        raise AuthSecurityError("找不到 icacls，无法设置 Windows ACL")
    try:
        result = subprocess.run(
            [icacls, str(path), *args], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AuthSecurityError(f"Windows ACL 子进程失败：{path}：{exc}") from exc
    if result.returncode != 0:
        detail = (result.stdout or result.stderr or "").strip()
        raise AuthSecurityError(
            f"Windows ACL 设置失败：{path}：{detail[-500:]}")


def _windows_verify_native(path: Path) -> None:
    library = _advapi32()
    owner = ctypes.c_void_p()
    group = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    sacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    status = library.GetNamedSecurityInfoW(
        str(path), _SE_FILE_OBJECT, _DACL_SECURITY_INFORMATION,
        ctypes.byref(owner), ctypes.byref(group), ctypes.byref(dacl),
        ctypes.byref(sacl), ctypes.byref(descriptor),
    )
    if status != 0:
        raise AuthSecurityError(
            f"读取 Windows ACL 失败：{path}：{ctypes.WinError(status)}")
    try:
        control = wintypes.WORD()
        revision = wintypes.DWORD()
        if not library.GetSecurityDescriptorControl(
                descriptor, ctypes.byref(control), ctypes.byref(revision)):
            raise AuthSecurityError(f"读取 Windows ACL 控制位失败：{path}")
        if not control.value & _SE_DACL_PROTECTED:
            raise AuthSecurityError(f"Windows ACL 未关闭继承：{path}")
        if not dacl:
            raise AuthSecurityError(f"Windows ACL 为空：{path}")
        info = _AclSizeInformation()
        if not library.GetAclInformation(
                dacl, ctypes.byref(info), ctypes.sizeof(info),
                _ACL_SIZE_INFORMATION):
            raise AuthSecurityError(f"读取 Windows ACL 失败：{path}")
        allowed = {_windows_sid(), *_WINDOWS_ALLOWED}
        for index in range(int(info.AceCount)):
            ace = ctypes.c_void_p()
            if not library.GetAce(dacl, index, ctypes.byref(ace)):
                raise AuthSecurityError(f"读取 Windows ACE 失败：{path}")
            header = ctypes.cast(ace, ctypes.POINTER(_AceHeader)).contents
            if header.AceFlags & _INHERITED_ACE:
                raise AuthSecurityError(f"Windows ACL 仍包含继承项：{path}")
            if header.AceType != _ACCESS_ALLOWED_ACE_TYPE:
                continue
            sid = ctypes.c_void_p(int(ace.value) + ctypes.sizeof(_AceHeader)
                                  + ctypes.sizeof(wintypes.DWORD))
            text = ctypes.c_wchar_p()
            if not library.ConvertSidToStringSidW(sid, ctypes.byref(text)):
                raise AuthSecurityError(f"无法解析 Windows SID：{path}")
            try:
                sid_text = str(text.value or "")
            finally:
                ctypes.windll.kernel32.LocalFree(text)
            if sid_text not in allowed:
                raise AuthSecurityError(
                    f"Windows ACL 授予额外身份：{path}：{sid_text}")
    finally:
        if descriptor:
            ctypes.windll.kernel32.LocalFree(descriptor)


def _windows_secure(path: Path) -> None:
    is_dir = path.is_dir()
    _icacls(path, ["/reset"])
    _icacls(path, ["/inheritance:r"])
    for sid in (_windows_sid(), *_WINDOWS_ALLOWED):
        permission = f"*{sid}:(OI)(CI)F" if is_dir else f"*{sid}:F"
        _icacls(path, ["/grant:r", permission])
    _windows_verify_native(path)


def _run_macos(command: list[str], path: Path, action: str) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AuthSecurityError(f"{action}失败：{path}：{exc}") from exc
    if result.returncode != 0:
        raise AuthSecurityError(f"{action}失败：{path}")
    return result


def _remove_macos_acl(path: Path) -> None:
    if sys.platform != "darwin":
        return
    chmod = shutil.which("chmod")
    if chmod is None:
        raise AuthSecurityError("找不到 chmod，无法清理 macOS ACL")
    _run_macos([chmod, "-N", str(path)], path, "清理 macOS ACL")


def _verify_macos_acl(path: Path) -> None:
    if sys.platform != "darwin":
        return
    result = _run_macos(["ls", "-lde", str(path)], path, "读取 macOS ACL")
    for line in result.stdout.splitlines():
        lowered = line.lower()
        if " allow " in lowered or " deny " in lowered:
            raise AuthSecurityError(f"macOS ACL 仍授予额外权限：{path}")


def _posix_verify(path: Path) -> None:
    info = path.stat()
    uid = os.geteuid() if hasattr(os, "geteuid") else None
    if uid is not None and info.st_uid != uid:
        raise AuthSecurityError(f"鉴权路径所有者不是当前用户：{path}")
    mode = stat.S_IMODE(info.st_mode)
    if mode & 0o077:
        raise AuthSecurityError(f"鉴权路径权限过宽：{path}：{oct(mode)}")
    _verify_macos_acl(path)


def secure_path(path: Path, *, directory: bool = False) -> None:
    target = Path(path)
    if os.name == "nt":
        _windows_secure(target)
        return
    try:
        os.chmod(target, 0o700 if directory else 0o600)
    except OSError as exc:
        raise AuthSecurityError(f"无法设置鉴权路径权限：{target}：{exc}") from exc
    _remove_macos_acl(target)
    _posix_verify(target)


def verify_path(path: Path, *, directory: bool = False) -> None:
    target = Path(path)
    if not target.exists():
        raise AuthSecurityError(f"鉴权路径不存在：{target}")
    if os.name == "nt":
        _windows_verify_native(target)
    else:
        _posix_verify(target)


def ensure_auth_dir(path: Path) -> None:
    target = Path(path)
    try:
        target.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as exc:
        raise AuthSecurityError(f"无法创建鉴权目录：{target}：{exc}") from exc
    try:
        verify_path(target, directory=True)
    except AuthSecurityError:
        secure_path(target, directory=True)


def read_text(path: Path) -> str:
    target = Path(path)
    verify_path(target)
    try:
        return target.read_text(encoding="utf-8")
    except OSError as exc:
        raise AuthSecurityError(f"无法读取鉴权文件：{target}：{exc}") from exc


def atomic_write_text(path: Path, text: str) -> None:
    target = Path(path)
    ensure_auth_dir(target.parent)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".auth-", dir=str(target.parent))
    temp = Path(temporary)
    handle = None
    try:
        fchmod = getattr(os, "fchmod", None)
        if callable(fchmod):
            fchmod(descriptor, 0o600)
        handle = os.fdopen(descriptor, "w", encoding="utf-8")
        descriptor = -1
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        handle = None
        secure_path(temp)
        verify_path(temp)
        os.replace(temp, target)
    except Exception:
        if handle is not None:
            handle.close()
        if descriptor >= 0:
            os.close(descriptor)
        if temp.exists():
            try:
                temp.unlink()
            except OSError as exc:
                report_error("agent.shell.web.auth.security.cleanup", exc)
        raise


def append_line(path: Path, line: str) -> None:
    target = Path(path)
    if not target.parent.is_dir():
        ensure_auth_dir(target.parent)
    created = not target.exists()
    if not created:
        verify_path(target)
    try:
        with target.open("a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError as exc:
        raise AuthSecurityError(f"无法写入鉴权文件：{target}：{exc}") from exc
    if created:
        secure_path(target)
    verify_path(target)
