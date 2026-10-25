# -*- coding: utf-8 -*-
"""进程级错误日志：JSONL 落盘 + stderr 双写。

只在本模块写 `data/logs/errors.log`；core 经 `error_report` 回调进来，不 import 路径。
写失败只留 stderr，再抛禁止。
"""
from __future__ import annotations

import json
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Union

from agent.core.stderr import write_stderr

_MAX_MESSAGE = 4000
_MAX_FILE_BYTES = 2 * 1024 * 1024
_ExcLike = Union[BaseException, str]


def _iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _exc_parts(exc: _ExcLike) -> tuple[str, str, str]:
    """→ (exc_type, message, traceback 可选)。"""
    if isinstance(exc, BaseException):
        exc_type = type(exc).__name__
        message = str(exc) or exc_type
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        return exc_type, message, tb
    text = str(exc or "").strip() or "(empty)"
    return "", text, ""


def _clip(text: str, limit: int = _MAX_MESSAGE) -> str:
    s = str(text or "")
    if len(s) <= limit:
        return s
    return s[: limit - 3] + "..."


class ErrorLog:
    """错误日志写入器：`<data_root>/logs/errors.log`。"""

    def __init__(self, data_root: Path) -> None:
        self._root = Path(data_root)
        # 用 `data_root / "logs"` 形状，供 check_readme AST 识别（勿写成 self._root / …）
        self._path = (data_root / "logs") / "errors.log"
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def report(
        self,
        tag: str,
        exc: _ExcLike,
        *,
        conversation_id: str = "",
        **fields: Any,
    ) -> None:
        """记一条错误：stderr + JSONL；绝不向外抛。"""
        exc_type, message, tb = _exc_parts(exc)
        tag_s = str(tag or "unknown").strip() or "unknown"
        cid = str(conversation_id or "").strip()
        extra = {str(k): v for k, v in fields.items() if v is not None and v != ""}
        line_msg = f"[{tag_s}]"
        if cid:
            line_msg += f" cid={cid}"
        if exc_type:
            line_msg += f" {exc_type}: {_clip(message, 500)}"
        else:
            line_msg += f" {_clip(message, 500)}"
        write_stderr(line_msg)

        record: dict[str, Any] = {
            "ts": _iso_now(),
            "level": "error",
            "tag": tag_s,
            "message": _clip(message),
        }
        if exc_type:
            record["exc_type"] = exc_type
        if cid:
            record["conversation_id"] = cid
        if tb:
            record["traceback"] = _clip(tb, 8000)
        for key, val in extra.items():
            if key in record:
                continue
            if isinstance(val, (str, int, float, bool)):
                record[key] = val if not isinstance(val, str) else _clip(val, 1000)
            else:
                record[key] = _clip(str(val), 1000)

        try:
            with self._lock:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._rotate_if_needed()
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as write_exc:
            write_stderr(f"[error_log] 写盘失败：{type(write_exc).__name__}: {write_exc}")

    def _rotate_if_needed(self) -> None:
        """单文件超约 2MB 时 rename 为 errors.log.1（只保留一代）。"""
        try:
            if not self._path.is_file():
                return
            if self._path.stat().st_size < _MAX_FILE_BYTES:
                return
            bak = self._path.with_name("errors.log.1")
            if bak.exists():
                bak.unlink()
            self._path.rename(bak)
        except Exception as exc:
            write_stderr(f"[error_log] 轮转失败：{type(exc).__name__}: {exc}")
