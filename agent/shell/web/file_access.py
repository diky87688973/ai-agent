"""授权目录内打开普通文件；检查实际句柄，避免路径检查与打开之间的替换。"""
from __future__ import annotations

import ctypes
import os
import re
import stat
from pathlib import Path
from typing import Sequence

from agent.common.http_contract import FileAccessError, OpenedFile


def _inside(path: Path, roots: Sequence[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def _windows_path(fd: int) -> Path:
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    query = kernel.GetFinalPathNameByHandleW
    query.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    query.restype = wintypes.DWORD
    handle = msvcrt.get_osfhandle(fd)
    size = query(handle, None, 0, 0)
    if not size:
        raise ctypes.WinError(ctypes.get_last_error())
    buffer = ctypes.create_unicode_buffer(size + 1)
    copied = query(handle, buffer, len(buffer), 0)
    if not copied or copied >= len(buffer):
        raise OSError("无法验证已打开文件的真实路径")
    value = buffer.value
    if value.startswith("\\\\?\\UNC\\"):
        raise FileAccessError(403, "remote_path_denied")
    return Path(value.removeprefix("\\\\?\\")).resolve()


class LocalFileAccess:
    def __init__(self, roots: Sequence[Path], workspace: Path | None = None) -> None:
        self.roots = tuple(Path(root).resolve() for root in roots)
        self.workspace = Path(workspace).resolve() if workspace else None

    def _target(self, raw: str) -> Path:
        if not raw or "\x00" in raw or raw.startswith(("\\\\", "//")) or "://" in raw:
            raise FileAccessError(400, "invalid_path")
        if os.name == "nt" and (":" in raw[2:] or any(
                re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part)
                for part in Path(raw).parts)):
            raise FileAccessError(403, "device_path_denied")
        target = Path(raw)
        if not target.is_absolute():
            candidates = ([self.workspace] if self.workspace else []) + list(self.roots)
            target = next((root / target for root in candidates if (root / target).exists()),
                          (candidates[0] / target) if candidates else target)
        target = target.resolve()
        if not _inside(target, self.roots):
            raise FileAccessError(403, "outside_read_roots")
        return target

    def _open_posix(self, target: Path) -> int:
        root = next(root for root in self.roots if target == root or root in target.parents)
        parts = target.relative_to(root).parts
        if not parts:
            raise FileAccessError(403, "not_regular_file")
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in parts[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.close(directory)
                directory = child
            return os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        finally:
            os.close(directory)

    def open(self, path: str) -> OpenedFile:
        fd = None
        try:
            target = self._target(str(path or "").strip())
            before = target.stat()
            if not stat.S_ISREG(before.st_mode):
                raise FileAccessError(403, "not_regular_file")
            fd = (os.open(target, os.O_RDONLY | os.O_BINARY | os.O_NOINHERIT)
                  if os.name == "nt" else self._open_posix(target))
            actual = os.fstat(fd)
            if not stat.S_ISREG(actual.st_mode) or not os.path.samestat(before, actual):
                raise FileAccessError(409, "file_changed")
            if os.name == "nt" and not _inside(_windows_path(fd), self.roots):
                raise FileAccessError(403, "outside_read_roots")
            stream = os.fdopen(fd, "rb")
            fd = None
            return OpenedFile(target, stream, actual)
        except FileAccessError:
            raise
        except FileNotFoundError as exc:
            raise FileAccessError(404, "file_missing") from exc
        except (PermissionError, ValueError) as exc:
            raise FileAccessError(403, "file_access_denied") from exc
        finally:
            if fd is not None:
                os.close(fd)
