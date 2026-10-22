# -*- coding: utf-8 -*-
"""SSE 行解析与流总超时。"""
from __future__ import annotations

import json
import sys
import threading
from typing import Any, Dict, Iterable, Iterator

from agent.mechanisms.providers.base import ModelRequestError


def parse_sse_lines(lines: Iterable[str]) -> Iterator[Dict[str, Any]]:
    """SSE 行流 → chunk 字典。

    只处理 data: 行；空行 / 其他字段（event: / id: / 注释）跳过；
    [DONE] 终止；JSON 解析失败的行跳过不中断。
    """
    for raw in lines:
        line = str(raw or "").rstrip("\r\n")
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data:
            continue
        if data == "[DONE]":
            return
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            yield obj


def stream_with_timeout(
    resp: Any,
    timeout: float,
    *,
    label: str = "model",
) -> Iterator[Dict[str, Any]]:
    """SSE 流总超时：到期关闭响应，避免上游心跳把读取永久拖住。"""
    timed_out = threading.Event()

    def _warn_close(exc: Exception) -> None:
        message = f"{label} 超时关闭响应流失败：{type(exc).__name__}: {exc}"
        print(f"[providers.sse] {message}", file=sys.stderr, flush=True)

    def _expire() -> None:
        timed_out.set()
        try:
            resp.close()
        except Exception as exc:
            _warn_close(exc)

    watchdog = threading.Timer(max(0.001, float(timeout)), _expire)
    watchdog.daemon = True
    watchdog.start()
    try:
        try:
            lines = (raw.decode("utf-8", errors="replace") for raw in resp)
            yield from parse_sse_lines(lines)
        except Exception as exc:
            if timed_out.is_set():
                raise ModelRequestError(f"{label} 模型流超时（{timeout:g}s）") from exc
            raise
        if timed_out.is_set():
            raise ModelRequestError(f"{label} 模型流超时（{timeout:g}s）")
    finally:
        watchdog.cancel()
        try:
            resp.close()
        except Exception:
            # 已经拿到的流或即将抛出的错误更重要，关闭失败不覆盖它们。
            pass
