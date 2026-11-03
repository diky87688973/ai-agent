# -*- coding: utf-8 -*-
"""系统提示词章节注册表：插件按章节名追加文本，同一章节合并为一个。"""
from __future__ import annotations

import re
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from agent.core.app_path import app_path
from agent.core.error_report import report_error

ASSEMBLE_PATH = app_path("kernel", "modules", "prompt", "assemble")
_HEADING_BLANK_RE = re.compile(r"(?m)^(#{2,6} [^\n]*)\n[ \t]*\n")


def _compact_heading_spacing(text: str) -> str:
    """标题后不留空行，规则与技能章节同样适用。"""
    return _HEADING_BLANK_RE.sub(r"\1\n", str(text or ""))




class PromptSections:
    """按章节合并系统提示词片段；来源异常隔离，空片段不占位。"""

    def __init__(self, slots: Any = None) -> None:
        self._lock = threading.Lock()
        self._sources: List[Tuple[str, Callable[[str], Any], Optional[int]]] = []
        self._after_sources: List[Tuple[str, Callable[[str], Any], Optional[int]]] = []
        self._slots = slots
        if self._slots is not None and ASSEMBLE_PATH not in self._slots.nodes:
            self._slots.register_slot(
                ASSEMBLE_PATH, kind="kernel-stage", default=self._render,
                default_owner="__host__")

    def add(self, section: str, fn: Callable[[str], Any], *,
            rank: Optional[int] = None, after_tools: bool = False) -> Callable[[], None]:
        """注册章节来源；同一 `section` 的正文按位次与注册序合并。"""
        heading = str(section or "").strip()
        if not heading:
            raise ValueError("系统提示词章节名不能为空")
        if not callable(fn):
            raise ValueError("系统提示词来源必须可调用")
        item = (heading, lambda cid, _fn=fn: _fn(cid), rank)
        target = self._after_sources if after_tools else self._sources
        with self._lock:
            target.append(item)

        def _dispose() -> None:
            with self._lock:
                if item in target:
                    target.remove(item)

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
        if self._slots is not None and ASSEMBLE_PATH in self._slots.nodes:
            impl = self._slots.resolve(ASSEMBLE_PATH)
            if impl is not self._render:
                return impl(str(conversation_id or ""))
        return self._render(str(conversation_id or ""))

    def _render_sources(self, sources: List[Tuple[str, Callable[[str], Any], Optional[int]]],
                        conversation_id: str) -> List[str]:
        sources = list(sources)
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
        rendered: List[str] = []
        for section, lines in groups.items():
            body = _compact_heading_spacing("\n".join(lines))
            first = body.lstrip().splitlines()[0] if body.lstrip() else ""
            if not section.lstrip().startswith("#") and first.startswith("#"):
                rendered.append(body)
            else:
                rendered.append(section + "\n" + body)
        return rendered

    def _render(self, conversation_id: str) -> List[str]:
        with self._lock:
            sources = list(self._sources)
        return self._render_sources(sources, conversation_id)

    def render_after_tools(self, conversation_id: str) -> List[str]:
        """渲染放在工具清单之后的系统提示词章节。"""
        with self._lock:
            sources = list(self._after_sources)
        return self._render_sources(sources, conversation_id)
