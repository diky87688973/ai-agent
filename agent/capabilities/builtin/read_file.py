# -*- coding: utf-8 -*-
"""read_file 工具：读取文本文件（支持行区间与截断）。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from agent.capabilities.registry import ToolPlugin

DEFAULT_MAX_CHARS = 200000


class ReadFileTool(ToolPlugin):
    """读取文本文件内容（1-based 闭区间行切片；编码容错）。"""

    name = "read_file"
    label = "读取文件"
    icon = "📖"
    description = "读取文本文件；可选行区间（line_start/line_end）与 max_chars 截断。"
    parameters = {
        "path": {"type": "string", "description": "文件路径"},
        "line_start": {"type": "integer", "description": "起始行（1-based，含）"},
        "line_end": {"type": "integer", "description": "结束行（1-based，含）"},
        "max_chars": {"type": "integer", "description": "最大返回字符数，默认 200000"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw = str(arguments.get("path") or "").strip()
        if not raw:
            raise ValueError("缺少 path")
        target = Path(raw)
        if not target.is_file():
            raise FileNotFoundError(f"文件不存在或不是文件：{target}")
        text = target.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        total_lines = len(lines)
        if total_lines == 0:
            return {
                "path": str(target),
                "content": "",
                "line_start": 0,
                "line_end": 0,
                "total_lines": 0,
                "truncated": False,
            }
        start = max(1, int(arguments.get("line_start") or 1))
        end_raw = arguments.get("line_end")
        end = min(int(end_raw) if end_raw else total_lines, total_lines)
        if start > end:
            raise ValueError(f"行区间无效：line_start={start} > line_end={end}（共 {total_lines} 行）")
        content = "\n".join(lines[start - 1:end])
        max_chars = int(arguments.get("max_chars") or DEFAULT_MAX_CHARS)
        truncated = False
        if max_chars > 0 and len(content) > max_chars:
            content = content[:max_chars]
            truncated = True
        return {
            "path": str(target),
            "content": content,
            "line_start": start,
            "line_end": end,
            "total_lines": total_lines,
            "truncated": truncated,
        }


def build() -> ReadFileTool:
    """构造 read_file 插件。"""
    return ReadFileTool()
