# -*- coding: utf-8 -*-
"""请求尾部片段注册表：执行模式之后追加的临时文本，不进系统提示词。"""
from __future__ import annotations

import threading
from typing import Any, Callable, List, Tuple

from agent.core.error_report import report_error


class PromptTail:
    """按注册顺序拼接请求尾部片段；单个来源异常隔离。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sources: List[Tuple[Callable[[str], Any], bool]] = []

    def add(self, fn: Callable[[str], Any], *,
            subagent_visible: bool = True) -> Callable[[], None]:
        """注册一个尾部来源；返回幂等 disposer。

        subagent_visible=False 的来源不会渲染到子 Agent 请求尾部。
        """
        if not callable(fn):
            raise ValueError("尾部来源必须可调用")
        entry = (fn, bool(subagent_visible))
        with self._lock:
            self._sources.append(entry)

        def _dispose() -> None:
            with self._lock:
                if entry in self._sources:
                    self._sources.remove(entry)

        return _dispose

    def render(self, conversation_id: str, *, is_subagent: bool = False) -> str:
        """渲染当前请求的尾部文本；空片段不占位。"""
        with self._lock:
            sources = list(self._sources)
        parts: List[str] = []
        for fn, subagent_visible in sources:
            if is_subagent and not subagent_visible:
                continue
            try:
                raw = fn(str(conversation_id or ""))
            except Exception as exc:  # 插件片段失败不阻断主请求
                report_error("prompt_tail.source", exc)
                continue
            text = str(raw or "").strip()
            if text:
                parts.append(text)
        return "\n\n".join(parts)
