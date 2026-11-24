"""串行复用的 HTTP 工作进程；每个请求只持有自己的头、正文与响应。"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import BinaryIO

from agent.core.error_report import report_error
from agent.mechanisms.model_http.wire import (
    MAX_DATA_BYTES,
    WireProtocolError,
    read_body,
    read_frame,
    write_frame,
)


def completed(line: bytes, rule: dict | None) -> bool:
    if not rule or not line.startswith(b"data:"):
        return False
    payload = line[5:].strip()
    if "data" in rule:
        return payload == rule["data"].encode("utf-8")
    expected = rule.get("json", {})
    if not expected or not all(str(value).encode("utf-8") in payload for value in expected.values()):
        return False
    try:
        data = json.loads(payload)
    except (ValueError, UnicodeDecodeError):
        return False
    return isinstance(data, dict) and all(data.get(key) == value for key, value in expected.items())


def serve_one(incoming: BinaryIO, outgoing: BinaryIO) -> None:
    kind, config, request_id = read_frame(incoming)
    if kind != b"C":
        raise ValueError("模型 HTTP 请求帧不匹配")
    options = json.loads(config)
    body = read_body(incoming, options["body_bytes"], request_id)
    request = urllib.request.Request(options["url"], data=body if options["has_body"] else None,
                                     headers=options["headers"], method=options["method"])
    try:
        with urllib.request.urlopen(request, timeout=options["timeout"]) as response:
            write_frame(outgoing, b"R", request_id=request_id)
            for line in iter(lambda: response.readline(MAX_DATA_BYTES + 1), b""):
                if len(line) > MAX_DATA_BYTES:
                    raise WireProtocolError("模型 HTTP 上游单行超过 64 MiB 上限")
                terminal = completed(line, options["completion"])
                write_frame(outgoing, b"T" if terminal else b"D", line, request_id=request_id)
                if terminal:
                    break
    except urllib.error.HTTPError as exc:
        with exc:
            error = {"type": "HTTPError", "status": exc.code, "message": exc.reason,
                     "headers": dict(exc.headers),
                     "body": exc.read(8192).decode("utf-8", errors="replace")}
        write_frame(outgoing, b"X", json.dumps(error, ensure_ascii=False).encode("utf-8"), request_id=request_id)
    except Exception as exc:
        report_error("model_http.worker", exc)
        error = {"type": type(exc).__name__, "message": str(exc)}
        write_frame(outgoing, b"X", json.dumps(error, ensure_ascii=False).encode("utf-8"), request_id=request_id)
    write_frame(outgoing, b"E", request_id=request_id)


def main() -> None:
    while True:
        try:
            serve_one(sys.stdin.buffer, sys.stdout.buffer)
        except EOFError:
            return


if __name__ == "__main__":
    main()
