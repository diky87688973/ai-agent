"""公共 HTTP 扩展的数据契约；文件句柄交接后由传输层独占并关闭。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, BinaryIO, Mapping, Protocol


@dataclass(frozen=True)
class OpenedFile:
    path: Path
    stream: BinaryIO
    stat: Any

    def close(self) -> None:
        self.stream.close()


class FileAccess(Protocol):
    def open(self, path: str) -> OpenedFile: ...


@dataclass(frozen=True)
class HttpRequest:
    method: str
    path: str
    query: Mapping[str, str]
    headers: Mapping[str, str]
    files: FileAccess
    version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "query", MappingProxyType(dict(self.query)))
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))


@dataclass(frozen=True)
class JsonResponse:
    payload: Mapping[str, Any]
    status: int = 200
    headers: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class FileResponse:
    file: OpenedFile
    content_type: str


class FileAccessError(OSError):
    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
