# -*- coding: utf-8 -*-
"""系统提示词章节注册表：插件按章节名追加文本，同一章节合并为一个。"""
from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from agent.core.error_report import report_error


class PromptSections:
    """按章节合并系统提示词片段；来源异常隔离，空片段不占位。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sources: List[Tuple[str, Callable[[str], Any], Optional[int]]] = []

    def add(self, section: str, fn: Callable[[str], Any], *,
            rank: Optional[int] = None) -> Callable[[], None]:
        """注册章节来源；同一 `section` 的正文按位次与注册序合并。"""
        heading = str(section or "").strip()
        if not heading:
            raise ValueError("系统提示词章节名不能为空")
        if not callable(fn):
            raise ValueError("系统提示词来源必须可调用")
        item = (heading, fn, rank)
        with self._lock:
            self._sources.append(item)

        def _dispose() -> None:
            with self._lock:
                if item in self._sources:
                    self._sources.remove(item)

        return _dispose

    @staticmethod
    def _texts(raw: Any) -> List[str]:
        if isinstance(raw, (list, tuple)):
            texts = [str(x or "").rstrip() for x in raw]
            return [text for text in texts if text.strip()]
        text = str(raw or "").rstrip()
        return [text] if text.strip() else []

    def render(self, conversation_id: str) -> List[str]:
        """渲染章节列表；同一章节的正文合并在一个标题下。"""
        with self._lock:
            sources = list(self._sources)
        sources.sort(key=lambda item: (item[2] is None, item[2] if item[2] is not None else 0))
        groups: Dict[str, List[str]] = {}
        for section, fn, _rank in sources:
            try:
                raw = fn(str(conversation_id or ""))
            except Exception as exc:
                report_error("prompt_section.source", exc,
                             conversation_id=str(conversation_id or ""), section=section)
                continue
            texts = self._texts(raw)
            if texts:
                groups.setdefault(section, []).extend(texts)
        return [section + "\n" + "\n".join(lines) for section, lines in groups.items()]
