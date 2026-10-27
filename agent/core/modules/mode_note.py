# -*- coding: utf-8 -*-
"""运行态与模式尾部。"""
from __future__ import annotations

from typing import Any, Dict, List

from agent.core.error_report import report_error
from agent.core.mode_marker import MODE_MARKER

_RUNTIME_NOTE_PREFIXES = ("## 当前模式", "## Todo-List")


def strip_runtime_note(messages: Any) -> List[Dict[str, Any]]:
    """去掉末尾遗留的临时运行态消息，避免重复拼接。"""
    out = list(messages or [])
    while out:
        last = out[-1]
        if not isinstance(last, dict) or str(last.get("role") or "") != "system":
            break
        content = str(last.get("content") or "")
        if not content.startswith(_RUNTIME_NOTE_PREFIXES):
            break
        out.pop()
    return out


def resolve_runtime_note(value: Any) -> str:
    """把字符串或每次求值的回调解析成当前运行态文本。"""
    if callable(value):
        try:
            return str(value() or "").strip()
        except Exception as exc:
            report_error("core.runtime_note", exc)
            return ""
    return str(value or "").strip()


def with_mode_note(messages: Any, mode_note: str) -> List[Dict[str, Any]]:
    """把执行模式说明附加到请求消息的最末尾（不动原列表、不动事实流）。

    模式说明是宿主附加的指令，不是用户发言 —— 用 `role=system`。
    非用户发起的请求一律走 system：用户消息的位置只放用户真正发的东西。

    追加一条独立消息而不是拼进最后一条的正文：最后一条可能是多模态数组
    或工具结果，拼接会改坏它的结构；独立成条也保证"改动只落在尾部"这件事一眼可见。
    """
    base = strip_runtime_note(messages)
    note = str(mode_note or "").strip()
    if not note:
        return base
    if base and str(base[-1].get("content") or "") == note:
        return base
    return base + [{"role": "system", "content": note}]


def mode_tail(messages: Any) -> List[Dict[str, Any]]:
    """请求尾部的执行模式说明（正文以 `MODE_MARKER` 开头）。

    位置不固定：用户输入轮末尾是 `[本回合新输入][执行模式]`，工具调用里是
    `[执行模式][工具结果]`。所以倒序按内容认，不按位置猜。
    """
    for m in reversed(list(messages or [])):
        if not isinstance(m, dict):
            continue
        if str(m.get("role") or "") == "system" \
                and str(m.get("content") or "").startswith(MODE_MARKER):
            return [m]
    return []
