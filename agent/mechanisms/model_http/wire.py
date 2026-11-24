"""模型 HTTP 管道：按帧类型限长，请求正文分块传输。"""
from __future__ import annotations

import struct
from typing import BinaryIO

from agent.mechanisms.providers.base import ModelRequestError

BODY_CHUNK_BYTES = 1024 * 1024
MAX_DATA_BYTES = 64 * 1024 * 1024
_FRAME_LIMITS = {b"C": 256 * 1024, b"B": BODY_CHUNK_BYTES,
                 b"R": 0, b"E": 0, b"D": MAX_DATA_BYTES, b"T": MAX_DATA_BYTES, b"X": 64 * 1024}


class WireProtocolError(ModelRequestError):
    """损坏或超限帧不能继续使用同一条管道。"""


def validate_frame(kind: bytes, size: int) -> None:
    if kind not in _FRAME_LIMITS or size > _FRAME_LIMITS[kind]:
        raise WireProtocolError(f"模型 HTTP 帧类型无效或超过长度上限：{kind!r}, {size}")


def read_exact(stream: BinaryIO, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        part = stream.read(min(size - len(chunks), BODY_CHUNK_BYTES))
        if not part:
            raise EOFError("模型 HTTP 工作进程管道提前关闭")
        chunks.extend(part)
    return bytes(chunks)


def read_frame(stream: BinaryIO) -> tuple[bytes, bytes, bytes]:
    kind, request_id, size = struct.unpack("!c16sQ", read_exact(stream, 25))
    validate_frame(kind, size)
    return kind, read_exact(stream, size), request_id


def write_frame(stream: BinaryIO, kind: bytes, payload: bytes = b"", *, request_id: bytes) -> None:
    validate_frame(kind, len(payload))
    stream.write(struct.pack("!c16sQ", kind, request_id, len(payload)))
    stream.write(payload)
    stream.flush()


def write_body(stream: BinaryIO, body: bytes, *, request_id: bytes) -> None:
    view = memoryview(body)
    for offset in range(0, max(1, len(body)), BODY_CHUNK_BYTES):
        write_frame(stream, b"B", view[offset:offset + BODY_CHUNK_BYTES], request_id=request_id)


def read_body(stream: BinaryIO, size: int, request_id: bytes) -> bytes:
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise WireProtocolError("模型 HTTP 请求正文长度无效")
    body = bytearray()
    while True:
        kind, part, body_id = read_frame(stream)
        if kind != b"B" or body_id != request_id or len(body) + len(part) > size:
            raise WireProtocolError("模型 HTTP 请求正文帧不匹配")
        body.extend(part)
        if len(body) == size:
            return bytes(body)
        if not part:
            raise WireProtocolError("模型 HTTP 请求正文提前结束")
