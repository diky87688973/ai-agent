# -*- coding: utf-8 -*-
"""grep_files 工具：目录内文本内容搜索（字面含 | 分隔 / 正则）。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

from agent.capabilities.registry import ToolPlugin

DEFAULT_LIMIT = 200
_BINARY_SNIFF = "\x00"


def _iter_text_files(root: Path) -> Iterator[Tuple[Path, str]]:
    """遍历 root 下文件，产出 (path, text)；不可读或疑似二进制跳过。"""
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _BINARY_SNIFF in text:
            continue
        yield p, text


def _compile_pattern(pattern: str, regex: bool, ignore_case: bool):
    """构建匹配器：正则，或字面（| 为 OR 分隔）；无效返回 None。"""
    flags = re.IGNORECASE if ignore_case else 0
    if regex:
        return re.compile(pattern, flags)
    parts = [re.escape(x.strip()) for x in pattern.split("|") if x.strip()]
    if not parts:
        return None
    return re.compile("|".join(parts), flags)


class GrepFilesTool(ToolPlugin):
    """在目录内搜索文本内容。"""

    name = "grep_files"
    label = "搜索文件内容"
    icon = "🔎"
    description = (
        "按字面（| 为 OR 分隔）或正则搜索目录内文本文件内容。"
        "需要 gitignore 过滤 / 上下文行 / 编码嗅探时用 file_search。"
    )
    parameters = {
        "pattern": {"type": "string", "description": "搜索模式（字面或正则）"},
        "path": {"type": "string", "description": "搜索根目录，默认 ."},
        "regex": {"type": "boolean", "description": "true 时按 Python 正则解析，默认 false"},
        "ignore_case": {"type": "boolean", "description": "忽略大小写，默认 false"},
        "limit": {"type": "integer", "description": "结果上限，默认 200"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        pattern = str(arguments.get("pattern") or "")
        if not pattern:
            raise ValueError("缺少 pattern")
        root = Path(str(arguments.get("path") or ".")).resolve()
        if not root.is_dir():
            raise ValueError(f"path 不是目录：{root}")
        matcher = _compile_pattern(
            pattern, bool(arguments.get("regex")), bool(arguments.get("ignore_case"))
        )
        if matcher is None:
            raise ValueError("pattern 为空（字面模式）")
        limit = int(arguments.get("limit") or DEFAULT_LIMIT)
        matches: List[Dict[str, Any]] = []
        truncated = False
        for file_path, text in _iter_text_files(root):
            rel = str(file_path.relative_to(root)).replace("\\", "/")
            for lineno, line in enumerate(text.splitlines(), 1):
                if not matcher.search(line):
                    continue
                if len(matches) >= limit:
                    truncated = True
                    break
                matches.append({"file": rel, "line": lineno, "text": line})
            if truncated:
                break
        return {
            "pattern": pattern,
            "root": str(root),
            "matches": matches,
            "count": len(matches),
            "truncated": truncated,
        }


def build() -> GrepFilesTool:
    """构造 grep_files 插件。"""
    return GrepFilesTool()
