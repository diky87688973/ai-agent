"""有界文件传输与 HTTP 字节范围；独占响应句柄直到连接完成。"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import timezone
from email.utils import formatdate, parsedate_to_datetime
from urllib.parse import quote

from agent.common.http_contract import FileResponse, JsonResponse
from agent.core.error_report import report_error

CHUNK_BYTES = 256 * 1024
TRANSFER_LIMIT = 16
WRITE_TIMEOUT = 10.0


class InvalidRange(ValueError):
    """无法满足的字节范围。"""


def byte_range(value: str, size: int) -> tuple[int, int]:
    if not value or not value.startswith("bytes=") or "," in value:
        return 0, size
    if len(value) > 128:
        raise InvalidRange("range too long")
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value)
    if not match or not any(match.groups()) or not size:
        raise InvalidRange("invalid range")
    first, last = match.groups()
    if not first:
        length = int(last)
        if length <= 0:
            raise InvalidRange("invalid suffix")
        return max(0, size - length), min(size, length)
    start = int(first)
    end = min(int(last) if last else size - 1, size - 1)
    if start >= size or end < start:
        raise InvalidRange("unsatisfiable range")
    return start, end - start + 1


def _not_newer(modified: float, value: str) -> bool:
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(modified) <= parsed.timestamp()
    except (TypeError, ValueError, OverflowError):
        return False


def _head(handler, status, headers):
    for key, value in headers.items():
        if not re.fullmatch(r"[A-Za-z0-9-]+", key) or "\r" in str(value) or "\n" in str(value):
            raise ValueError("HTTP response header contains newline")
    handler.send_response(status)
    for key, value in headers.items():
        handler.send_header(key, str(value))
    handler.end_headers()


def _json(handler, response):
    body = json.dumps(dict(response.payload), ensure_ascii=False).encode("utf-8")
    _head(handler, response.status, {**response.headers,
          "Content-Type": "application/json; charset=utf-8", "Content-Length": str(len(body)),
          "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})
    if handler.command != "HEAD":
        handler.wfile.write(body)


class FileTransfers:
    def __init__(self, limit: int = TRANSFER_LIMIT):
        self._capacity = threading.BoundedSemaphore(limit)

    def send(self, handler, response):
        if isinstance(response, JsonResponse):
            _json(handler, response)
            return
        if not isinstance(response, FileResponse):
            raise TypeError("HTTP handler must return JsonResponse or FileResponse")
        acquired = self._capacity.acquire(blocking=False)
        try:
            if not acquired:
                _json(handler, JsonResponse({"error": "file_transfer_busy"}, 503, {"Retry-After": "1"}))
                return
            self._file(handler, response)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            handler.close_connection = True
        except OSError as exc:
            handler.close_connection = True
            report_error("http.file_response", exc, stage="response")
        finally:
            try:
                response.file.close()
            except OSError as exc:
                handler.close_connection = True
                report_error("http.file_response", exc, stage="close")
            finally:
                if acquired:
                    self._capacity.release()

    def _file(self, handler, response):
        file = response.file
        size, modified = file.stat.st_size, file.stat.st_mtime
        headers = {"Content-Type": response.content_type, "Accept-Ranges": "bytes",
                   "Last-Modified": formatdate(min(modified, time.time()), usegmt=True),
                   "Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff",
                   "Content-Disposition": "inline; filename*=UTF-8''" + quote(file.path.name, safe="")}
        if _not_newer(modified, handler.headers.get("If-Modified-Since", "")):
            _head(handler, 304, headers)
            return
        value = handler.headers.get("Range", "") if handler.command == "GET" else ""
        condition = handler.headers.get("If-Range", "")
        # 文件系统的秒级修改日期不是强校验器，不能用 If-Range 拼接潜在不同版本。
        if condition:
            value = ""
        try:
            start, length = byte_range(value, size)
        except InvalidRange:
            _json(handler, JsonResponse({"error": "range_not_satisfiable"}, 416,
                                       {"Content-Range": f"bytes */{size}"}))
            return
        partial = bool(value.startswith("bytes=") and "," not in value)
        headers["Content-Length"] = str(length)
        if partial:
            headers["Content-Range"] = f"bytes {start}-{start + length - 1}/{size}"
        _head(handler, 206 if partial else 200, headers)
        if handler.command != "HEAD":
            self._copy(handler, file.stream, start, length)

    def _copy(self, handler, stream, start, length):
        previous = handler.connection.gettimeout()
        try:
            handler.connection.settimeout(WRITE_TIMEOUT)
            stream.seek(start)
            remaining = length
            while remaining:
                chunk = stream.read(min(CHUNK_BYTES, remaining))
                if not chunk:
                    raise OSError("file shortened during transfer")
                handler.wfile.write(chunk)
                remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            handler.close_connection = True
        except OSError as exc:
            handler.close_connection = True
            report_error("http.file_transfer", exc, stage="copy")
        finally:
            handler.connection.settimeout(previous)
