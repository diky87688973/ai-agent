"""有界池上的流式 HTTP 响应；租约标识隔离迟到帧和迟到取消。"""
from __future__ import annotations

import io
import json
import urllib.error
from http.client import RemoteDisconnected
from typing import Any, Iterator

from agent.core.error_report import report_error
from agent.core.stream_control import register_stream_abort
from agent.mechanisms.model_http.pool import ModelHTTPPool, PoolRequest
from agent.mechanisms.model_http.process import HTTPWorker
from agent.mechanisms.model_http.wire import WireProtocolError, read_frame, write_body, write_frame
from agent.mechanisms.providers.base import ModelRequestCancelled, ModelRequestError


class ModelHTTPResponse:
    """只有读完终态帧的健康进程才能归还；取消和关闭按租约身份生效。"""

    def __init__(self, pool: ModelHTTPPool) -> None:
        self._pool = pool
        self._request = PoolRequest()
        self._worker: HTTPWorker | None = None
        self._ended = self._terminal = self._closed = False
        self._unregister = register_stream_abort(self.abort)

    def open(self, request: Any, timeout: float, completion: dict | None) -> None:
        if self._closed or self._worker is not None:
            raise ModelRequestError("模型 HTTP 响应不可重复开启")
        self._worker = self._pool.acquire(self._request)
        if self._request.canceled.is_set():
            raise ModelRequestCancelled("模型请求已取消")
        options = {"url": request.full_url, "headers": dict(request.header_items()),
                   "method": request.get_method(), "timeout": timeout,
                   "has_body": request.data is not None, "body_bytes": len(request.data or b""),
                   "completion": completion}
        outgoing = self._worker.process.stdin
        write_frame(outgoing, b"C", json.dumps(options).encode("utf-8"),
                    request_id=self._request.request_id)
        write_body(outgoing, request.data or b"", request_id=self._request.request_id)
        kind, payload = self._read()
        self._check_error(kind, payload, request.full_url)
        if kind != b"R":
            self.abort()
            raise ModelRequestError("模型 HTTP 工作进程未返回就绪帧")

    def _read(self) -> tuple[bytes, bytes]:
        try:
            kind, payload, request_id = read_frame(self._worker.process.stdout)
        except WireProtocolError:
            self.abort()
            raise
        if request_id != self._request.request_id:
            self.abort()
            raise ModelRequestError("模型 HTTP 响应与当前请求不匹配，已丢弃工作进程")
        if kind == b"E":
            self._ended = True
        if kind in (b"T", b"X"):
            self._terminal = True
        return kind, payload

    def _check_error(self, kind: bytes, payload: bytes, url: str = "") -> None:
        if kind != b"X":
            return
        try:
            error = json.loads(payload)
            message, error_type = error["message"], error["type"]
            if not isinstance(message, str) or not isinstance(error_type, str):
                raise ValueError("错误字段必须为字符串")
            if error_type == "HTTPError":
                status, headers, body = error["status"], error["headers"], error["body"]
                if not isinstance(status, int) or not isinstance(headers, dict) or not isinstance(body, str):
                    raise ValueError("HTTP 错误字段无效")
        except (ValueError, TypeError, KeyError) as exc:
            self.abort()
            raise ModelRequestError("模型 HTTP 错误帧无效，已丢弃工作进程") from exc
        if error["type"] == "HTTPError":
            raise urllib.error.HTTPError(url, error["status"], message, error["headers"],
                                         io.BytesIO(error["body"].encode("utf-8")))
        if error["type"] == "RemoteDisconnected":
            raise RemoteDisconnected(message)
        if error["type"] in ("TimeoutError", "timeout"):
            raise TimeoutError(message)
        raise urllib.error.URLError(message)

    def __iter__(self) -> Iterator[bytes]:
        while True:
            if self._closed:
                raise ModelRequestError("模型 HTTP 响应已关闭")
            if self._request.canceled.is_set():
                raise ModelRequestCancelled("模型请求已取消")
            try:
                kind, payload = self._read()
            except EOFError:
                if self._request.canceled.is_set():
                    raise ModelRequestCancelled("模型请求已取消")
                raise ModelRequestError("模型 HTTP 工作进程异常退出，未完成响应")
            if self._request.canceled.is_set():
                raise ModelRequestCancelled("模型请求已取消")
            self._check_error(kind, payload)
            if kind == b"E":
                return
            if kind not in (b"D", b"T"):
                self.abort()
                raise ModelRequestError("模型 HTTP 工作进程返回无效帧")
            yield payload

    def abort(self) -> None:
        self._pool.cancel(self._request)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._worker is not None and self._terminal and not self._request.canceled.is_set():
                # 解析器可在 SSE 结束标记处返回；归还前仍须消费传输终态。
                while not self._ended:
                    kind, _ = self._read()
                    if kind != b"E":
                        raise ModelRequestError("模型 HTTP 结束标记后仍有未结算数据")
        except Exception as exc:
            report_error("model_http.response.close", exc)
        finally:
            try:
                if self._worker is not None:
                    self._pool.release(self._request, self._worker, healthy=self._ended)
            finally:
                self._unregister()


def open_model_response(request: Any, timeout: float, *, pool: ModelHTTPPool,
                        completion: dict | None = None) -> ModelHTTPResponse:
    response = ModelHTTPResponse(pool)
    try:
        response.open(request, timeout, completion)
    except EOFError as exc:
        response.close()
        if response._request.canceled.is_set():
            raise ModelRequestCancelled("模型请求已取消") from exc
        raise ModelRequestError("模型 HTTP 工作进程异常退出，未完成响应") from exc
    except BaseException:
        response.close()
        raise
    return response
